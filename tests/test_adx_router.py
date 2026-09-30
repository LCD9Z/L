# -*- coding: utf-8 -*-
"""ADX 市场状态路由器测试。

重点守卫：
1. Wilder ADX 在趋势/震荡序列上给出方向正确的区分；
2. 防前视：decide(date) 只依赖 date 及之前的数据；
3. confirm_days 平滑确定性回放；
4. 默认关闭 / 数据不足 / 手动覆盖的回退语义。
"""
import math

import pytest

from regime.adx_router import (
    RegimeRouter,
    classify_regime,
    compute_adx_by_date,
)


# ---------------------------------------------------------------------------
# 测试数据构造
# ---------------------------------------------------------------------------

def _trending_bars(days=80, start=100.0, drift=0.5, noise=0.0):
    """稳定上涨序列（可叠加确定性的锯齿噪声）。"""
    bars = []
    price = start
    for i in range(days):
        wiggle = noise * (1 if i % 2 == 0 else -1)
        o = price
        c = price + drift + wiggle
        bars.append({
            "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": o, "high": max(o, c) + 0.1, "low": min(o, c) - 0.1, "close": c,
        })
        price = c
    return bars


def _flat_bars(days=80, base=100.0, swing=2.0):
    """多空方向交替的震荡序列（+DM/-DM 轮流出现 → DX≈0 → ADX 低位）。

    注意：不能用「窄幅静止」构造震荡 —— 无相反方向的 DM 时 DI- 恒为 0，
    DX 恒为 100，ADX 永远不衰减，那不是震荡而是趋势衰竭。
    """
    bars = []
    price = base
    prev_high = None
    prev_low = None
    for i in range(days):
        if i % 2 == 0:      # 上行日：high 创新高 → +DM
            o, c = price, price + swing
            h = (prev_high + 1.0) if prev_high is not None else c + 1.0
            low = o - 1.0
        else:               # 下行日：low 创新低 → -DM
            o, c = price, price - swing
            h = o + 1.0
            low = (prev_low - 1.0) if prev_low is not None else o - 1.0
        bars.append({
            "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": o, "high": h, "low": low, "close": c,
        })
        prev_high, prev_low = h, low
        price = c
    return bars


# ---------------------------------------------------------------------------
# ADX 计算
# ---------------------------------------------------------------------------

def test_adx_distinguishes_trend_from_chop():
    trend = compute_adx_by_date(_trending_bars(noise=0.0), period=14)
    chop = compute_adx_by_date(_flat_bars(), period=14)
    assert trend and chop
    assert max(trend.values()) > 40.0, f"趋势序列 ADX 应显著偏高: {max(trend.values()):.1f}"
    assert max(chop.values()) < 25.0, f"窄幅震荡序列 ADX 应偏低: {max(chop.values()):.1f}"


def test_adx_stays_elevated_in_persistent_uptrend():
    bars = _trending_bars()
    adx_map = compute_adx_by_date(bars, period=14)
    dates = sorted(adx_map)
    first, last = adx_map[dates[0]], adx_map[dates[-1]]
    # 持续上涨（无回调）→ DX 恒为 100 → ADX 全程贴顶且不回落
    assert first > 40.0 and last >= first


def test_adx_insufficient_data_returns_empty():
    assert compute_adx_by_date(_trending_bars(days=20), period=14) == {}
    assert compute_adx_by_date([], period=14) == {}


def test_classify_regime_thresholds():
    assert classify_regime(19.9) == "震荡"
    assert classify_regime(20.0) == "萌芽"
    assert classify_regime(24.9) == "萌芽"
    assert classify_regime(25.0) == "明确"


# ---------------------------------------------------------------------------
# 路由器语义
# ---------------------------------------------------------------------------

def test_router_disabled_by_default():
    router = RegimeRouter({}, index_bars=_trending_bars())
    d = router.decide("2024-03-01")
    assert d.source == "disabled"
    assert d.position_ratio == 1.0
    assert not d.is_active()


def test_router_insufficient_data_falls_back_to_no_scaling():
    router = RegimeRouter({"enabled": True}, index_bars=_trending_bars(days=20))
    d = router.decide("2024-03-01")  # 数据远早于该日 / 暖机不足
    assert d.source == "insufficient_data"
    assert d.position_ratio == 1.0


