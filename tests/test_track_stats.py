# -*- coding: utf-8 -*-
"""`track/stats` 单测（HANDOVER §7 第 4 项「无覆盖模块」之一，163 行）。

**为什么补**：这是**推荐质量校准**的唯一统计入口——胜率、平均收益、
「高分是否真的更好」全靠这里的口径。它此前**零直接测试引用**，
而口径错了会直接误导「推荐系统是否有用」的判断。

**重点**：`compute_stats` 里**看空档位用「方向收益%」（= −avg）**，
与看多档的「平均收益%」是**两个不同字段**——混用会得出相反结论。
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from track import stats as ts


# ---------------------------------------------------------------------------
# stance_bucket：立场归一
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("stance,expect", [
    ("强烈看多", "看多"), ("看多", "看多"),
    ("强烈看空", "看空"), ("看空", "看空"),
    ("中性", "中性"), ("", "中性"), (None, "中性"), ("随便", "中性"),
])
def test_stance_bucket(stance, expect):
    assert ts.stance_bucket(stance) == expect


# ---------------------------------------------------------------------------
# is_hit：命中判定
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ret,bucket,expect", [
    (1.0, "看多", 1.0), (-1.0, "看多", 0.0), (0.0, "看多", 0.0),
    (-1.0, "看空", 1.0), (1.0, "看空", 0.0), (0.0, "看空", 0.0),
    (1.0, "中性", None), (-1.0, "中性", None),
    (None, "看多", None), (None, "看空", None), (None, "中性", None),
])
def test_is_hit(ret, bucket, expect):
    assert ts.is_hit(ret, bucket) == expect


def test_is_hit_zero_is_not_a_hit_in_either_direction():
    """⚠️ 收益恰好为 0 ⇒ 双向**都不算命中**（严格不等号）。"""
    assert ts.is_hit(0.0, "看多") == 0.0
    assert ts.is_hit(0.0, "看空") == 0.0


# ---------------------------------------------------------------------------
# _norm_date：日期归一（兼容两种格式）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("s,expect", [
    ("2024-01-02", "20240102"), ("20240102", "20240102"),
    (None, None), ("", ""), (0, 0),
])
def test_norm_date(s, expect):
    assert ts._norm_date(s) == expect


# ---------------------------------------------------------------------------
# find_base_and_close
# ---------------------------------------------------------------------------
def _k(dates_and_close: List[tuple]) -> List[Dict[str, Any]]:
    return [{"date": d, "close": c} for d, c in dates_and_close]


def test_find_base_is_first_bar_on_or_after_rec_date():
    k = _k([("2024-01-01", 10), ("2024-01-02", 11), ("2024-01-03", 12)])
    assert ts.find_base_and_close(k, "2024-01-02", 1) == (11.0, 12.0)


def test_find_base_skips_to_next_bar_when_rec_date_absent():
    """推荐日无 K 线（如非交易日）⇒ 取**之后第一根**为基准。"""
    k = _k([("2024-01-01", 10), ("2024-01-05", 11), ("2024-01-08", 12)])
    assert ts.find_base_and_close(k, "2024-01-02", 1) == (11.0, 12.0)


def test_find_base_mixed_date_formats():
    """东财(YYYY-MM-DD) 与本地(YYYYMMDD) 混排也能正确比较。"""
    k = _k([("20240101", 10), ("2024-01-02", 11), ("20240103", 12)])
    assert ts.find_base_and_close(k, "2024-01-02", 1) == (11.0, 12.0)


def test_find_base_returns_none_when_no_bar_after():
    k = _k([("2024-01-01", 10)])
    assert ts.find_base_and_close(k, "2024-12-31", 1) == (None, None)


def test_find_base_close_none_when_horizon_incomplete():
    """⚠️ **未满 N 根时 close 为 None**（表示仍待回填），但基准价已可得。"""
    k = _k([("2024-01-01", 10), ("2024-01-02", 11)])
    assert ts.find_base_and_close(k, "2024-01-01", 5) == (10.0, None)


def test_find_base_horizon_zero_returns_same_bar():
    k = _k([("2024-01-01", 10), ("2024-01-02", 11)])
    assert ts.find_base_and_close(k, "2024-01-01", 0) == (10.0, 10.0)


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------
@pytest.fixture
def stats_of(monkeypatch):
    """把 list_rows 换成可控桩，返回 compute_stats 的结果。"""

    def _run(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        monkeypatch.setattr(ts, "list_rows", lambda conn, backfilled=False: rows)
        return ts.compute_stats(object())
    return _run


def test_stats_empty(stats_of):
    assert stats_of([]) == {}


def test_stats_bull_win_rate_and_avg(stats_of):
    rows = [{"horizon": 5, "stance": "看多", "return_pct": 2.0, "score": 8.0},
            {"horizon": 5, "stance": "看多", "return_pct": -1.0, "score": 8.0}]
    out = stats_of(rows)
    cell = out["5日-看多"]
    assert cell["样本数"] == 2
    assert cell["胜率%"] == 50.0
    assert cell["平均收益%"] == 0.5


def test_stats_bear_uses_direction_return_field(stats_of):
    """⚠️ **看空档用「方向收益%」，不是「平均收益%」**（取负号）。

    看空命中 = 下跌 = 原收益<0 ⇒ 取负后为正，与胜率语义一致。
    误读为「平均收益%」会得到**符号相反**的结论。
    """
    rows = [{"horizon": 5, "stance": "看空", "return_pct": -3.0, "score": None},
            {"horizon": 5, "stance": "看空", "return_pct": -1.0, "score": None}]
    out = stats_of(rows)
    cell = out["5日-看空"]
    assert cell["样本数"] == 2 and cell["胜率%"] == 100.0
    assert "方向收益%" in cell and cell["方向收益%"] == 2.0   # -(-2.0)
    assert "平均收益%" not in cell, "看空档不应出现「平均收益%」字段"


def test_stats_neutral_counts_sample_but_no_return(stats_of):
    """⚠️ **已登记缺陷（HANDOVER §5.3 #14）**：中性档的**胜率显示为 0.0%**。

    中性档 `is_hit` 返回 `None` ⇒ `hit` 与 `rets` 都不累加，
    但胜率仍按 `hit / n * 100` 算出 **0.0** ——
    语义上中性**无方向可判**，0.0% 会被误读为「中性判断全部失败」，
    而正确展示应为「不适用」(`None`)。

    本测试按 characterization **锁定当前（0.0）行为**；
    修好后须改为 `is None`。
    """
    rows = [{"horizon": 5, "stance": "中性", "return_pct": 2.0, "score": None},
            {"horizon": 5, "stance": "中性", "return_pct": 4.0, "score": None}]
    out = stats_of(rows)
    cell = out["5日-中性"]
    assert cell["样本数"] == 2
    assert cell["胜率%"] == 0.0, "现状：中性档胜率被算成 0.0（缺陷 #14）"
    assert cell["平均收益%"] is None, "中性档不累计收益"


def test_stats_default_horizon_is_five(stats_of):
    rows = [{"stance": "看多", "return_pct": 1.0, "score": None}]
    assert "5日-看多" in stats_of(rows)


def test_stats_separates_horizons(stats_of):
    rows = [{"horizon": 5, "stance": "看多", "return_pct": 1.0, "score": None},
            {"horizon": 20, "stance": "看多", "return_pct": 1.0, "score": None}]
    out = stats_of(rows)
    assert {"5日-看多", "20日-看多"} <= set(out)


def test_stats_score_buckets(stats_of):
    """评分档：≥7.5 高分 / ≥4 中分 / <4 低分（边界值必须落在高档）。"""
    rows = [{"horizon": 5, "stance": "看多", "return_pct": 10.0, "score": 7.5},
            {"horizon": 5, "stance": "看多", "return_pct": 0.0, "score": 4.0},
            {"horizon": 5, "stance": "看多", "return_pct": -5.0, "score": 3.99}]
    out = stats_of(rows)
    assert out["评分:高分(≥7.5)"]["平均收益%"] == 10.0
    assert out["评分:中分(4-7.5)"]["平均收益%"] == 0.0
    assert out["评分:低分(<4)"]["平均收益%"] == -5.0


def test_stats_score_bucket_has_no_win_rate(stats_of):
    """评分档**不做命中判定**（跨方向混合无意义）⇒ 胜率恒为 None。"""
    rows = [{"horizon": 5, "stance": "看多", "return_pct": 1.0, "score": 8.0}]
    assert stats_of(rows)["评分:高分(≥7.5)"]["胜率%"] is None


def test_stats_skips_none_score(stats_of):
    rows = [{"horizon": 5, "stance": "看多", "return_pct": 1.0, "score": None}]
    assert not any(k.startswith("评分:") for k in stats_of(rows))


def test_stats_skips_none_return_in_avg(stats_of):
    """收益缺失 ⇒ 不进平均（缺失即缺失，不当作 0）。"""
    rows = [{"horizon": 5, "stance": "看多", "return_pct": None, "score": None},
            {"horizon": 5, "stance": "看多", "return_pct": 4.0, "score": None}]
    out = stats_of(rows)
    assert out["5日-看多"]["样本数"] == 2
    assert out["5日-看多"]["平均收益%"] == 4.0   # 不是 2.0


def test_stats_all_returns_missing_gives_none_avg(stats_of):
    rows = [{"horizon": 5, "stance": "看多", "return_pct": None, "score": None}]
    assert stats_of(rows)["5日-看多"]["平均收益%"] is None


def test_stats_rounding(stats_of):
    """胜率保留 1 位、平均收益保留 2 位（展示口径）。"""
    rows = [{"horizon": 5, "stance": "看多", "return_pct": 1.0 / 3, "score": None},
            {"horizon": 5, "stance": "看多", "return_pct": 2.0 / 3, "score": None},
            {"horizon": 5, "stance": "看多", "return_pct": 3.0 / 3, "score": None}]
    out = stats_of(rows)
    assert out["5日-看多"]["胜率%"] == 100.0
    assert out["5日-看多"]["平均收益%"] == 0.67
