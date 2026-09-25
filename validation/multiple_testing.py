# -*- coding: utf-8 -*-
"""多重检验校正：把「跑了很多次」这件事算进显著性里。

## 为什么必须有这个模块

本项目累计报告了 30 项以上统计检验结果（10 个因子假设、1 个复合反转假设、
3 个尾部剔除变体、4 档集中度、4 组独立抽样、6 个滚动窗口、2 个 ADX 变体），
**全部按单次检验的 t / p 门槛判定，未做任何校正**。

这不是小瑕疵：在 m 次独立检验中，即使全部假设都为假，至少出现一个
p < 0.05 的概率是 ``1 - 0.95^m``。m = 30 时该概率为 **78.5%**。
换言之，**"跑出显著结果"几乎是必然的**，未校正的 t 值不能作为证据强度。

## 提供的两件工具

* :func:`deflated_sharpe_ratio` —— Bailey & López de Prado (2014) 的**紧缩夏普
  比率（DSR）**：在夏普比率上直接扣除「试验次数 N 带来的选择性偏差」
  与「收益非正态（偏度/峰度）带来的估计误差」。这是本项目的核心指标，
  因为全部结论都是「某策略的年化超额是否 > 0」。
* :func:`benjamini_hochberg` —— 对一批 p 值做 **FDR（错误发现率）**控制。
  比 Bonferroni 宽松、比不校正严格，适合"先筛一批候选、再逐个深挖"的研究流程。

另附 :func:`minimum_track_record_length`（MinTRL）：回答
「给定这个夏普比率与样本量，**还需要多少年数据**才能判定它真的 > 0」——
即统计功效问题。样本不够时它给出的数字会大到荒唐，这正是它存在的意义。

## 共同红线

* **样本不足返回 ``None``**，不返回一个"看起来还行"的近似值。
* **不替调用方做结论**。本模块只输出校正后的数值与拒绝与否，
  是否据此修改已发布结论由人决定。
* 纯标准库实现（``math`` / ``statistics``），不引入 scipy / numpy。

## 引用

* Bailey, D. H., & López de Prado, M. (2014). *The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting, and Non-Normality.*
  Journal of Portfolio Management, 40(5), 94-107.
* Benjamini, Y., & Hochberg, Y. (1995). *Controlling the False Discovery Rate.*
  JRSS-B, 57(1), 289-300.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Sequence

# Euler–Mascheroni 常数（期望最大夏普的公式中出现）
EULER_GAMMA = 0.5772156649015329

# Peter Acklam 有理逼近系数（正态分布反函数，精度约 1.15e-9）
_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01)
_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
      3.754408661907416e+00)
_P_LOW = 0.02425
_P_HIGH = 1.0 - _P_LOW


# ---------------------------------------------------------------------------
# 分布函数（纯标准库）
# ---------------------------------------------------------------------------

def normal_cdf(x: float) -> float:
    """标准正态 CDF。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_ppf(p: Optional[float]) -> Optional[float]:
    """标准正态分位数（Acklam 逼近）。

    ``p`` 必须落在开区间 (0, 1)；``None`` 或端点返回 ``None``
    （端点对应 ±∞，不可用于算术）。
    """
    if p is None or p <= 0.0 or p >= 1.0:
        return None
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) \
            / ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    if p <= _P_HIGH:
        q = p - 0.5
        r = q * q
        return (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q \
            / (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) \
        / ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)


# ---------------------------------------------------------------------------
# 收益序列的矩
# ---------------------------------------------------------------------------

def _clean(values: Sequence[Any]) -> List[float]:
    out = []
    for v in values:
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if x == x and math.isfinite(x):
            out.append(x)
    return out


def sharpe_moments(returns: Sequence[Any]) -> Optional[Dict[str, float]]:
    """非年化的夏普比率与高阶矩。

    返回 ``{n, mean, sd, sr, skew, kurt}``：

    * ``sr``   —— **非年化**（单期）夏普比率 ``mean / sd``；DSR 公式要求单期口径，
      年化会把它放大 sqrt(252) 倍并使判定失真。
    * ``skew`` —— 偏度（正态为 0）。
    * ``kurt`` —— **非超额**峰度（正态为 3，不是 0）。

    样本不足（< 4 个观测）或标准差为 0 时返回 ``None``。
    """
    vals = _clean(returns)
    n = len(vals)
    if n < 4:
        return None
    mean = statistics.mean(vals)
    sd = statistics.pstdev(vals)
    if sd <= 0:
        return None
    m2 = sum((v - mean) ** 2 for v in vals) / n
    m3 = sum((v - mean) ** 3 for v in vals) / n
    m4 = sum((v - mean) ** 4 for v in vals) / n
    return {
        'n': float(n),
        'mean': mean,
        'sd': sd,
        'sr': mean / sd,
        'skew': m3 / (m2 ** 1.5) if m2 > 0 else 0.0,
        'kurt': m4 / (m2 ** 2) if m2 > 0 else 3.0,
    }


