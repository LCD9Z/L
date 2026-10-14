# -*- coding: utf-8 -*-
"""增强 VaR 计算器（自 KHunter `utils/var_calculator.py` 移植，纯标准库实现）。

三种方法（与 KHunter 语义一致）：
- historical：历史分位数法（numpy percentile 的线性插值口径）；
- ewma      ：指数加权（λ 默认 0.94）历史模拟，近期数据权重更高；
- hybrid    ：0.4 × historical + 0.6 × ewma（KHunter 默认，推荐）。

数据真实性红线：
- 样本 < 100 点 / 置信水平非法 / 序列含 NaN → 返回 None，**绝不编造数值**；
- 与 KHunter 的差异（有意为之）：KHunter 的 validate_returns 以 ±20% 为界，
  A股创业板/科创板单日 ±20%、北交所 ±30% 属正常波动，故默认界放宽到 ±35%
  （可通过 abs_return_cap 配置），且 validate 只作提示，不改变 calculate 语义。

约定：收益率序列以「负数表示亏损」，VaR 为负数（如 -0.023 表示 99% 置信下
单日最大亏损约 2.3%）。
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple


def _percentile(sorted_vals: Sequence[float], q_pct: float) -> float:
    """线性插值分位数（与 numpy.percentile 默认 method='linear' 一致）。"""
    n = len(sorted_vals)
    if n == 0:
        raise ValueError("empty sequence")
    if n == 1:
        return float(sorted_vals[0])
    rank = (n - 1) * (q_pct / 100.0)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(sorted_vals[lo])
    frac = rank - lo
    return float(sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo]))


def historical_var(returns: Sequence[float], confidence: float = 0.99) -> float:
    """历史分位数法 VaR（调用方负责样本量校验）。"""
    alpha = 1.0 - confidence
    return _percentile(sorted(returns), alpha * 100.0)


def ewma_var(returns: Sequence[float], confidence: float = 0.99,
             lambda_ewma: float = 0.94) -> float:
    """EWMA 加权历史模拟 VaR：近期样本权重更高，对市场变化反应更快。"""
    n = len(returns)
    weights = [lambda_ewma ** (n - i - 1) for i in range(n)]
    total = sum(weights)
    if total <= 0:
        raise ValueError("invalid weights")
    weights = [w / total for w in weights]
    pairs = sorted(zip(returns, weights, strict=True), key=lambda t: t[0])
    alpha = 1.0 - confidence
    cum = 0.0
    var_index = -1
    for i, (_, w) in enumerate(pairs):
        cum += w
        if cum >= alpha:
            var_index = i
            break
    if var_index <= 0:
        return float(pairs[0][0])
    prev_w = cum - pairs[var_index][1]
    weight_diff = cum - prev_w
    t = (alpha - prev_w) / weight_diff if weight_diff > 0 else 0.0
    lo_val, hi_val = pairs[var_index - 1][0], pairs[var_index][0]
    return float(lo_val + t * (hi_val - lo_val))


def hybrid_var(returns: Sequence[float], confidence: float = 0.99,
               lambda_ewma: float = 0.94) -> float:
    """混合法：0.4 × 历史 + 0.6 × EWMA（兼顾稳定性与敏感性）。"""
    return 0.4 * historical_var(returns, confidence) + 0.6 * ewma_var(
        returns, confidence, lambda_ewma)


class EnhancedVaRCalculator:
    """与 KHunter 同名的增强 VaR 计算器（零第三方依赖）。

    方法与守卫语义保持一致；样本不足 / 非法输入一律返回 None。
    """

    MIN_SAMPLES = 100  # 与 KHunter 一致：样本不足不做统计推断

    def __init__(self, method: str = "hybrid", lambda_ewma: float = 0.94,
                 lookback_days: int = 500, abs_return_cap: float = 0.35):
        if method not in ("historical", "ewma", "hybrid"):
            raise ValueError(f"未知 VaR 方法: {method}")
        self.method = method
        self.lambda_ewma = float(lambda_ewma)
        self.lookback_days = int(lookback_days)
        self.abs_return_cap = float(abs_return_cap)

    # -- 校验 ---------------------------------------------------------------

    def _clean_window(self, returns: Optional[Sequence[float]]) -> Optional[List[float]]:
        """取最近 lookback_days 个样本并做基本质量检查；不合格返回 None。"""
        if returns is None:
            return None
        vals = [float(x) for x in returns][-self.lookback_days:] if len(returns) else []
        if len(vals) < self.MIN_SAMPLES:
            return None
        if any(math.isnan(v) or math.isinf(v) for v in vals):
            return None
        return vals

    # -- 主计算 -------------------------------------------------------------

    def calculate_var(self, returns: Optional[Sequence[float]],
                      confidence: float = 0.99) -> Optional[float]:
        if returns is None or len(returns) == 0:
            return None
        if not (0.0 < confidence < 1.0):
            return None
        vals = self._clean_window(returns)
        if vals is None:
            return None
        try:
            if self.method == "historical":
                return float(historical_var(vals, confidence))
            if self.method == "ewma":
                return float(ewma_var(vals, confidence, self.lambda_ewma))
            return float(hybrid_var(vals, confidence, self.lambda_ewma))
        except (ValueError, ZeroDivisionError):
            return None

    def calculate_var_and_es(self, returns: Optional[Sequence[float]],
                             confidence: float = 0.99) -> Tuple[Optional[float], Optional[float]]:
        """VaR 与 ES（期望损失：超过 VaR 的尾部均值）。尾部为空时 ES 为 None。"""
        var = self.calculate_var(returns, confidence)
        if var is None:
            return None, None
        # var 非 None 已保证窗口合格；`or []` 仅为类型收窄（不改行为）
        vals = self._clean_window(returns) or []
        tail = [v for v in vals if v < var]
        if not tail:
            return var, None
        return var, float(sum(tail) / len(tail))

    def calculate_multi_day_var(self, var_1day: Optional[float], days: int) -> Optional[float]:
        """平方根法则：VaR_n = VaR_1 × sqrt(n)（仅适用于独立同分布近似）。"""
        if var_1day is None or days <= 0:
            return None
        return float(var_1day * math.sqrt(days))

    # -- 辅助 ---------------------------------------------------------------

    def validate_returns(self, returns: Optional[Sequence[float]]) -> Tuple[bool, str]:
        """数据质量提示（不参与 calculate 判定）。默认界 ±35%（覆盖北交所 ±30%）。"""
        if returns is None:
            return False, "收益率数据为空"
        if len(returns) == 0:
            return False, "收益率数据长度为0"
        if len(returns) < self.MIN_SAMPLES:
            return False, f"收益率数据点不足（{len(returns)} < {self.MIN_SAMPLES}）"
        vals = [float(x) for x in returns]
        if any(math.isnan(v) for v in vals):
            return False, "收益率数据包含NaN"
        if any(math.isinf(v) for v in vals):
            return False, "收益率数据包含Inf"
        if any(v < -self.abs_return_cap for v in vals):
            return False, f"收益率数据包含异常小值（<-{self.abs_return_cap:.0%}）"
        if any(v > self.abs_return_cap for v in vals):
            return False, f"收益率数据包含异常大值（>{self.abs_return_cap:.0%}）"
        return True, ""

    def get_var_statistics(self, returns: Optional[Sequence[float]]) -> dict:
        if not returns or len(returns) == 0:
            return {}
        vals = sorted(float(x) for x in returns)
        n = len(vals)
        mean = sum(vals) / n
        var_pop = sum((v - mean) ** 2 for v in vals) / n
        return {
            "count": n,
            "mean": mean,
            "std": math.sqrt(var_pop),
            "min": vals[0],
            "max": vals[-1],
            "median": _percentile(vals, 50.0),
            "percentile_1": _percentile(vals, 1.0),
            "percentile_5": _percentile(vals, 5.0),
            "percentile_10": _percentile(vals, 10.0),
            "percentile_90": _percentile(vals, 90.0),
            "percentile_95": _percentile(vals, 95.0),
            "percentile_99": _percentile(vals, 99.0),
        }
