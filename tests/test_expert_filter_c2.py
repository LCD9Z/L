# -*- coding: utf-8 -*-
"""C2：两个原标 ❌ 的专家条件的单测（产业策略师拥挤度 / 估值分析师上轨排除）。

## 背景

`risk/expert_filter.py` 的模块表里，这两条长期写「⚠️ 未实现」，
理由是「需先做统计行业聚类」「需 PIT 财务 join」。两个前提其实都已存在
（`pit/statistical_industry.py` / `pit/pit_fundamentals.py`），
2026-10-18 把它们接进过滤器。

## 这些测试防什么

- **整簇 vs 单股**：拥挤度是**簇级**判定，只排除「自己热」的那只等于退化成条件 A，
  是最容易写错的地方；
- **PIT 窗不含当日**：窗口写成含当日 → 当日极值把自己稀释掉，永不触发（静默失效）；
- **缺失即不干预**：缺 turnover / 缺 pe_ttm / 截面过薄时**不许猜**；
- **默认关闭**：新条件默认 False，否则会静默改写既有研究的配置。

全部用合成数据 + 注入 labels / fund，**不碰磁盘数据集**。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

import pytest

from risk.expert_filter import (
    IND_CROWD_LOOKBACK,
    MIN_CROSS_SECTION,
    VAL_HIGH_PCT,
    build_expert_filter,
    precompute_industry_crowding,
    precompute_valuation_cap,
)


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

def _days(n: int, start: date = date(2020, 1, 1)) -> List[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def _bars(days: List[str], turnovers: Sequence[Optional[float]],
          close: float = 10.0) -> List[Dict[str, Any]]:
    return [{"date": d, "close": close, "turnover": t, "limit_ratio": 0.1}
            for d, t in zip(days, turnovers, strict=True)]


def _labels(days: List[str], mapping: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    """静态簇映射，每天一样（真实实现里会定期重聚类）。"""
    return {d: dict(mapping) for d in days}


class _FakeFund:
    """最小 `PitFundamentals` 替身：只实现 ``factors_as_of``。"""

    def __init__(self, table: Dict[tuple, Dict[str, float]]):
        self._table = table

    def factors_as_of(self, code: str, day: str,
                      price: Optional[float] = None) -> Dict[str, Any]:
        return self._table.get((code, day), {})


# ---------------------------------------------------------------------------
# 产业策略师 · 行业拥挤度 gate
# ---------------------------------------------------------------------------

CLUSTER0 = ["600000", "600001", "600002", "600003", "600004"]
CLUSTER1 = ["600010", "600011", "600012", "600013", "600014"]
MAPPING = {**dict.fromkeys(CLUSTER0, 0), **dict.fromkeys(CLUSTER1, 1)}


def test_industry_crowding_excludes_whole_hot_cluster():
    """簇 0 最后一天换手率飙到历史最高 → **整簇 5 只**全排除，簇 1 不受影响。"""
    n = IND_CROWD_LOOKBACK + 10
    days = _days(n)
    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in CLUSTER0:
        to = [1.0] * n
        to[-1] = 9.0                      # 远高于历史任何一天
        data[c] = _bars(days, to)
    for c in CLUSTER1:
        data[c] = _bars(days, [1.0] * n)

    out = precompute_industry_crowding(data, labels=_labels(days, MAPPING))

    assert days[-1] in out, "最后一天簇 0 明显拥挤，应触发排除"
    assert out[days[-1]] == set(CLUSTER0), (
        "必须是**整簇**排除（簇级判定），不能只排自己热的那只")
    assert not (out[days[-1]] & set(CLUSTER1)), "簇 1 平稳，不得被误排"


def test_industry_crowding_flat_series_never_triggers():
    """全程完全平稳 → 分位恒为 0 → 不得触发（防「任何输入都排除」的假阳性）。"""
    n = IND_CROWD_LOOKBACK + 10
    days = _days(n)
    data = {c: _bars(days, [1.0] * n) for c in CLUSTER0 + CLUSTER1}

    out = precompute_industry_crowding(data, labels=_labels(days, MAPPING))
    assert out == {}, f"平稳序列不该产生排除，实际 {sorted(out)}"


def test_industry_crowding_requires_full_lookback():
    """历史不足 ``lookback`` 日 → 不判定（缺失即不干预，不猜）。"""
    n = IND_CROWD_LOOKBACK - 1
    days = _days(n)
    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in CLUSTER0:
        to = [1.0] * n
        to[-1] = 9.0
        data[c] = _bars(days, to)
    for c in CLUSTER1:
        data[c] = _bars(days, [1.0] * n)

    out = precompute_industry_crowding(data, labels=_labels(days, MAPPING))
    assert out == {}, "历史窗未满时不得给出拥挤判定"


def test_industry_crowding_missing_turnover_still_excluded():
    """簇拥挤判定是**簇级外部信息** → 当日缺 turnover 的同簇成员**也被排除**。

    这是刻意为之的**保守方向**：宁可少买一只不知情的，也不在已知过热的风格里持仓。
    与「个股自身指标缺失就不判它」（条件 A 的语义）不同 —— 那里没有外部信息可用。
    同时验证：有效成员不足 ``min_cluster_size`` 时**整簇不判定**。
    """
    n = IND_CROWD_LOOKBACK + 10
    days = _days(n)
    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in CLUSTER0:
        to: List[Optional[float]] = [1.0] * n
        to[-1] = 9.0
        data[c] = _bars(days, to)
    data["600004"] = _bars(days, [None] * n)     # 全程缺 turnover
    for c in CLUSTER1:
        data[c] = _bars(days, [1.0] * n)

    labels = _labels(days, MAPPING)
    # 4 只有效成员 ≥ 3 → 簇仍可判定，整簇（含缺数据的那只）被排除
    out = precompute_industry_crowding(data, labels=labels, min_cluster_size=3)
    assert out.get(days[-1]) == set(CLUSTER0), (
        "簇级判定成立时，整簇成员（含当日缺 turnover 的）都应进入排除集")

    # 有效成员 < min_cluster_size → 整簇不判定
    out2 = precompute_industry_crowding(data, labels=labels, min_cluster_size=5)
    assert out2.get(days[-1], set()) == set(), "有效成员不足时整簇不判定"


def test_industry_crowding_percentile_window_excludes_today():
    """PIT：分位窗**不含当日** —— 当日值只作被比较对象。

    构造（``lookback=5``，前 7 天恒 1.0，当日 2.0）：

    - 正确实现（窗＝前 5 天 ``[1,1,1,1,1]``）→ ``below/len = 5/5 = 1.0``；
    - 错误实现（窗含当日 ``[1,1,1,1,2]``）→ ``4/5 = 0.8``。

    取阈值 ``0.9`` 正好卡在两者之间：**只有窗不含当日才会触发**。
    这是「含当日 → 当日极值稀释自己 → 永不触发」这个静默失效形态的直接判据。
    """
    n = 8
    days = _days(n)
    turnaround = [1.0] * (n - 1) + [2.0]
    data = {c: _bars(days, turnaround) for c in CLUSTER0}
    data.update({c: _bars(days, [1.0] * n) for c in CLUSTER1})

    out = precompute_industry_crowding(
        data, labels=_labels(days, MAPPING), lookback=5, pct=0.9)

    assert days[-1] in out, (
        "窗不含当日时分位=1.0 > 0.9 → 应触发；"
        "若把当日也算进窗，分位被稀释成 0.8 → 不触发（静默失效）")
    assert out[days[-1]] == set(CLUSTER0)
    # 前 7 天当日值恒等于历史值 → below=0 → 不得触发
    assert not any(d in out for d in days[:-1]), "平稳日不该触发"


def test_industry_crowding_rejects_unknown_normalize():
    """`normalize` 只允许预注册的两个口径 —— 拼错不许静默退化成默认值。"""
    days = _days(5)
    data = {c: _bars(days, [1.0] * 5) for c in CLUSTER0}
    with pytest.raises(ValueError, match="normalize"):
        precompute_industry_crowding(data, labels=_labels(days, MAPPING),
                                     normalize="zscore")


def test_industry_crowding_ratio_mode_runs():
    """`ratio` 口径能跑通，且不改变「整簇排除」的语义。

    ⚠️ **暖机期是 2×lookback**：先用 250 天算「均值」得到比率，再用 250 个比率
    算分位 —— 所以第 `2×lookback` 天后才开始判定。
    这是两个口径的**可判期不同**（`ratio` 少约 250 天），比较时必须按共同可判期对齐。
    """
    n = 2 * IND_CROWD_LOOKBACK + 10
    days = _days(n)
    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in CLUSTER0:
        to = [1.0] * n
        to[-1] = 9.0                      # 相对历史均值 1.0 → 比率 9.0，远高于历史比率
        data[c] = _bars(days, to)
    for c in CLUSTER1:
        data[c] = _bars(days, [1.0] * n)

    out = precompute_industry_crowding(data, labels=_labels(days, MAPPING),
                                       normalize="ratio")
    assert out, "ratio 口径下「当日相对强度 9 倍」应触发"
    assert out[days[-1]] == set(CLUSTER0), "仍须整簇排除"


def test_industry_crowding_ratio_warmup_is_double_lookback():
    """`ratio` 在 `2×lookback` 之前**不得**给出判定（暖机期未满即不猜）。"""
    n = 2 * IND_CROWD_LOOKBACK - 1
    days = _days(n)
    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in CLUSTER0:
        to = [1.0] * n
        to[-1] = 9.0
        data[c] = _bars(days, to)
    for c in CLUSTER1:
        data[c] = _bars(days, [1.0] * n)

    out = precompute_industry_crowding(data, labels=_labels(days, MAPPING),
                                       normalize="ratio")
    assert out == {}, "比率序列历史不足 lookback 时不得判定"


# ---------------------------------------------------------------------------
# 估值分析师 · 估值上轨排除
# ---------------------------------------------------------------------------

def test_valuation_cap_excludes_top_third():
    """60 只有效估值 → cut = int(60×0.67) = 40 → idx 40..59 被排除。"""
    n_codes = 60
    day = "2024-01-02"
    codes = [f"{600000 + i}" for i in range(n_codes)]
    data = {c: _bars([day], [1.0]) for c in codes}
    table = {(c, day): {"pe_ttm": float(i + 1)} for i, c in enumerate(codes)}

    out = precompute_valuation_cap(data, fund=_FakeFund(table))
    excl = out.get(day, set())
    cut = int(n_codes * VAL_HIGH_PCT)
    expected = {codes[i] for i in range(cut, n_codes)}
    assert excl == expected, f"应排除最高 {n_codes - cut} 只，实际 {len(excl)} 只"
    assert codes[0] not in excl, "估值最低的那只绝不能被排除"


def test_valuation_cap_skips_thin_cross_section():
    """截面 < min_cross_section → 不做分档（薄截面分位无意义）。"""
    n_codes = MIN_CROSS_SECTION - 1
    day = "2024-01-02"
    codes = [f"{600000 + i}" for i in range(n_codes)]
    data = {c: _bars([day], [1.0]) for c in codes}
    table = {(c, day): {"pe_ttm": float(i + 1)} for i, c in enumerate(codes)}

    out = precompute_valuation_cap(data, fund=_FakeFund(table))
    assert out == {}, "截面过薄时不得给出排除判定"


def test_valuation_cap_ignores_missing_and_nonpositive():
    """缺 pe_ttm / 负 PE 不参与排序，也**不被排除**（负 PE 无经济含义）。"""
    day = "2024-01-02"
    n_codes = 60
    codes = [f"{600000 + i}" for i in range(n_codes)]
    data = {c: _bars([day], [1.0]) for c in codes}
    table: Dict[tuple, Dict[str, float]] = {
        (c, day): {"pe_ttm": float(i + 1)} for i, c in enumerate(codes)}
    table[(codes[0], day)] = {}                 # 缺失
    table[(codes[1], day)] = {"pe_ttm": -5.0}   # 负值

    out = precompute_valuation_cap(data, fund=_FakeFund(table))
    excl = out.get(day, set())
    assert codes[0] not in excl and codes[1] not in excl, "缺失/负值不得被判上轨"


def test_valuation_cap_requires_fund_or_dataset():
    with pytest.raises(ValueError, match="fund 或 dataset_dir"):
        precompute_valuation_cap({}, fund=None, dataset_dir=None)


# ---------------------------------------------------------------------------
# 组合：默认关闭 + AND 语义
# ---------------------------------------------------------------------------

def _tiny_panel() -> Dict[str, List[Dict[str, Any]]]:
    days = _days(6)
    return {c: _bars(days, [1.0, 1.0, 1.0, 1.0, 1.0, 5.0]) for c in CLUSTER0}


def test_new_conditions_off_by_default():
    """新条件默认 False —— 不得静默改写既有研究（`run_expert_filter_study`）的配置。"""
    flt, stats = build_expert_filter(_tiny_panel(), use_tail=False,
                                    use_turnover=False, use_streak=False,
                                    use_market=False)
    assert stats["enabled"]["industry_crowding"] is False
    assert stats["enabled"]["valuation_cap"] is False
    assert stats["industry_crowd_excl_pairs"] == 0
    assert stats["valuation_cap_excl_pairs"] == 0
    assert flt("600000", [], "2020-01-06") is True, "无任何条件时应全部保留"


def test_new_conditions_and_semantics():
    """任一条件命中即排除（AND 组合）；两条件都关时不排除。"""
    n = IND_CROWD_LOOKBACK + 10
    days = _days(n)
    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in CLUSTER0:
        to = [1.0] * n
        to[-1] = 9.0
        data[c] = _bars(days, to)
    for c in CLUSTER1:
        data[c] = _bars(days, [1.0] * n)

    flt, stats = build_expert_filter(
        data, use_tail=False, use_turnover=False, use_streak=False, use_market=False,
        use_industry_crowding=True, ind_labels=_labels(days, MAPPING))

    assert stats["enabled"]["industry_crowding"] is True
    assert stats["industry_crowd_excl_pairs"] >= len(CLUSTER0)
    last = days[-1]
    assert flt("600000", data["600000"], last) is False, "簇 0 拥挤 → 应排除"
    assert flt("600010", data["600010"], last) is True, "簇 1 平稳 → 应保留"
    # caliber 必须随 stats 一起返回，否则结论无法复述口径
    assert stats["caliber"]["ind_crowd_pct"] == pytest.approx(0.80)
    assert stats["caliber"]["ind_n_clusters"] == 20