def _sr_variance_term(sr: float, skew: float, kurt: float) -> float:
    """DSR/PSR 分母中的方差项 ``1 - γ3·SR + ((γ4-1)/4)·SR²``。

    该项恒为正（Hansen 界），但极端矩下可能因数值原因 <= 0，此时返回 0 表示不可用。
    """
    v = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    return v if v > 0 else 0.0


# ---------------------------------------------------------------------------
# 概率夏普比率 / 紧缩夏普比率
# ---------------------------------------------------------------------------

def expected_max_sharpe(n_trials: int, sr_variance: float) -> Optional[float]:
    """N 次试验中**最大**夏普比率的期望值（选择性偏差的基准线）。

    ``E[max SR] = sqrt(Var[SR_n]) · [(1-γ)·Z⁻¹(1 - 1/N) + γ·Z⁻¹(1 - 1/(N·e))]``

    * ``n_trials <= 1`` → 返回 ``0.0``（没有选择，就不存在选择偏差）。
    * ``sr_variance <= 0`` → 返回 ``0.0``（各次试验夏普无离散度，同样无选择偏差）。
    * ``sr_variance`` 必须是**各次试验夏普比率的方差**；无法估计时调用方
      应传 ``None`` 语义的 0，并在结论中声明"未校正选择偏差"。
    """
    if n_trials is None or n_trials <= 1:
        return 0.0
    if sr_variance is None or sr_variance <= 0:
        return 0.0
    z1 = normal_ppf(1.0 - 1.0 / n_trials)
    z2 = normal_ppf(1.0 - 1.0 / (n_trials * math.e))
    if z1 is None or z2 is None:
        return None
    return math.sqrt(sr_variance) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)


def probabilistic_sharpe_ratio(returns: Sequence[Any],
                               benchmark_sr: float = 0.0) -> Optional[Dict[str, Any]]:
    """PSR：在**不考虑选择偏差**时，真实夏普 > ``benchmark_sr`` 的概率。

    即"这一次回测的夏普比率，有多少把握是真的为正"。
    """
    m = sharpe_moments(returns)
    if m is None:
        return None
    var_term = _sr_variance_term(m['sr'], m['skew'], m['kurt'])
    if var_term <= 0:
        return None
    z = (m['sr'] - benchmark_sr) * math.sqrt(m['n'] - 1.0) / math.sqrt(var_term)
    return {
        'psr': normal_cdf(z),
        'sr': m['sr'],
        'n': m['n'],
        'skew': m['skew'],
        'kurt': m['kurt'],
        'benchmark_sr': benchmark_sr,
        'z': z,
    }


def deflated_sharpe_ratio(returns: Sequence[Any],
                          n_trials: int,
                          sr_variance: float,
                          benchmark_sr: float = 0.0) -> Optional[Dict[str, Any]]:
    """DSR：扣除**选择偏差**与**非正态**之后的夏普比率显著性。

    与 PSR 的唯一差别是把比较基准从 ``benchmark_sr`` 换成
    ``max(benchmark_sr, E[max SR])`` —— 即"考虑到我试了 N 次，
    我至少该跑赢多少次试验里的最好那个"。

    返回 ``{dsr, psr, expected_max_sr, sr, n, n_trials, skew, kurt, ...}``。
    样本不足或方差项非正时返回 ``None``。

    **判读**：``dsr`` 是"真实夏普 > 选择偏差基准"的概率。
    ``dsr < 0.95`` 即该结果在多重检验下**不构成证据**——这正是本项目
    30+ 项未校正检验需要重新评估的原因。
    """
    m = sharpe_moments(returns)
    if m is None:
        return None
    e_max = expected_max_sharpe(n_trials, sr_variance)
    if e_max is None:
        return None
    var_term = _sr_variance_term(m['sr'], m['skew'], m['kurt'])
    if var_term <= 0:
        return None
    threshold = max(benchmark_sr, e_max)
    z = (m['sr'] - threshold) * math.sqrt(m['n'] - 1.0) / math.sqrt(var_term)
    return {
        'dsr': normal_cdf(z),
        'psr': normal_cdf((m['sr'] - benchmark_sr) * math.sqrt(m['n'] - 1.0) / math.sqrt(var_term)),
        'expected_max_sr': e_max,
        'threshold_sr': threshold,
        'sr': m['sr'],
        'n': m['n'],
        'n_trials': n_trials,
        'sr_variance': sr_variance,
        'skew': m['skew'],
        'kurt': m['kurt'],
        'z': z,
    }


