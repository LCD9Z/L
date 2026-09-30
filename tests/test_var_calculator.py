# -*- coding: utf-8 -*-
"""EnhancedVaRCalculator（risk/var_calculator.py）测试。

守卫重点：
1. 数据不足 / 非法输入 → None，绝不编造数值（项目红线）；
2. 三种方法的相对关系与解析近似值（正态 99% VaR ≈ -2.326σ）；
3. EWMA 对近期亏损更敏感（近期恶化时 EWMA VaR 更深）；
4. hybrid 恒等于 0.4×historical + 0.6×ewma。
"""
import math
import random

import pytest

from risk.var_calculator import (
    EnhancedVaRCalculator,
    ewma_var,
    historical_var,
    hybrid_var,
)


def _normal_returns(n=500, mu=0.0005, sigma=0.02, seed=42):
    rng = random.Random(seed)
    return [rng.gauss(mu, sigma) for _ in range(n)]


# ---------------------------------------------------------------------------
# 守卫语义
# ---------------------------------------------------------------------------

def test_insufficient_data_returns_none():
    calc = EnhancedVaRCalculator()
    assert calc.calculate_var(None) is None
    assert calc.calculate_var([]) is None
    assert calc.calculate_var([0.01] * 99) is None        # 99 < 100
    assert calc.calculate_var([0.01] * 100) is not None   # 恰好达标


def test_invalid_confidence_returns_none():
    calc = EnhancedVaRCalculator()
    rets = _normal_returns()
    assert calc.calculate_var(rets, confidence=0.0) is None
    assert calc.calculate_var(rets, confidence=1.0) is None
    assert calc.calculate_var(rets, confidence=-0.99) is None


def test_nan_contaminated_series_returns_none():
    calc = EnhancedVaRCalculator()
    rets = _normal_returns()
    rets[10] = float("nan")
    assert calc.calculate_var(rets) is None


def test_invalid_method_rejected():
    with pytest.raises(ValueError):
        EnhancedVaRCalculator(method="montecarlo")


def test_lookback_window_limits_samples():
    calc = EnhancedVaRCalculator(lookback_days=120)
    rets = _normal_returns(n=500)
    # 前 380 个是良性样本，最近 120 个是深亏 —— 有限窗口应反映最近数据
    recent_bad = [0.0] * 380 + [-0.30 + i * 1e-9 for i in range(120)]
    normal = calc.calculate_var(rets)
    bad = calc.calculate_var(recent_bad)
    assert bad < normal  # 更深（更负）的 VaR


# ---------------------------------------------------------------------------
# 方法语义
# ---------------------------------------------------------------------------

def test_historical_var_matches_normal_approximation():
    calc = EnhancedVaRCalculator(method="historical")
    rets = _normal_returns(sigma=0.02)
    var = calc.calculate_var(rets, confidence=0.99)
    # 正态近似 99% 分位 = μ - 2.326σ ≈ 0.0005 - 0.0465 ≈ -0.046
    assert var == pytest.approx(-0.046, abs=0.02)


def test_ewma_deeper_than_historical_when_recent_losses_worsen():
    # 400 天平静 + 最近 100 天逐步加深的亏损（最深者最近）：EWMA 应比历史分位更深
    calm = [random.Random(1).gauss(0.0, 0.005) for _ in range(400)]
    stress = [-0.02 - 0.0002 * i for i in range(100)]
    rets = calm + stress
    h = historical_var(rets, 0.99)
    e = ewma_var(rets, 0.99, lambda_ewma=0.94)
    assert e < h, f"近期恶化时 EWMA({e:.4f}) 应深于历史分位({h:.4f})"


def test_ewma_sensitive_to_ordering_historical_is_not():
    """同一组数值、不同时间顺序：历史分位完全相同，EWMA 必须不同。

    这是「EWMA 对近期变化更快」的最严格证明 —— 排除样本构成的干扰。
    """
    calm = [random.Random(2).gauss(0.0, 0.005) for _ in range(400)]
    stress = [-0.02 - 0.0002 * i for i in range(100)]
    recent_stress = calm + stress   # 压力在最近
    mid_stress = stress + calm      # 压力在中段（数值完全相同）
    h1 = historical_var(recent_stress, 0.99)
    h2 = historical_var(mid_stress, 0.99)
    assert h1 == pytest.approx(h2)  # 历史分位与顺序无关
    e1 = ewma_var(recent_stress, 0.99, 0.94)
    e2 = ewma_var(mid_stress, 0.99, 0.94)
    assert e1 < e2, f"压力在近端({e1:.4f}) 应深于在远端({e2:.4f})"


def test_hybrid_is_weighted_average():
    rets = _normal_returns(seed=7)
    h = historical_var(rets, 0.99)
    e = ewma_var(rets, 0.99, 0.94)
    assert hybrid_var(rets, 0.99, 0.94) == pytest.approx(0.4 * h + 0.6 * e)
    calc = EnhancedVaRCalculator(method="hybrid")
    assert calc.calculate_var(rets, 0.99) == pytest.approx(0.4 * h + 0.6 * e)


def test_var_negative_and_es_at_least_as_deep():
    calc = EnhancedVaRCalculator(method="historical")
    rets = _normal_returns(seed=11)
    var, es = calc.calculate_var_and_es(rets, 0.99)
    assert var < 0
    assert es is not None and es <= var  # ES（尾部均值）不浅于 VaR


def test_multi_day_var_sqrt_rule():
    calc = EnhancedVaRCalculator()
    assert calc.calculate_multi_day_var(-0.02, 10) == pytest.approx(-0.02 * math.sqrt(10))
    assert calc.calculate_multi_day_var(None, 10) is None
    assert calc.calculate_multi_day_var(-0.02, 0) is None


def test_validate_and_statistics():
    calc = EnhancedVaRCalculator()
    ok, msg = calc.validate_returns(_normal_returns())
    assert ok and msg == ""
    bad = _normal_returns()[:50]
    ok, msg = calc.validate_returns(bad)
    assert not ok and "不足" in msg
    # 北交所 ±30% 属正常波动：默认 ±35% 界不应误报
    ok, msg = calc.validate_returns(_normal_returns() + [-0.30])
    assert ok, msg
    stats = calc.get_var_statistics(_normal_returns(seed=3))
    assert stats["count"] == 500 and stats["min"] <= stats["percentile_1"] <= stats["median"] <= stats["percentile_99"] <= stats["max"]
    assert calc.get_var_statistics([]) == {}
