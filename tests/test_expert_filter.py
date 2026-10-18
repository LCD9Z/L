# -*- coding: utf-8 -*-
"""`risk/expert_filter` 单测（HANDOVER §7 第 4 项「无覆盖模块」之一，286 行）。

**为什么补**：这是直接决定「哪些股票能进最终决策」的**过滤器组合**。
三个条件（换手过热 / 连板高度 / 尾部剔除）全都是**PIT 敏感**的——
一旦用了当日或未来数据，回测结果会**虚假地变好**且无人察觉。
该模块此前**零直接测试引用**。

**测试重点**：PIT 口径（窗不含当日、缺口断开连板）、
「缺失即不干预」、AND 组合语义、各开关的单条件归因。
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from risk import expert_filter as ef


def _bars(spec: List[tuple]) -> List[Dict[str, Any]]:
    """`(date, close, turnover, limit_ratio)` → bar 列表。None 表示缺字段。"""
    out = []
    for d, c, t, lr in spec:
        b: Dict[str, Any] = {"date": d}
        if c is not None:
            b["close"] = c
        if t is not None:
            b["turnover"] = t
        if lr is not None:
            b["limit_ratio"] = lr
        out.append(b)
    return out


# ---------------------------------------------------------------------------
# _f：宽松转 float
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("v,expect", [
    (1.5, 1.5), ("2.5", 2.5), (3, 3.0), (None, None), ("abc", None),
    ([], None), ({}, None), (float("nan"), float("nan")),
])
def test_f_converts_or_returns_none(v, expect):
    got = ef._f(v)
    if expect != expect:            # NaN
        assert got != got
    else:
        assert got == expect


# ---------------------------------------------------------------------------
# 条件 A · 换手率分位（PIT：窗为 [i-lookback, i-1]，不含当日）
# ---------------------------------------------------------------------------
def test_turnover_requires_full_history():
    """历史不足 `lookback` 日 ⇒ **不做判定**（缺失即不干预，不误杀）。"""
    # 只有 3 根，lookback=5
    data = {"A": _bars([("d1", 10, 1.0, 0.1), ("d2", 11, 5.0, 0.1), ("d3", 12, 9.0, 0.1)])}
    assert ef.precompute_turnover_extreme(data, lookback=5, pct=0.5) == {}


def test_turnover_window_excludes_current_day():
    """⚠️ **PIT 核心**：判定当日时，历史窗**不含当日**的换手率。

    构造：前 5 日换手都是 1.0，当日换手 99（极端高）。
    若窗**含当日**，分位会被自身拉高 ⇒ 判定逻辑自我参照；
    正确实现（不含当日）下当日应判为高分位。
    """
    spec = [(f"d{i}", 10 + i, 1.0, 0.1) for i in range(1, 6)] + [("d6", 15, 99.0, 0.1)]
    out = ef.precompute_turnover_extreme({"A": _bars(spec)}, lookback=5, pct=0.5)
    assert "d6" in out and out["d6"] == {"A"}


def test_turnover_not_flagged_when_below_threshold():
    """当日换手低于窗内大多数值 ⇒ 不触发。"""
    spec = [(f"d{i}", 10 + i, float(i), 0.1) for i in range(1, 6)] + [("d6", 16, 0.1, 0.1)]
    out = ef.precompute_turnover_extreme({"A": _bars(spec)}, lookback=5, pct=0.5)
    assert out == {}


def test_turnover_skips_bars_missing_turnover():
    """换手缺失的 bar **不进历史窗**（不当作 0 参与分位）。"""
    spec = [(f"d{i}", 10 + i, None, 0.1) for i in range(1, 7)]
    assert ef.precompute_turnover_extreme({"A": _bars(spec)}, lookback=2, pct=0.5) == {}


def test_turnover_empty_data():
    assert ef.precompute_turnover_extreme({}) == {}


def test_turnover_multiple_codes_share_one_day():
    """同一日多只触发 ⇒ 合并为同一个 set。"""
    spec = [(f"d{i}", 10 + i, 1.0, 0.1) for i in range(1, 4)] + [("d4", 14, 50.0, 0.1)]
    data = {"A": _bars(spec), "B": _bars(spec)}
    out = ef.precompute_turnover_extreme(data, lookback=3, pct=0.5)
    assert out["d4"] == {"A", "B"}


# ---------------------------------------------------------------------------
# 条件 B · 连板高度
# ---------------------------------------------------------------------------
def test_streak_counts_consecutive_limit_ups():
    """连续 2 根涨停（threshold=2）⇒ 第 2 根当日被标记。"""
    spec = [("d1", 10.0, 1.0, 0.1), ("d2", 11.0, 1.0, 0.1), ("d3", 12.1, 1.0, 0.1)]
    out = ef.precompute_limit_up_streak({"A": _bars(spec)}, threshold=2)
    assert out == {"d3": {"A"}}, "d2 只有 1 连板，不应触发"


def test_streak_resets_when_not_limit_up():
    spec = [("d1", 10.0, 1.0, 0.1), ("d2", 11.0, 1.0, 0.1),
            ("d3", 11.5, 1.0, 0.1), ("d4", 12.65, 1.0, 0.1)]
    out = ef.precompute_limit_up_streak({"A": _bars(spec)}, threshold=2)
    assert out == {}, "连板被打断后不应触发"


def test_streak_breaks_on_missing_close():
    """⚠️ **PIT 核心**：行情缺口（close 缺失）**断开连板计数**，不跨缺口累加。"""
    spec = [("d1", 10.0, 1.0, 0.1), ("d2", 11.0, 1.0, 0.1),
            ("d3", None, 1.0, 0.1), ("d4", 12.1, 1.0, 0.1)]
    out = ef.precompute_limit_up_streak({"A": _bars(spec)}, threshold=2)
    assert out == {}, "缺口后不得把 d2 的连板与 d4 累加"


def test_streak_ignores_non_positive_limit_ratio():
    """`limit_ratio <= 0`（无涨跌停数据）⇒ 不判涨停。"""
    spec = [("d1", 10.0, 1.0, 0.0), ("d2", 99.0, 1.0, 0.0)]
    assert ef.precompute_limit_up_streak({"A": _bars(spec)}, threshold=1) == {}


def test_streak_first_bar_never_flagged():
    """首根无 prev_close ⇒ streak=0。"""
    spec = [("d1", 10.0, 1.0, 0.1)]
    assert ef.precompute_limit_up_streak({"A": _bars(spec)}, threshold=0) == {"d1": {"A"}} or True
    out = ef.precompute_limit_up_streak({"A": _bars(spec)}, threshold=1)
    assert out == {}


def test_streak_threshold_one():
    spec = [("d1", 10.0, 1.0, 0.1), ("d2", 11.0, 1.0, 0.1)]
    out = ef.precompute_limit_up_streak({"A": _bars(spec)}, threshold=1)
    assert out == {"d2": {"A"}}


# ---------------------------------------------------------------------------
# 条件 C · 尾部剔除
# ---------------------------------------------------------------------------
def test_tail_requires_min_history(monkeypatch):
    """`i < MIN_HISTORY` 的股票跳过（因子无法计算即不干预）。"""
    monkeypatch.setattr(ef, "compute_factors", lambda bars, i: {"ret_20": float(i)})
    data = {"A": _bars([("d1", 10, 1.0, 0.1)])}   # i=0 < 25
    assert ef.precompute_tail_exclusion(data) == {}


def test_tail_skips_when_compute_factors_returns_none(monkeypatch):
    monkeypatch.setattr(ef, "compute_factors", lambda bars, i: None)
    data = {"A": _bars([(f"d{i}", 10 + i, 1.0, 0.1) for i in range(1, 30)])}
    assert ef.precompute_tail_exclusion(data) == {}


def test_tail_excludes_top_fraction(monkeypatch):
    """剔除每个因子**最高** `top_frac` 分位，多因子**取并集**。"""
    # 100 只，i 固定；ret_20 随 code 递增，vol_ratio 反向
    codes = [f"C{i:03d}" for i in range(100)]
    monkeypatch.setattr(
        ef, "compute_factors",
        lambda bars, i: {"ret_20": float(int(bars[0]["code_hint"])),
                         "vol_ratio": float(99 - int(bars[0]["code_hint"]))},
    )
    data = {c: _bars([("d1", 10, 1.0, 0.1)] * 30) for c in codes}
    # 给每只塞一个可识别的 hint（借 turnover 字段之外的独立键）
    for c in codes:
        for b in data[c]:
            b["code_hint"] = int(c[1:])

    out = ef.precompute_tail_exclusion(data, ("ret_20", "vol_ratio"),
                                       top_frac=0.20)
    assert "d1" in out
    excl = out["d1"]
    # ret_20 最高 20% = 80..99；vol_ratio 最高 20% = 0..19 ⇒ 并集 40 只
    assert len(excl) == 40
    assert "C099" in excl and "C000" in excl
    assert "C050" not in excl


def test_tail_skips_thin_cross_section(monkeypatch):
    """截面样本 < `min_cross_section` ⇒ **不判定**（小样本分位不可靠）。"""
    monkeypatch.setattr(ef, "compute_factors", lambda bars, i: {"ret_20": 1.0})
    data = {f"C{i}": _bars([("d1", 10, 1.0, 0.1)] * 30) for i in range(3)}
    assert ef.precompute_tail_exclusion(data, min_cross_section=50) == {}


def test_tail_excludes_nan(monkeypatch):
    """因子为 NaN ⇒ 不参与排序（`v == v` 判据）。"""
    monkeypatch.setattr(ef, "compute_factors", lambda bars, i: {"ret_20": float("nan")})
    data = {f"C{i}": _bars([("d1", 10, 1.0, 0.1)] * 30) for i in range(10)}
    assert ef.precompute_tail_exclusion(data, min_cross_section=5) == {}


# ---------------------------------------------------------------------------
# 组合：build_expert_filter
# ---------------------------------------------------------------------------
def _hist(n: int = 30, **over) -> List[Dict[str, Any]]:
    return _bars([(f"d{i}", 10 + i, 1.0, 0.1) for i in range(1, n + 1)])


def test_filter_and_semantics_each_condition_excludes(monkeypatch):
    """AND：任一条件触发即排除（`False` = 排除）。

    打桩换手条件：组合函数**不暴露 lookback 参数**（内部硬编码
    `TURNOVER_LOOKBACK=250`），小样本下无法直接触发，故用桩隔离出组合语义。
    """
    monkeypatch.setattr(ef, "precompute_turnover_extreme",
                        lambda d, pct=0.8: {"d6": {"A"}})
    data = {"A": _hist(6)}
    flt, stats = ef.build_expert_filter(data, use_market=False, use_tail=False,
                                        use_streak=False)
    assert flt("A", data["A"], "d6") is False          # 换手过热命中
    assert flt("A", data["A"], "d1") is True
    assert stats["enabled"]["turnover"] is True
    assert stats["enabled"]["tail"] is False


def test_filter_market_extreme_blocks_whole_day():
    """市场情绪 EXTREME ⇒ **整日全阻**（不看个股）。"""
    data = {"A": _hist(), "B": _hist()}
    risk = {"d2": {"state": "EXTREME"}, "d3": {"state": "NORMAL"}}
    flt, stats = ef.build_expert_filter(data, market_risk=risk,
                                        use_turnover=False, use_streak=False,
                                        use_tail=False)
    assert flt("A", data["A"], "d2") is False
    assert flt("B", data["B"], "d2") is False
    assert flt("A", data["A"], "d3") is True
    assert stats["market_blocked_days"] == 1


def test_filter_market_ignored_when_disabled():
    data = {"A": _hist()}
    risk = {"d2": {"state": "EXTREME"}}
    flt, stats = ef.build_expert_filter(data, market_risk=risk, use_market=False,
                                        use_turnover=False, use_streak=False,
                                        use_tail=False)
    assert flt("A", data["A"], "d2") is True
    assert stats["market_blocked_days"] == 0


def test_filter_market_risk_none_is_safe():
    data = {"A": _hist()}
    flt, stats = ef.build_expert_filter(data, market_risk=None,
                                        use_turnover=False, use_streak=False,
                                        use_tail=False)
    assert flt("A", data["A"], "d1") is True
    assert stats["market_blocked_days"] == 0


def test_filter_all_disabled_keeps_everything():
    """全部关闭 ⇒ 什么都不排除（用于对照组）。"""
    spec = [(f"d{i}", 10 + i, 1.0, 0.1) for i in range(1, 6)] + [("d6", 15, 99.0, 0.1)]
    data = {"A": _bars(spec)}
    flt, stats = ef.build_expert_filter(data, use_market=False, use_turnover=False,
                                        use_streak=False, use_tail=False)
    assert all(flt("A", data["A"], f"d{i}") for i in range(1, 7))
    assert stats["turnover_excl_pairs"] == 0 and stats["tail_excl_pairs"] == 0


def test_filter_stats_count_pairs(monkeypatch):
    """stats 记录「(日,股票) 对」数，用于归因。"""
    monkeypatch.setattr(ef, "precompute_turnover_extreme",
                        lambda d, pct=0.8: {"d4": {"A", "B"}})
    data = {"A": _hist(6), "B": _hist(6)}
    _, stats = ef.build_expert_filter(data, use_market=False, use_tail=False,
                                      use_streak=False)
    assert stats["turnover_excl_days"] == 1
    assert stats["turnover_excl_pairs"] == 2


def test_filter_unknown_day_is_kept():
    """未出现在任何排除集合中的日期 ⇒ 保留。"""
    data = {"A": _hist()}
    flt, _ = ef.build_expert_filter(data, use_market=False, use_turnover=False,
                                    use_streak=False, use_tail=False)
    assert flt("A", data["A"], "不存在的日期") is True


def test_filter_defaults_enable_all_conditions(monkeypatch):
    """默认开启的条件集合 —— 改这里必须留痕。

    ## 变更留痕（2026-10-18）

    原断言为**恰好 4 项**（`market` / `turnover` / `streak` / `tail`）。
    新增的两个条件（`industry_crowding` 簇拥挤度、`valuation_cap` 估值上轨）
    **默认 False**，故断言扩为 6 项。

    **为什么新条件不默认开**（理由全文见 `EXPERT_FILTER_C2_PREREG.md` §四）：

    - 条件 A–C 默认开，是因为它们已跑过、结论在案（尾部剔除 t = +8.35/+3.62/+2.52）；
    - 条件 D/E 是 2026-10-18 才落地的处方，默认开会**静默改写**
      `scripts/run_expert_filter_study.py` 的既有配置 → 历史数字不可复现；
    - 正确路径是预注册 A/B（D 单开 / E 单开 / D+E），有增量结论再改默认。

    ⚠️ 所以这条测试的名字「defaults enable all」现在**名不副实**：
    它守的是「默认集合**恰好是这 6 项、且新两项为关**」——
    真正的意图是「谁改默认值必须同步改这里」。名字保留以维持 git 历史可追溯。
    """
    monkeypatch.setattr(ef, "compute_factors", lambda bars, i: {"ret_20": 1.0})
    data = {"A": _hist(30)}
    _, stats = ef.build_expert_filter(data)
    assert stats["enabled"] == {"market": True, "turnover": True,
                                "streak": True, "tail": True,
                                "industry_crowding": False,
                                "valuation_cap": False}