def minimum_track_record_length(returns: Sequence[Any],
                                benchmark_sr: float = 0.0,
                                alpha: float = 0.05) -> Optional[Dict[str, Any]]:
    """MinTRL：判定「真实夏普 > ``benchmark_sr``」所需的最小观测数。

    ``MinTRL = 1 + [1 - γ3·SR + ((γ4-1)/4)·SR²] · (Z_{1-α} / (SR - SR*))²``

    * 观测数不足时返回 ``{required: inf, sufficient: False, ...}`` ——
      **不返回一个"勉强够用"的数字**。
    * 同时给出按 252 交易日折算的年数，便于判断"当前数据够不够下结论"。
    """
    m = sharpe_moments(returns)
    if m is None:
        return None
    z = normal_ppf(1.0 - alpha)
    if z is None:
        return None
    var_term = _sr_variance_term(m['sr'], m['skew'], m['kurt'])
    if var_term <= 0:
        return None
    excess = m['sr'] - benchmark_sr
    if excess <= 0:
        return {
            'required': None, 'required_years': None, 'sufficient': False,
            'available': m['n'], 'sr': m['sr'], 'benchmark_sr': benchmark_sr,
            'alpha': alpha,
            'reason': 'observed_sr_not_above_benchmark',
        }
    required = 1.0 + var_term * (z / excess) ** 2
    return {
        'required': required,
        'required_years': required / 252.0,
        'sufficient': m['n'] >= required,
        'available': m['n'],
        'sr': m['sr'],
        'benchmark_sr': benchmark_sr,
        'alpha': alpha,
    }


# ---------------------------------------------------------------------------
# p 值族的多重检验校正
# ---------------------------------------------------------------------------

def _as_pvalues(pvalues: Sequence[Any]) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for p in pvalues:
        try:
            x = float(p)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(x if (x == x and 0.0 <= x <= 1.0) else None)
    return out


def benjamini_hochberg(pvalues: Sequence[Any], alpha: float = 0.05) -> Dict[str, Any]:
    """Benjamini-Hochberg 逐步法（FDR 控制）。

    给定 m 个 p 值，取**最大的** k 使得 ``p_(k) <= (k/m)·alpha``，
    拒绝秩次 <= k 的全部假设。调整后 p 值为
    ``p_adj_(i) = min_{j >= i} ( m·p_(j) / j )``（并施加单调性、截断到 1）。

    ``None`` / 非法的 p 值视为**未检验**，不进入 m，结果中原样返回 ``None``。

    返回 ``{method, alpha, m, k, threshold, results}``，``results`` 与输入同序。
    """
    ps = _as_pvalues(pvalues)
    idx = [(p, i) for i, p in enumerate(ps) if p is not None]
    m = len(idx)
    results: List[Optional[Dict[str, Any]]] = [None] * len(ps)
    if m == 0:
        return {'method': 'benjamini_hochberg', 'alpha': alpha, 'm': 0, 'k': 0,
                'threshold': None, 'results': results}
    idx.sort(key=lambda t: t[0])
    adjusted = [0.0] * m
    running = 1.0
    for j in range(m - 1, -1, -1):
        p, _ = idx[j]
        val = p * m / (j + 1)
        running = min(running, val)
        adjusted[j] = min(1.0, running)
    k = 0
    threshold: Optional[float] = None
    for j in range(m):
        if idx[j][0] <= (j + 1) / m * alpha:
            k = j + 1
            threshold = (j + 1) / m * alpha
    for j, (p, orig) in enumerate(idx):
        results[orig] = {
            'index': orig,
            'p': p,
            'p_adjusted': adjusted[j],
            'rank': j + 1,
            'rejected': j < k,
        }
    return {'method': 'benjamini_hochberg', 'alpha': alpha, 'm': m, 'k': k,
            'threshold': threshold, 'results': results}


def bonferroni(pvalues: Sequence[Any], alpha: float = 0.05) -> Dict[str, Any]:
    """Bonferroni 校正（FWER 控制）：``p_adj = min(1, m·p)``，拒绝条件 ``p <= alpha/m``。

    作为 BH-FDR 的对照给出——它更保守，在 m 较大时几乎不会拒绝任何假设。
    """
    ps = _as_pvalues(pvalues)
    idx = [(p, i) for i, p in enumerate(ps) if p is not None]
    m = len(idx)
    results: List[Optional[Dict[str, Any]]] = [None] * len(ps)
    if m == 0:
        return {'method': 'bonferroni', 'alpha': alpha, 'm': 0, 'k': 0,
                'threshold': None, 'results': results}
    cutoff = alpha / m
    k = 0
    for p, orig in sorted(idx, key=lambda t: t[0]):
        rejected = p <= cutoff
        if rejected:
            k += 1
        results[orig] = {
            'index': orig,
            'p': p,
            'p_adjusted': min(1.0, p * m),
            'rejected': rejected,
        }
    return {'method': 'bonferroni', 'alpha': alpha, 'm': m, 'k': k,
            'threshold': cutoff, 'results': results}


def family_wise_error_rate(m: int) -> Optional[float]:
    """m 次**独立**检验中至少出现一个 p < 0.05 的概率 ``1 - 0.95^m``。

    用来向读者说明"未校正会怎样"：m = 30 时该值约 78.5%。
    """
    if m is None or m < 0:
        return None
    return 1.0 - 0.95 ** m
