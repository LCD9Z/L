# -*- coding: utf-8 -*-
"""Phase 21: conservative Alpha Survival Lab.

This module deliberately separates *evidence* from *claims*.  It can analyse
aligned out-of-sample strategy/benchmark return series, but returns
INCONCLUSIVE when data are insufficient rather than manufacturing an Alpha
verdict.
"""
import math
import random
import statistics
from typing import Any, Dict, List


def _f(x):
    return float(x)


def align_returns(strategy, benchmark):
    """Accept mappings {date:return} or aligned sequences; return common pairs."""
    if isinstance(strategy, dict) and isinstance(benchmark, dict):
        dates = sorted(set(strategy) & set(benchmark))
        return [(d, _f(strategy[d]), _f(benchmark[d])) for d in dates]
    if len(strategy) != len(benchmark):
        raise ValueError('strategy and benchmark sequences must have equal length')
    return [(str(i), _f(s), _f(b)) for i, (s, b) in enumerate(zip(strategy, benchmark, strict=True))]


def _mean(xs):
    return statistics.mean(xs) if xs else 0.0


def annualized_excess_arithmetic(excess_returns, annualization=252, as_percent=False):
    """**算术**年化超额 —— 本项目因子/滚动类研究的统一年化口径。

    定义：``mean(日超额) × annualization``（默认 252 个交易日）。

    与**几何（复合）年化**的区别（两者回答的是不同问题，**不要互相替代**）：

    ==========  ================================  ==============================
    口径        公式                              适用场景
    ==========  ================================  ==============================
    算术         ``mean(日超额) × 252``            单期期望的线性外推；比较因子
                                                   /横截面排序强度
    几何         ``(期末/期初)^(1/年) − 1``        实际复利结果（含波动拖累
                                                   variance drag）；陈述"跑赢
                                                   基准多少个百分点"
    ==========  ================================  ==============================

    有波动的策略上必然 **算术 ≥ 几何**，故两份报告若各用一种口径，
    其数字**不可直接比较** —— 引用时必须写明用的是哪一种。

    本项目分工（2026-09-15 核实）：
    - 算术：本函数。``analyse_alpha`` 与 4 个研究脚本
      （tail_exclusion / concentration / sampling_sensitivity /
      universe_replication）均走此口径。
    - 几何：``scripts/run_contrarian_portfolio.py``（A/B 组合层面对照），
      因其要陈述"策略 CAGR 相对沪深 300 CAGR 的超额"。

    空输入返回 ``0.0``（与既有调用点 ``if common else 0.0`` 的语义一致）。
    注意这会把"无对齐样本"与"超额恰好为 0"混同 —— 调用方须自行确保样本非空。
    """
    vals = [_f(x) for x in excess_returns]
    if not vals:
        return 0.0
    annual = statistics.mean(vals) * annualization
    return annual * 100.0 if as_percent else annual


def _std(xs):
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def _t_stat(xs):
    if len(xs) < 2:
        return None
    sd = _std(xs)
    return _mean(xs) / (sd / math.sqrt(len(xs))) if sd else None


def _normal_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _two_sided_pvalue_from_t(t):
    # Normal approximation: deliberately conservative for the default evidence gate.
    return None if t is None else max(0.0, min(1.0, 2.0 * (1.0 - _normal_cdf(abs(t)))))


def block_bootstrap_mean_ci(values, reps=2000, block_size=5, seed=20260905, alpha=0.05):
    vals = [_f(x) for x in values]
    if len(vals) < 2:
        return None
    n = len(vals)
    block_size = max(1, min(int(block_size), n))
    rng = random.Random(seed)
    means = []
    for _ in range(int(reps)):
        sample: List[int] = []
        while len(sample) < n:
            start = rng.randrange(n)
            for j in range(block_size):
                sample.append(vals[(start + j) % n])
                if len(sample) >= n:
                    break
        means.append(_mean(sample))
    means.sort()
    lo_i = max(0, int((alpha / 2) * (len(means) - 1)))
    hi_i = min(len(means) - 1, int((1 - alpha / 2) * (len(means) - 1)))
    return {'mean': _mean(vals), 'lower': means[lo_i], 'upper': means[hi_i], 'reps': int(reps), 'block_size': block_size}