def test_router_auto_decision_maps_position_ratio():
    router = RegimeRouter({"enabled": True}, index_bars=_trending_bars())
    d = router.decide("2024-03-01")  # 趋势序列 → 明确 → 1.0
    assert d.source == "auto"
    assert d.regime == "明确"
    assert d.position_ratio == 1.0
    assert d.adx is not None and d.adx > 25.0


def test_router_no_lookahead():
    """decide(d) 的 ADX 必须等于「截断到 d 的序列」算出的最后一个 ADX。"""
    bars = _trending_bars(days=60)
    router = RegimeRouter({"enabled": True}, index_bars=bars)
    cut = bars[40]["date"]
    full = router.decide(cut)
    truncated = RegimeRouter({"enabled": True}, index_bars=bars[:41])
    part = truncated.decide(cut)
    assert full.adx == pytest.approx(part.adx)
    assert full.regime == part.regime
    # 更晚日期的决策不得早于截断点已知（未来数据不可影响过去决策）
    later = router.decide(bars[59]["date"])
    assert later.adx != full.adx or later.regime == full.regime


def test_confirm_days_smoothing_is_deterministic():
    bars = _trending_bars(days=60) + _flat_bars(days=60, base=200.0)
    # 重新编日期，保证日期连续：后半段与半段同日历格式但值不同
    for i, b in enumerate(bars[60:], start=60):
        b["date"] = f"2025-{((i - 60) // 28) + 1:02d}-{((i - 60) % 28) + 1:02d}"
    fast = RegimeRouter({"enabled": True, "confirm_days": 1}, index_bars=bars)
    slow = RegimeRouter({"enabled": True, "confirm_days": 5}, index_bars=bars)
    # 在整个后半段（状态由趋势衰减为震荡）上，慢路由应产生切换滞后
    diff_days = [d for d in slow._dates if d >= "2025-01-01"
                 and fast.decide(d).regime != slow.decide(d).regime]
    assert diff_days, "confirm_days>1 必须产生切换滞后"
    # 原始标签翻转时，慢路由仍保持旧档位（先由 明确 → 萌芽/震荡 的滞后）
    first_flip = next(d for d in slow._dates if d >= "2025-01-01"
                      and slow.decide(d).raw_regime != slow.decide(d).regime)
    assert slow.decide(first_flip).regime != slow.decide(first_flip).raw_regime
    # 同一日期重复决策结果一致（确定性）
    assert slow.decide("2025-01-10").regime == slow.decide("2025-01-10").regime


def test_manual_override_takes_priority():
    router = RegimeRouter(
        {"enabled": True, "manual_override": {"regime": "震荡"}},
        index_bars=_trending_bars(),
    )
    d = router.decide("2024-03-01")
    assert d.source == "manual"
    assert d.regime == "震荡"
    assert d.position_ratio == pytest.approx(0.3)


def test_custom_position_ratios_and_unknown_config_rejected():
    router = RegimeRouter(
        {"enabled": True, "position_ratios": {"明确": 0.8, "萌芽": 0.4, "震荡": 0.1}},
        index_bars=_trending_bars(),
    )
    assert router.decide("2024-03-01").position_ratio == pytest.approx(0.8)
    with pytest.raises(ValueError):
        RegimeRouter({"not_a_key": 1})


def test_position_scaler_clamps_and_enabled_gate():
    router = RegimeRouter({"enabled": True}, index_bars=_flat_bars())
    scaler = router.make_position_scaler()
    day = sorted(compute_adx_by_date(_flat_bars()))[-1]
    ratio = scaler(day)
    assert 0.0 <= ratio <= 1.0
    assert ratio == pytest.approx(0.3)  # 窄幅震荡 → 震荡档 0.3
    # 关闭状态下 scaler 恒为 1.0（不缩放）
    off = RegimeRouter({}, index_bars=_flat_bars())
    assert off.make_position_scaler()(day) == 1.0


def test_flat_regime_choppy_position_ratio():
    """震荡序列 → 震荡档 → 仓位 0.3（与 KHunter 默认一致）。"""
    router = RegimeRouter({"enabled": True}, index_bars=_flat_bars())
    d = router.decide("2024-03-01")
    assert d.regime == "震荡"
    assert d.position_ratio == pytest.approx(0.3)
