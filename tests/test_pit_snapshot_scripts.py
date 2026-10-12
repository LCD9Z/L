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

import sys
from pathlib import Path
from typing import Dict, List

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_pit_gap_check as gap  # noqa: E402
import run_pit_snapshot_ingest as ing  # noqa: E402
from pit.pit_snapshot_store import PitSnapshotStore  # noqa: E402


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
