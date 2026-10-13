# -*- coding: utf-8 -*-
"""PIT 采集脚本的纯函数守卫（`scripts/run_pit_snapshot_ingest.py` · `run_pit_gap_check.py`）。

锁住四类**不会报错、但会让结论悄悄变好**的失效：

1. **L2 层级码派生错误** —— `industry_l1` / `industry_l2` 若切错位，
   行业分层归因会把「同一行业」拆成多个 → **虚增行业内样本量**。
2. **L1 的 `effective_date` 与 `ipo_date` 脱钩** —— 双时间轴的生效日会指向错的值。
3. **退市类型不拆分** —— 「缺 N 只退市股」若不区分「真实退市」与「吸收合并」，
   会**严重高估幸存者偏差**（本项目实测：98 只里只有 6 只真实退市）。
4. **申万标签的 PIT 取法错误** —— 若不取「生效日 ≤ 当日的最新一条」，
   会拿到未来才生效的行业（前视）。
5. **L1 的 raw 层被过滤** —— `raw/` 若存 `type == "1"` 的子集，
   就退化成 `normalized/` 的副本，**丧失「复核过滤本身是否正确」的能力**
   （本项目 2026-10-11 实际发生过：磁盘 5,561 行 vs 全量 8,992 行）。
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from typing import Dict, List

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_pit_gap_check as gap  # noqa: E402
import run_pit_snapshot_ingest as ing  # noqa: E402
from pit.pit_snapshot_store import DATASET_REGISTRY, PitSnapshotStore  # noqa: E402


# ---------------------------------------------------------------------------
# L2 规范化
# ---------------------------------------------------------------------------
def test_normalize_l2_derives_hierarchy_codes():
    """6 位层级码 → 一级 = 前 2 位 + '0000'，二级 = 前 4 位 + '00'。"""
    recs = [{"股票代码": "1", "计入日期": "2021-07-30 00:00:00",
             "行业代码": "480301", "更新日期": "2025-12-15 16:33:00"}]
    rows = ing._normalize_l2(recs, "RUN", "2026-10-11T21:00:00+08:00")
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "000001", "股票代码必须补零到 6 位"
    assert r["industry_code"] == "480301"
    assert r["industry_l1"] == "480000"
    assert r["industry_l2"] == "480300"


def test_normalize_l2_truncates_effective_date_to_day():
    """计入日期原值带时分秒；日频口径必须截断到日，否则跨日比较会错。"""
    recs = [{"股票代码": "600000", "计入日期": "2014-02-21 09:30:00",
             "行业代码": "480101", "更新日期": "2024-09-27 09:08:00"}]
    rows = ing._normalize_l2(recs, "RUN", "2026-10-11T21:00:00+08:00")
    assert rows[0]["effective_date"] == "2014-02-21"


def test_normalize_l2_keeps_double_timeline_fields():
    recs = [{"股票代码": "600000", "计入日期": "2014-02-21 00:00:00",
             "行业代码": "480101", "更新日期": "2024-09-27 09:08:00"}]
    r = ing._normalize_l2(recs, "20261011-2130", "2026-10-11T21:00:00+08:00")[0]
    assert r["as_of"] == "2026-10-11T21:00:00+08:00"
    assert r["ingest_run_id"] == "20261011-2130"


# ---------------------------------------------------------------------------
# L1 规范化
# ---------------------------------------------------------------------------
def test_normalize_l1_effective_date_is_ipo_date():
    recs = [{"code": "600519", "code_name": "贵州茅台", "ipo_date": "2001-08-27",
             "out_date": "", "status": "1"}]
    r = ing._normalize_l1(recs, "RUN", "2026-10-11T21:00:00+08:00")[0]
    assert r["effective_date"] == "2001-08-27"
    assert r["is_delisted"] == "0"


def test_normalize_l1_marks_delisted():
    recs = [{"code": "600001", "code_name": "邯郸钢铁", "ipo_date": "1998-01-22",
             "out_date": "2009-12-29", "status": "0"}]
    r = ing._normalize_l1(recs, "RUN", "2026-10-11T21:00:00+08:00")[0]
    assert r["is_delisted"] == "1"


# ---------------------------------------------------------------------------
# L1 的 raw 层必须是「未过滤全量」
#
# ⚠️ 2026-10-11 的 L1 raw 曾由旧版脚本写入**过滤后**数据（磁盘 5,561 行 vs 全量
# 8,992 行）—— raw 因此退化成 normalized 的副本，**丧失「复核过滤本身」的能力**。
# 本组守卫纯函数、不依赖网络，锁住该类复发。
# ---------------------------------------------------------------------------
def _api_row(code: str, typ: str, name: str = "某标的") -> Dict[str, str]:
    return {"code": code, "code_name": name, "ipoDate": "2000-01-01",
            "outDate": "", "type": typ, "status": "1"}


def test_split_l1_filters_only_type_1_into_recs():
    """`recs` 只保留 `type == "1"`（股票）；2=指数 / 4=可转债 / 5=ETF 必须剔除。"""
    api = [_api_row("sh.600000", "1", "浦发银行"), _api_row("sh.000001", "2", "上证指数"),
           _api_row("sh.110000", "4"), _api_row("sh.510300", "5")]
    recs, _raw = ing._split_l1(api)
    assert [r["code"] for r in recs] == ["600000"], "非股票类型不得进入 recs"


def test_split_l1_raw_is_unfiltered_full():
    """⚠️ 核心守卫：raw 必须**原样等于**输入全量，不得只返回过滤后的子集。"""
    api = [_api_row("sh.600000", "1"), _api_row("sh.000001", "2"),
           _api_row("sh.110000", "4"), _api_row("sh.510300", "5")]
    _recs, raw = ing._split_l1(api)
    assert len(raw) == len(api) == 4, "raw 必须是未过滤全量（含非股票类型）"
    assert raw == api, "raw 不得改写、不得过滤"


def test_split_l1_raw_is_strict_superset_of_recs_when_mixed():
    """混合类型时 `len(raw) > len(recs)` —— 相等即说明 raw 被过滤了。"""
    api = [_api_row("sh.600000", "1"), _api_row("sh.000001", "2")]
    recs, raw = ing._split_l1(api)
    assert len(raw) > len(recs), "raw 与 recs 等长 ⇒ raw 存的是过滤后数据（本类缺陷）"


def test_split_l1_code_is_normalized_to_6_digits():
    """`sh.600000` → `600000`（去掉市场前缀）。"""
    recs, _raw = ing._split_l1([_api_row("sz.000001", "1", "平安银行")])
    assert recs[0]["code"] == "000001"


def test_fetch_l1_delegates_to_split_l1():
    """防回归：`_fetch_l1` 必须经 `_split_l1` 拆分，不得内联出第二套过滤逻辑。"""
    src = (ROOT / "scripts" / "run_pit_snapshot_ingest.py").read_text(encoding="utf-8")
    assert "return _split_l1(api_rows)" in src, (
        "_fetch_l1 必须委托给 _split_l1 —— 两套过滤逻辑会漂移"
    )


def _l1_norm_row(code: str) -> Dict[str, str]:
    return {"code": code, "code_name": "X", "ipo_date": "2000-01-01", "out_date": "",
            "status": "1", "is_delisted": "0", "effective_date": "2000-01-01",
            "as_of": "2026-10-12T08:00:00+08:00", "ingest_run_id": "RUN"}


def test_self_check_flags_filtered_l1_raw():
    """⚠️ 核心守卫：L1 的 raw 行数 ≤ 规范层行数 ⇒ 必须 WARN（raw 被过滤）。"""
    rows = [_l1_norm_row("600000")]
    problems, metrics = ing._self_check(rows, ing.L1_DATASET, raw_rows=1)
    assert any("raw 疑似被过滤" in p for p in problems), "过滤后的 raw 必须被标出"
    assert metrics["raw_rows"] == 1


def test_self_check_accepts_full_l1_raw():
    """raw 行数 > 规范层行数（含指数/可转债/ETF）⇒ 不得告警。"""
    rows = [_l1_norm_row("600000")]
    problems, metrics = ing._self_check(rows, ing.L1_DATASET, raw_rows=3)
    assert not any("raw 疑似被过滤" in p for p in problems)
    assert metrics["raw_rows"] == 3


def test_self_check_does_not_flag_l2_raw_equality():
    """L2 的 raw 就是解析后的记录，与规范层等长属**正常** → 不得误报。"""
    rows = [{"code": "000001", "industry_code": "480301", "industry_l1": "480000",
             "industry_l2": "480300", "effective_date": "2021-07-30",
             "as_of": "2026-10-12T08:00:00+08:00", "ingest_run_id": "RUN"}]
    problems, _m = ing._self_check(rows, ing.L2_DATASET, raw_rows=1)
    assert not any("raw 疑似被过滤" in p for p in problems)


def test_ingest_log_entry_includes_raw_rows():
    """采集日志必须记录 raw 行数 —— 否则过滤缺陷在审计链里**隐形**。"""
    src = (ROOT / "scripts" / "run_pit_snapshot_ingest.py").read_text(encoding="utf-8")
    assert '"raw_rows": len(raw_rows)' in src, (
        "日志缺 raw_rows ⇒ 无法从审计链发现 raw 被过滤（2026-10-11 的缺陷正是这样隐形的）"
    )


def test_ingest_log_distinguishes_write_from_skip():
    """日志必须能区分「实际写入」与「已存在跳过」。

    否则两条 `raw_sha256` 相同、`force: false` 的记录无法分辨哪条真写了
    —— 2026-10-11 的 22:44 / 22:45 两条正是此情形。
    """
    src = (ROOT / "scripts" / "run_pit_snapshot_ingest.py").read_text(encoding="utf-8")
    assert 'action = "write"' in src, "缺少写入动作标记"
    assert 'action = "skip"' in src, "缺少跳过动作标记"
    assert '"action": action' in src, "日志未写入 action 字段"


# ---------------------------------------------------------------------------
# baostock 分页静默截断守卫（pit/baostock_guard.py）
#
# ⚠️ 机制（读 baostock/data/resultset.py 得出）：
#   某页**恰好** 2000 行时，客户端会去取下一页；若该请求失败（空响应 / 非成功错误码）
#   → `next()` **直接 return False 且不抛异常** → 调用方看到「干净地结束在 2000 行」。
#   2026-10-12 实测同一接口同时段 0.9.3 / 0.9.4 均得 2,000，另一时刻得 8,992
#   → **不是版本差异，是服务端返回规模时变 × 客户端静默停止**。
# ---------------------------------------------------------------------------
from pit.baostock_guard import (  # noqa: E402
    BAOSTOCK_PER_PAGE_COUNT,
    assert_not_truncated,
    suspect_truncation,
)


def test_suspect_truncation_boundaries():
    assert suspect_truncation(2000) is True
    assert suspect_truncation(4000) is True
    assert suspect_truncation(8000) is True
    assert suspect_truncation(8992) is False
    assert suspect_truncation(4291) is False
    assert suspect_truncation(0) is False, "0 行不是截断（是空结果，另一类失效）"
    assert suspect_truncation(1999) is False


def test_assert_not_truncated_raises_on_multiple_of_page():
    """整数倍 ⇒ 抛错（**宁可失败，不可静默写入残缺快照**）。"""
    for n in (2000, 4000, 6000):
        with pytest.raises(RuntimeError, match="分页静默截断"):
            assert_not_truncated(n, "test")


def test_assert_not_truncated_passes_on_real_totals():
    """实测过的真实总数（8,992 / 4,291 / 5,561）不得被误拦。"""
    for n in (8992, 4291, 5561, 1, 0):
        assert_not_truncated(n, "test")


def test_page_count_constant_matches_baostock():
    """⚠️ 2000 是 baostock 的**私有实现细节** —— 上游改了本模块须同步。

    装了 baostock 才校验（未装则跳过，不误报）。
    """
    try:
        from baostock.common import contants
    except ImportError:
        pytest.skip("未安装 baostock（可选依赖）")
    assert BAOSTOCK_PER_PAGE_COUNT == contants.BAOSTOCK_PER_PAGE_COUNT, (
        "baostock 的 PER_PAGE_COUNT 已变 —— pit/baostock_guard.py 的常量须同步"
    )


def test_l1_fetch_is_guarded_against_silent_truncation():
    """防回归：`_fetch_l1` 必须调用截断守卫。"""
    src = (ROOT / "scripts" / "run_pit_snapshot_ingest.py").read_text(encoding="utf-8")
    assert "assert_not_truncated(len(api_rows)" in src, (
        "L1 采集未接截断守卫 —— 残缺快照会被静默写入 raw/ 与 normalized/"
    )


def test_gap_check_calendar_is_guarded_against_silent_truncation():
    """防回归：交易日历被截断会报出**假缺口**，必须守卫。"""
    src = (ROOT / "scripts" / "run_pit_gap_check.py").read_text(encoding="utf-8")
    assert "assert_not_truncated(n_raw" in src, "断更检测的日历未接截断守卫"


# ---------------------------------------------------------------------------
# L3 日频估值历史（脚本纯函数）
# ---------------------------------------------------------------------------
def test_bs_symbol_prefix_mapping():
    """号段 → 市场前缀。

    ⚠️ 2026-10-13 实测（baostock 0.9.3 · query_history_k_data_plus）：
    该端点**只接受 sh./sz.** —— ``bj.830799`` 报 ``10004011 股票代码未标识sh或sz``；
    北交所号段（4xx/8xx/920xxx）无任何覆盖 → 4/8 段显式抛错（见下一测试），
    920 段走 sh. 前缀收空响应（记零数据清单，见 test_fetch_l3_records_zero_data_as_not_failed）。
    """
    assert ing.bs_symbol("600519") == "sh.600519"
    assert ing.bs_symbol("000001") == "sz.000001"
    assert ing.bs_symbol("300750") == "sz.300750"
    assert ing.bs_symbol("688981") == "sh.688981"
    assert ing.bs_symbol("920000") == "sh.920000", "920 段走 sh. 前缀（baostock 只认 sh/sz）"
    assert ing.bs_symbol("519") == "sz.000519", "不足 6 位须补零后再判号段"


def test_bs_symbol_rejects_unknown_prefix():
    """⚠️ 未知号段必须**抛错**，不得猜 —— 猜错会静默取到别的标的。"""
    with pytest.raises(ValueError, match="未知号段"):
        ing.bs_symbol("700001")


def test_bs_symbol_rejects_beijing_segment_with_coverage_note():
    """⚠️ 北交所 4/8 段显式抛错：baostock 本端点拒绝 bj. 前缀（10004011），
    sh./sz. 前缀对该段为 success 空响应 —— 猜前缀只会把「源无覆盖」伪装成
    「取到了但为空」。抛错让调用方记入零数据清单（显式），不混入抓取失败。
    """
    with pytest.raises(ValueError, match="北交所号段"):
        ing.bs_symbol("830799")
    with pytest.raises(ValueError, match="10004011"):
        ing.bs_symbol("430047")


def test_normalize_l3_maps_fields_and_keeps_effective_date():
    raw = [{"date": "2024-01-02", "code": "sh.600519", "close": "1685.01",
            "peTTM": "29.732", "pbMRQ": "9.718", "psTTM": "9.0",
            "pcfNcfTTM": "37.3", "turn": "0.2", "tradestatus": "1", "isST": "0"}]
    r = ing._normalize_l3(raw, "RUN", "2026-10-12T20:00:00+08:00")[0]
    assert r["code"] == "600519"
    assert r["effective_date"] == "2024-01-02", "effective_date 必须取交易日"
    assert r["pe_ttm"] == "29.732" and r["pb_mrq"] == "9.718"
    assert r["as_of"] == "2026-10-12T20:00:00+08:00"
    assert r["ingest_run_id"] == "RUN"


def test_normalize_l3_drops_rows_without_date():
    """⚠️ 无日期 → 无法定位 PIT 生效点 → **丢弃而非猜**。"""
    raw = [{"date": "", "code": "sh.600519", "close": "1"},
           {"date": "2024-01-02", "code": "sh.600519", "close": "2"}]
    assert len(ing._normalize_l3(raw, "RUN", "T")) == 1


def test_normalize_l3_does_not_coerce_or_impute():
    """**缺失即缺失**：空值原样保留为空串，不填 0、不插补。"""
    raw = [{"date": "2024-01-02", "code": "sh.600519", "close": "1",
            "peTTM": "", "pbMRQ": None}]
    r = ing._normalize_l3(raw, "RUN", "T")[0]
    assert r["pe_ttm"] == "" and r["pb_mrq"] == ""


def test_l3_registered_with_composite_unique_key():
    """L3 必须已登记，且主键为 (code, effective_date)（同一标的多日）。"""
    assert "l3_valuation" in DATASET_REGISTRY
    assert DATASET_REGISTRY["l3_valuation"]["unique_key"] == ("code", "effective_date")
    assert DATASET_REGISTRY["l3_valuation"]["pit_mode"] == "revisable", (
        "回填的 as_of=采集日 ≠ effective_date —— 未通过对账前不得声明 immutable_fact"
    )


def test_universe_codes_reads_sorted_digits_only(tmp_path: Path):
    d = tmp_path / "ds" / "stocks"
    d.mkdir(parents=True)
    for name in ("600519.csv", "000001.csv", "note.txt", "abc.csv"):
        (d / name).write_text("x", encoding="utf-8")
    got = ing._universe_codes(str(tmp_path / "ds"))
    assert got == ["000001", "600519"], "只取 6 位数字代码并升序"
    assert ing._universe_codes(str(tmp_path / "ds"), limit=1) == ["000001"]


# ---------------------------------------------------------------------------
# L3 对账脚本的 PIT 判据（scripts/run_l3_valuation_reconciliation.py）
#
# ⚠️ 背景：旧判据把「A 股披露日」当「首次公开日」，会把 **A+H 公司**
# （港股业绩公告早于 A 股年报 4~8 周）的「baostock 正确、我方偏晚」
# 误判成 `early`（疑似前视）。新判据用「切换日 vs 报告期起始 / 披露日」。
# ---------------------------------------------------------------------------
import run_l3_valuation_reconciliation as rec  # noqa: E402


def test_reconciliation_docstring_labels_logical_not_statistical():
    """⚠️ P010 Q3.1：n=60 对账是**逻辑一致性检查**，不是**统计代表性检查**。

    docstring 必须显式标注强度边界 —— 否则引用方会把「逻辑判据未证伪」
    高估成「统计代表性验证」（n=60 对 1% 错误率检出概率仅 ~45%）。
    源码断言模式与 test_ingest_log_entry_includes_raw_rows 一致。
    """
    src = (ROOT / "scripts" / "run_l3_valuation_reconciliation.py").read_text(encoding="utf-8")
    for needle in ("逻辑一致性检查", "统计代表性检查", "强度边界"):
        assert needle in src, f"对账脚本 docstring 缺强度边界标注: {needle!r}"


def test_period_start_maps_quarters():
    """报告期 → 起始日（`impossible` 判定的锚点）。"""
    assert rec.period_start("2025-03-31") == "2025-01-01"
    assert rec.period_start("2025-06-30") == "2025-04-01"
    assert rec.period_start("2025-09-30") == "2025-07-01"
    assert rec.period_start("2025-12-31") == "2025-10-01"


def test_implied_eps_rejects_non_positive_pe():
    assert rec.implied_eps(10.0, 5.0) == pytest.approx(2.0)
    assert rec.implied_eps(10.0, 0.0) is None, "peTTM=0 无经济含义"
    assert rec.implied_eps(10.0, -3.0) is None, "负 PE 不硬算"
    assert rec.implied_eps(None, 5.0) is None


def test_switch_dates_ignores_small_drift():
    """⚠️ 核心：baostock 的隐含 EPS 有 0.03%~0.31% 的**数值漂移**（非报表变化）。

    若阈值过小（如 1e-4），漂移会被当成切换 → **伪造出「早于披露日/报告期」的切换**。
    """
    rows: List[rec.Row] = [("2025-01-02", 100.0, 10.0, None),    # eps = 10.0
                           ("2025-01-03", 100.2, 10.0, None),    # eps = 10.02  ← 0.2% 漂移
                           ("2025-02-10", 120.0, 10.0, None)]    # eps = 12.0   ← 真实变化 20%
    sw = rec.switch_dates(rows)
    assert [d for d, _ in sw] == ["2025-01-02", "2025-02-10"], "0.2% 漂移不得记为切换"


def test_switch_dates_keeps_material_change():
    rows: List[rec.Row] = [("2025-01-02", 100.0, 10.0, None),
                           ("2025-01-03", 100.0, 8.0, None)]     # eps 10 → 12.5
    assert len(rec.switch_dates(rows)) == 2


def test_last_and_first_switch_helpers():
    sws = [("2025-01-02", 1.0), ("2025-03-05", 2.0), ("2025-06-10", 3.0)]
    assert rec._last_switch_le(sws, "2025-04-01") == ("2025-03-05", 2.0)
    assert rec._first_switch_gt(sws, "2025-04-01") == ("2025-06-10", 3.0)
    assert rec._last_switch_le(sws, "2024-12-31") is None
    assert rec._first_switch_gt(sws, "2026-01-01") is None


def test_shift_moves_days():
    assert rec._shift("2025-03-28", 3) == "2025-03-31"
    assert rec._shift("2025-12-30", 3) == "2026-01-02"


# ---------------------------------------------------------------------------
# 退市类型拆分（本项目实测：不拆分会把 98 高估成 6 的 16 倍）
# ---------------------------------------------------------------------------
def _store_with_l1(tmp_path: Path, rows: List[Dict[str, str]]) -> PitSnapshotStore:
    st = PitSnapshotStore(tmp_path / "snap")
    st.write_normalized("l1_stock_basic", "2026-10-11", rows)
    return st


def _l1_row(code: str, name: str, ipo: str, out: str) -> Dict[str, str]:
    return {"code": code, "code_name": name, "ipo_date": ipo, "out_date": out,
            "status": "0" if out else "1", "is_delisted": "1" if out else "0",
            "effective_date": ipo, "as_of": "2026-10-11T21:00:00+08:00",
            "ingest_run_id": "RUN"}


def test_reconcile_l1_splits_true_delist_from_merger(tmp_path: Path):
    """⚠️ 核心守卫：真实退市（含「退」）与吸收合并必须分开报。

    构造：3 只退市股 —— 1 只真实退市（含「退」）、2 只吸收合并（不含「退」）；
    本地只覆盖其中 1 只合并股 → 缺失 = 1 真退 + 1 合并。
    """
    rows = [
        _l1_row("000001", "平安银行", "1991-04-03", ""),            # 在市
        _l1_row("000033", "新都退", "1994-01-03", "2017-07-07"),     # 真实退市（缺）
        _l1_row("601299", "中国北车", "2009-12-29", "2015-05-20"),   # 吸收合并（缺）
        _l1_row("600005", "武钢股份", "1999-08-03", "2017-02-14"),   # 吸收合并（本地有）
    ]
    st = _store_with_l1(tmp_path, rows)
    dsdir = tmp_path / "ds" / "stocks"
    dsdir.mkdir(parents=True)
    for c in ("000001", "600005"):
        (dsdir / f"{c}.csv").write_text("date,close\n", encoding="utf-8")

    rec = ing._reconcile_l1(st, str(tmp_path / "ds"), "2026-10-11")
    assert rec["src_delisted"] == 3
    assert rec["local_covers_delisted"] == 1
    assert rec["local_missing_delisted"] == 2
    assert rec["missing_true_delist"] == 1, "真实退市应只算 1 只"
    assert rec["missing_true_delist_codes"] == ["000033"]
    assert rec["missing_merge_or_restructure"] == 1


def test_reconcile_l1_reports_delisting_wave_separately(tmp_path: Path):
    """退市潮年份（2020-2024）必须单独报 —— 它直接回答「近年结论是否受影响」。"""
    rows = [
        _l1_row("000001", "平安银行", "1991-04-03", ""),
        _l1_row("000002", "某退A", "2000-01-01", "2022-05-10"),   # 潮内
        _l1_row("000003", "某退B", "2000-01-01", "2024-11-01"),   # 潮内
        _l1_row("000004", "某退C", "2000-01-01", "2015-01-01"),   # 潮外
    ]
    st = _store_with_l1(tmp_path, rows)
    dsdir = tmp_path / "ds" / "stocks"
    dsdir.mkdir(parents=True)
    (dsdir / "000001.csv").write_text("date,close\n", encoding="utf-8")
    (dsdir / "000002.csv").write_text("date,close\n", encoding="utf-8")   # 只覆盖 1 只潮内

    rec = ing._reconcile_l1(st, str(tmp_path / "ds"), "2026-10-11")
    assert rec["wave_2020_2024_src"] == 2
    assert rec["wave_2020_2024_covered"] == 1
    assert rec["wave_2020_2024_coverage_pct"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# 申万标签的 PIT 取法
# ---------------------------------------------------------------------------
def test_build_sw_labels_takes_latest_effective_le_day(tmp_path: Path):
    """⚠️ 核心守卫：某日的行业 = 生效日 ≤ 该日的**最新一条**（不得取到未来的）。"""
    st = PitSnapshotStore(tmp_path / "snap")
    st.write_normalized("l2_sw_industry", "2026-10-11", [
        {"code": "000001", "industry_code": "440101", "industry_l1": "440000",
         "industry_l2": "440100", "update_ts": "", "effective_date": "1991-04-03",
         "as_of": "2026-10-11T21:00:00+08:00", "ingest_run_id": "RUN"},
        {"code": "000001", "industry_code": "480101", "industry_l1": "480000",
         "industry_l2": "480100", "update_ts": "", "effective_date": "2014-02-21",
         "as_of": "2026-10-11T21:00:00+08:00", "ingest_run_id": "RUN"},
        {"code": "000001", "industry_code": "480301", "industry_l1": "480000",
         "industry_l2": "480300", "update_ts": "", "effective_date": "2021-07-30",
         "as_of": "2026-10-11T21:00:00+08:00", "ingest_run_id": "RUN"},
    ])
    days = ["1995-01-02", "2010-01-04", "2015-01-05", "2024-01-02"]
    import run_industry_ic_attribution as attr  # noqa: E402

    lab = attr._build_sw_labels(str(tmp_path / "snap"), ["000001"], days, "l1")
    # 同一行业字符串 → 同一 id；不同行业 → 不同 id
    assert lab["1995-01-02"]["000001"] == lab["2010-01-04"]["000001"]      # 都是 440000
    assert lab["2015-01-05"]["000001"] == lab["2024-01-02"]["000001"]      # 都是 480000
    assert lab["1995-01-02"]["000001"] != lab["2015-01-05"]["000001"]      # 44 vs 48


def test_build_sw_labels_omits_codes_without_history(tmp_path: Path):
    """该日尚无归属 → **不给标签**（不猜、不填默认值）。"""
    st = PitSnapshotStore(tmp_path / "snap")
    st.write_normalized("l2_sw_industry", "2026-10-11", [
        {"code": "000001", "industry_code": "480101", "industry_l1": "480000",
         "industry_l2": "480100", "update_ts": "", "effective_date": "2014-02-21",
         "as_of": "2026-10-11T21:00:00+08:00", "ingest_run_id": "RUN"},
    ])
    import run_industry_ic_attribution as attr  # noqa: E402

    lab = attr._build_sw_labels(str(tmp_path / "snap"), ["000001"], ["2010-01-04"], "l1")
    assert lab["2010-01-04"] == {}


# ---------------------------------------------------------------------------
# 交易日历（离线路径）
# ---------------------------------------------------------------------------
def test_trading_days_from_csv_filters_range(tmp_path: Path):
    p = tmp_path / "benchmark.csv"
    p.write_text("date,open,close,high,low,volume,amount\n"
                 "2026-09-01,1,1,1,1,1,1\n"
                 "2026-09-02,1,1,1,1,1,1\n"
                 "2026-10-11,1,1,1,1,1,1\n", encoding="utf-8")
    got = gap._trading_days_csv(str(p), "2026-09-01", "2026-09-30")
    assert got == ["2026-09-01", "2026-09-02"]


def test_gap_script_exposes_expected_exit_codes():
    """退出码约定：0 = 无超限缺口；3 = 有缺口（供调度器/告警读）。"""
    src = (ROOT / "scripts" / "run_pit_gap_check.py").read_text(encoding="utf-8")
    assert "rc = 3" in src, "缺口超限必须返回 3（非零），否则会静默通过"


# ---------------------------------------------------------------------------
# L3 抓取韧性与层间一致性（2026-10-12 全市场回填崩溃事故的守卫）
#
# 事故回放：5,667 只的回填跑到第 456 只时，一只 sz.001206 命中
# ``10002007 网络接收错误`` → RuntimeError → **整轮 6 小时任务终止**，
# 已抓的 456 只全部锁在 raw 里、规范化一步未做。
# → 单只失败必须「重试 → 仍败则跳过并记账」，绝不中止整轮；
# → raw/norm 的层间缺口必须显式化（--rebuild-norm 幂等补齐）。
# ---------------------------------------------------------------------------
def test_query_with_retry_recovers_from_transient_network_errors():
    """前两次失败、第三次成功 → 返回结果；每次失败后、下次尝试前重新登录。"""
    calls = {"query": 0, "relogin": 0}

    def query():
        calls["query"] += 1
        if calls["query"] < 3:
            return False, None, "10002007 网络接收错误"
        return True, [{"date": "2024-01-02"}], ""

    def relogin():
        calls["relogin"] += 1

    rows = ing._query_with_retry(query, relogin, 3, (0, 0))
    assert rows == [{"date": "2024-01-02"}]
    assert calls == {"query": 3, "relogin": 2}, "失败两次 ⇒ 两次重试前各登录一次"


def test_query_with_retry_raises_after_all_attempts_fail():
    """持续失败必须抛错（由 _fetch_l3 跳过该只），不得返回空结果冒充成功。"""
    with pytest.raises(RuntimeError, match="重试 3 次仍失败"):
        ing._query_with_retry(lambda: (False, None, "10002007 boom"), lambda: None, 3, (0,))


def test_query_with_retry_treats_query_exception_as_one_failure():
    """query_fn 自身抛异常（WinError 10054 类：先抛、后报 error_code）按一次失败处理。"""
    state = {"n": 0}

    def query():
        state["n"] += 1
        if state["n"] == 1:
            raise ConnectionError("远程主机强迫关闭了一个现有的连接")
        return True, [{"date": "x"}], ""

    assert ing._query_with_retry(query, lambda: None, 2, (0,)) == [{"date": "x"}]


def _fake_baostock(monkeypatch):
    """把惰性导入的 baostock 换成不连网的假模块（login 恒成功）。"""
    import types

    fake = types.SimpleNamespace(
        login=lambda: types.SimpleNamespace(error_code="0", error_msg=""),
        logout=lambda: None,
        query_history_k_data_plus=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "baostock", fake)
    return fake


def test_fetch_l3_skips_code_that_fails_after_retry(monkeypatch):
    """⚠️ 核心守卫：单只持续失败 → 跳过该只、其余照常、记入 failed（不静默、不中止）。"""
    _fake_baostock(monkeypatch)

    def fake_one(sym, start, end):
        if sym == "sz.001206":
            raise RuntimeError("sz.001206: 10002007 网络接收错误")
        return [{"code": sym, "date": "2024-01-02", "close": "1"}]

    monkeypatch.setattr(ing, "_fetch_one_l3", fake_one)
    raw, _n, suspect, real_trunc, failed, _zero, _zero_pref = ing._fetch_l3(
        ["600519", "001206", "000001"], "2016-01-01", "2026-10-12",
        progress_every=0, flush_path=None, flush_every=0,
    )
    assert [r["code"] for r in raw] == ["sh.600519", "sz.000001"], "失败标的被跳过、其余照常"
    assert failed == ["001206: sz.001206: 10002007 网络接收错误"]
    assert suspect == [] and real_trunc == [] and _zero == []


def test_fetch_l3_refetches_page_multiple_and_marks_suspect(monkeypatch):
    """行数恰为 2000（一页）→ 必须重取一次对比；两次一致 ⇒ suspect_stable（人工确认）。"""
    _fake_baostock(monkeypatch)
    rows_2000 = [{"code": "sh.600519", "date": "d", "close": "1"}] * 2000
    calls = {"n": 0}

    def fake_one(sym, start, end):
        calls["n"] += 1
        return rows_2000

    monkeypatch.setattr(ing, "_fetch_one_l3", fake_one)
    _raw, _n, suspect, real_trunc, _failed, _zero, _zero_pref = ing._fetch_l3(
        ["600519"], "2016-01-01", "2026-10-12",
        progress_every=0, flush_path=None, flush_every=0,
    )
    assert calls["n"] == 2, "2000 整数倍必须重取一次对比（防分页静默截断）"
    assert suspect == ["600519:2000"] and real_trunc == []


def test_fetch_l3_records_zero_data_as_not_failed(monkeypatch):
    """⚠️ 查询成功但 0 行 = 源无覆盖（如北交所 920 段 success 空响应），
    **记入 zero_data 而非 failed** —— 混入 failed 会让运维反复重试注定为空的代码，
    不记账则它们永不进 raw、每次 --resume 重试、只剩它们时 min_rows 假 FAIL
    （2026-10-13 收官实测：281 只 920 段代码正是此形态）。

    注意：920xxx 由 bs_symbol 映射为 **sh.** 前缀（baostock 只接受 sh/sz，
    bj. 前缀实测报 10004011）——空响应经该合法符号返回。
    """
    _fake_baostock(monkeypatch)

    def fake_one(sym, start, end):
        if sym in ("sh.920000", "sh.920030"):
            return []
        return [{"code": sym, "date": "2024-01-02", "close": "1"}]

    monkeypatch.setattr(ing, "_fetch_one_l3", fake_one)
    raw, _n, _suspect, _real_trunc, failed, zero_data, zero_pref = ing._fetch_l3(
        ["600519", "920000", "920030"], "2016-01-01", "2026-10-12",
        progress_every=0, flush_path=None, flush_every=0,
    )
    assert [r["code"] for r in raw] == ["sh.600519"], "零数据代码不进 raw"
    assert failed == [], "零数据 ≠ 失败"
    assert sorted(zero_data) == ["920000", "920030"]
    assert zero_pref == [], "success+0 行属「源无数据」形态，非 10004011 形态"


def test_fetch_l3_records_prefix_rejected_codes_as_zero_data(monkeypatch):
    """⚠️ 号段被 bs_symbol 显式拒绝（北交所 4/8 段）→ 同样记 zero_data，
    不得混入 failed（failed 会被 --resume 无限重试），更不得中止整轮。

    形态分离（P010 Q1.3）：10004011「源不接受符号格式」与 success+0 行「源无数据」
    是两种失败形态，metrics 必须分列 —— 混记会把格式错误误当成覆盖差。
    """
    _fake_baostock(monkeypatch)
    called = {"n": 0}

    def fake_one(sym, start, end):
        called["n"] += 1
        return [{"code": sym, "date": "2024-01-02", "close": "1"}]

    monkeypatch.setattr(ing, "_fetch_one_l3", fake_one)
    raw, _n, _suspect, _real_trunc, failed, zero_data, zero_pref = ing._fetch_l3(
        ["600519", "830799"], "2016-01-01", "2026-10-12",
        progress_every=0, flush_path=None, flush_every=0,
    )
    assert [r["code"] for r in raw] == ["sh.600519"], "被拒号段不进 raw、不影响其余标的"
    assert called["n"] == 1, "920/北交所号段不应发起查询"
    assert failed == [] and zero_data == ["830799"]
    assert zero_pref == ["830799"], "10004011 形态须单独记账（P010 Q1.3）"


def test_zero_data_sidecar_reader_and_resume_filter(tmp_path: Path):
    """边车清单：注释/空行跳过、缺文件空集；resume 筛选排除边车与已采码。"""
    p = tmp_path / "l3_zero_data_codes_2026-10-13.txt"
    p.write_text("# 2026-10-13 审计产物\n920000\n\n 920030 \n# 尾注\n", encoding="utf-8")
    got = ing.read_zero_data_codes(p)
    assert got == {"920000", "920030"}, "注释与空行跳过、空白裁剪"
    assert ing.read_zero_data_codes(tmp_path / "nope.txt") == set(), "缺文件 ⇒ 空集"

    kept, excluded = ing.filter_resume_codes(
        ["600519", "000001", "920000", "920030", "920098"],
        done={"600519"}, zero_known={"920000", "920030"},
    )
    assert kept == ["000001", "920098"], "未采且未记零数据才保留"
    assert excluded == ["920000", "920030"], "边车代码被排除（显式返回供打印，不静默）"


def test_zero_data_sidecar_path_is_meta_scoped():
    """边车路径必须落在 meta/ 并含 ingest_date（与 ingest_log 同域，便于对账）。"""
    p = ing.zero_data_sidecar_path(Path("/x/meta"), "2026-10-13")
    assert p == Path("/x/meta/l3_zero_data_codes_2026-10-13.txt")


def test_l3_socket_timeout_constant_is_sane():
    """超时常量必须为正且有上界（否则单只挂起仍可拖死整轮）。"""
    assert 0 < ing._L3_SOCKET_TIMEOUT_S <= 300, (
        f"_L3_SOCKET_TIMEOUT_S={ing._L3_SOCKET_TIMEOUT_S} 不在 (0, 300] 内")


def test_fetch_l3_sets_socket_timeout_before_login(monkeypatch):
    """⚠️ 挂起防护：进入抓取前必须先设 socket 默认超时（且早于 login）。

    2026-10-13 实测事故：baostock 连接 Established 但服务端无响应，
    进程卡死 2 小时 —— 挂起**不抛异常**，重试逻辑完全绕过。
    """
    _fake_baostock(monkeypatch)
    events: List[object] = []

    real_setdefaulttimeout = socket.setdefaulttimeout

    def recording_setdefaulttimeout(value):
        events.append(("setdefaulttimeout", value))
        return real_setdefaulttimeout(value)

    def recording_login():
        events.append("login")
        import types
        return types.SimpleNamespace(error_code="0", error_msg="")

    monkeypatch.setattr(socket, "setdefaulttimeout", recording_setdefaulttimeout)
    monkeypatch.setattr(sys.modules["baostock"], "login", recording_login)
    monkeypatch.setattr(ing, "_fetch_one_l3",
                        lambda sym, s, e: [{"code": sym, "date": "d", "close": "1"}])

    ing._fetch_l3(["600519"], "2016-01-01", "2026-10-12",
                  progress_every=0, flush_path=None, flush_every=0)

    assert events == [
        ("setdefaulttimeout", ing._L3_SOCKET_TIMEOUT_S), "login",
    ], f"必须先设超时再登录，实际事件序列: {events}"


def test_query_with_retry_treats_socket_timeout_as_one_failure():
    """socket.timeout（挂起的表现）按「失败一次」处理，成功后照常返回。

    挂起与 10002007 这类**会抛错**的瞬时错误不同：它连异常都没有。
    设了默认超时后它才落入本通道 —— 本测试锁住这条通路。
    """
    calls = {"n": 0}

    def hang_then_ok():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("timed out")
        return True, ["payload"], ""

    out = ing._query_with_retry(hang_then_ok, lambda: None, 3, (0.0,))
    assert out == ["payload"] and calls["n"] == 2

    def always_hang():
        raise TimeoutError("timed out")

    with pytest.raises(RuntimeError, match="重试 3 次仍失败"):
        ing._query_with_retry(always_hang, lambda: None, 3, (0.0,))


def test_rebuild_norm_appends_only_codes_missing_from_norm(tmp_path: Path):
    """--rebuild-norm：只补 norm 缺失的 code；已有 code 不动；二次运行幂等。"""
    store = PitSnapshotStore(tmp_path)
    ingest = "2026-10-13"
    raw = store.raw_path("baostock", "query_history_k_data_plus", ingest, ".jsonl")
    raw.parent.mkdir(parents=True, exist_ok=True)
    rows_a = [{"code": "sh.600519", "date": "2024-01-02", "close": "1"}]
    rows_b = [{"code": "sz.000001", "date": "2024-01-02", "close": "2"}]
    with raw.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows_a + rows_b:
            fh.write(json.dumps(r) + "\n")
    store.write_normalized(
        "l3_valuation", ingest, ing._normalize_l3(rows_a, "run-x", "2026-10-13T00:00:00+08:00"))

    info = ing._rebuild_norm_l3(store, "baostock", "query_history_k_data_plus",
                                ingest, "run-y", "2026-10-13T01:00:00+08:00")
    assert info["appended_codes"] == 1 and info["appended_rows"] == 1
    assert {r["code"] for r in store.read_normalized("l3_valuation")} == {"600519", "000001"}

    info2 = ing._rebuild_norm_l3(store, "baostock", "query_history_k_data_plus",
                                 ingest, "run-z", "2026-10-13T02:00:00+08:00")
    assert info2["appended_codes"] == 0, "第二次运行必须幂等（一只都不补）"
    assert len(store.read_normalized("l3_valuation")) == 2


def test_layer_gap_detects_codes_present_only_in_raw(tmp_path: Path):
    """⚠️ 核心守卫：raw 有、norm 无 ⇒ in_raw_not_norm 必须点名（事故缺口显式化）。"""
    store = PitSnapshotStore(tmp_path)
    ingest = "2026-10-13"
    raw = store.raw_path("baostock", "query_history_k_data_plus", ingest, ".jsonl")
    raw.parent.mkdir(parents=True, exist_ok=True)
    with raw.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"code": "sh.600519", "date": "2024-01-02"}) + "\n")
    gap = ing._layer_gap(store, "baostock", "query_history_k_data_plus",
                         ingest, "l3_valuation")
    assert gap["raw_codes"] == 1 and gap["norm_codes"] == 0
    assert gap["in_raw_not_norm"] == ["600519"]
    assert gap["in_norm_not_raw"] == []


def test_layer_gap_detects_orphan_codes_present_only_in_norm(tmp_path: Path):
    """⚠️ P010 Q3.2：反向缺口（norm 有、raw 无 = orphan / 「半个 code」残留）
    同样必须点名 —— 行数相等而 code 集合不等是可能的失败形态，只查一个方向会漏掉。"""
    store = PitSnapshotStore(tmp_path)
    ingest = "2026-10-13"
    norm = store.norm_path("l3_valuation", ingest)
    norm.parent.mkdir(parents=True, exist_ok=True)
    store.write_normalized("l3_valuation", ingest, [
        {"code": "600519", "effective_date": "2024-01-02", "as_of": "2026-10-13T00:00:00+08:00",
         "ingest_run_id": "run-x", "close": "1"},
    ])
    gap = ing._layer_gap(store, "baostock", "query_history_k_data_plus",
                         ingest, "l3_valuation")
    assert gap["raw_codes"] == 0 and gap["norm_codes"] == 1
    assert gap["in_raw_not_norm"] == []
    assert gap["in_norm_not_raw"] == ["600519"]


def test_rebuild_norm_then_gap_closes(tmp_path: Path):
    """闭环：补建后层间缺口必须归零（revision guard 的最终判据）。"""
    store = PitSnapshotStore(tmp_path)
    ingest = "2026-10-13"
    raw = store.raw_path("baostock", "query_history_k_data_plus", ingest, ".jsonl")
    raw.parent.mkdir(parents=True, exist_ok=True)
    with raw.open("w", encoding="utf-8", newline="\n") as fh:
        for code in ("sh.600519", "sz.000001"):
            fh.write(json.dumps({"code": code, "date": "2024-01-02", "close": "1"}) + "\n")
    ing._rebuild_norm_l3(store, "baostock", "query_history_k_data_plus",
                         ingest, "run-y", "2026-10-13T01:00:00+08:00")
    gap = ing._layer_gap(store, "baostock", "query_history_k_data_plus",
                         ingest, "l3_valuation")
    assert gap["in_raw_not_norm"] == [], "补建后缺口必须闭合"
