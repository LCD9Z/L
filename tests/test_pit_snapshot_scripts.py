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