def permutation_pvalue(values, reps=5000, seed=20260905):
    """Sign-flip randomization test for mean excess return > 0."""
    vals = [_f(x) for x in values]
    if len(vals) < 2:
        return None
    observed = _mean(vals)
    rng = random.Random(seed)
    ge = 0
    for _ in range(int(reps)):
        m = _mean([v if rng.random() < 0.5 else -v for v in vals])
        if m >= observed:
            ge += 1
    return (ge + 1) / (int(reps) + 1)


def analyse_alpha(strategy, benchmark, annualization=252, min_periods=252,
                  bootstrap_reps=2000, permutation_reps=5000, seed=20260905):
    rows = align_returns(strategy, benchmark)
    excess = [s - b for _, s, b in rows]
    n = len(excess)
    if n < min_periods:
        return {
            'verdict': 'INCONCLUSIVE',
            'reason': 'insufficient_out_of_sample_periods',
            'periods': n,
            'required_min_periods': min_periods,
        }
    mean = _mean(excess)
    ci = block_bootstrap_mean_ci(excess, reps=bootstrap_reps, seed=seed)
    t = _t_stat(excess)
    normal_p = _two_sided_pvalue_from_t(t)
    perm_p = permutation_pvalue(excess, reps=permutation_reps, seed=seed)
    annual_excess = annualized_excess_arithmetic(excess, annualization)
    positive = mean > 0
    ci_positive = ci is not None and ci['lower'] > 0
    significant = normal_p is not None and normal_p < 0.05 and perm_p is not None and perm_p < 0.05
    verdict = 'SUPPORTED' if positive and ci_positive and significant else 'NOT_SUPPORTED'
    return {
        'verdict': verdict,
        'periods': n,
        'mean_excess_daily': mean,
        'annualized_excess_estimate': annual_excess,
        't_stat_normal_approx': t,
        'normal_approx_pvalue': normal_p,
        'sign_flip_pvalue': perm_p,
        'bootstrap_mean_ci': ci,
        'conditions': {
            'positive_mean': positive,
            'bootstrap_ci_entirely_positive': ci_positive,
            'both_significance_tests_pass': significant,
        },
        'warning': 'Statistical support is not a guarantee of future profitability.',
    }


def alpha_survival_gate(experiments, required_benchmarks=None):
    """Require independent OOS experiments and benchmark diversity.

    experiments: iterable of dicts with keys name, strategy_returns,
    benchmark_returns and optional benchmark_name.
    """
    reports: List[Dict[str, Any]] = []
    seen = set()
    for exp in experiments:
        name = exp.get('name', f'experiment_{len(reports)+1}')
        bench_name = exp.get('benchmark_name', 'default')
        seen.add(bench_name)
        report = analyse_alpha(exp['strategy_returns'], exp['benchmark_returns'],
                               min_periods=exp.get('min_periods', 252),
                               bootstrap_reps=exp.get('bootstrap_reps', 2000),
                               permutation_reps=exp.get('permutation_reps', 5000),
                               seed=exp.get('seed', 20260905))
        report['name'] = name
        report['benchmark_name'] = bench_name
        reports.append(report)
    required = set(required_benchmarks or [])
    missing = sorted(required - seen)
    supported = [r for r in reports if r['verdict'] == 'SUPPORTED']
    if not reports:
        verdict, reason = 'INCONCLUSIVE', 'no_experiments'
    elif missing:
        verdict, reason = 'INCONCLUSIVE', 'missing_required_benchmarks'
    elif len(supported) != len(reports):
        verdict, reason = 'NOT_ESTABLISHED', 'one_or_more_alpha_tests_failed_or_inconclusive'
    else:
        verdict, reason = 'ALPHA_SURVIVES_CURRENT_TESTS', 'all_predeclared_tests_supported'
    return {'verdict': verdict, 'reason': reason, 'reports': reports, 'missing_benchmarks': missing,
            'disclaimer': 'This gate establishes evidence under supplied data and predeclared tests only; it does not predict future returns.'}
