# -*- coding: utf-8 -*-
"""年化超额口径的一致性守卫。

## 背景（一次误诊的纠正）

`CALIBRATION_DISCREPANCY_REPORT.md` §2.3 曾记载「尾部剔除用算术年化、
滚动评估用 `analyse_alpha` 的分析估计 —— 这是两个不同的指标」。
2026-09-15 逐行核实后确认**该记载有误**：

- `run_tail_exclusion_study` 等 4 个脚本：``mean(日超额) × 252 × 100``
- `alpha_survival_lab.analyse_alpha`：``mean(超额) × 252``

**两者是同一个公式**（仅差 ×100 的单位换算），实测差值恒为 0.0。
真正的口径分歧在别处：``scripts/run_contrarian_portfolio.py``（A/B 组合层面）
用的是**几何（复合）年化** ``(期末/期初)^(1/年) − 1``。

## 为什么不把它们"统一"成一种

两种口径回答的是**不同问题**，各自在其语境下成立：

- 算术 —— 单期期望的线性外推，用于比较因子/横截面排序强度；
- 几何 —— 实际复利结果（含波动拖累），用于陈述"策略 CAGR 跑赢基准多少"。

强行合并会让 A/B 报告无法回答"是否跑赢指数"。正确做法是
**单一口径来源 + 显式标注**，并由本文件把三条性质固化为断言。
"""
from __future__ import annotations

import re
import statistics
from pathlib import Path

from alpha.alpha_survival_lab import analyse_alpha, annualized_excess_arithmetic

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

#: 走**算术**年化口径的研究脚本（与 A/B 的几何口径相对）
ARITHMETIC_STUDY_SCRIPTS = (
    "run_tail_exclusion_study.py",
    "run_concentration_study.py",
    "run_sampling_sensitivity_study.py",
    "run_universe_replication.py",
)


def _sample_series(n: int = 300):
    """构造带波动的策略/基准序列，便于复算。

    默认 300 个交易日 —— 须 ≥ `analyse_alpha` 的 `min_periods=252`，
    否则会走 INCONCLUSIVE 分支而不返回年化估计。
    """
    dates = [f"d{i}" for i in range(n)]
    strat = {d: 0.001 + 0.002 * ((i % 7) - 3) for i, d in enumerate(dates)}
    bench = dict.fromkeys(dates, 0.0008)
    return strat, bench


def test_helper_reproduces_legacy_inline_expression_bit_for_bit():
    """统一函数必须与各脚本此前的内联写法**逐位相同**。

    这条证明 2026-09-15 的提取式重构**没有改变任何已发布数字** ——
    4 个研究脚本的输出应与重构前完全一致。
    """
    strat, bench = _sample_series()
    common = sorted(set(strat) & set(bench))

    legacy = (statistics.mean(strat[d] - bench[d] for d in common) * 252 * 100
              if common else 0.0)
    new = annualized_excess_arithmetic(
        (strat[d] - bench[d] for d in common), as_percent=True)

    assert new == legacy, f"重构改变了数字：legacy={legacy!r} new={new!r}"


def test_analyse_alpha_uses_the_same_arithmetic_convention():
    """`analyse_alpha` 的年化超额必须与统一函数一致。

    这保证「因子/滚动类报告」与「A/B 之外的其他报告」的数字可直接互相印证。
    """
    strat, bench = _sample_series()
    common = sorted(set(strat) & set(bench))

    report = analyse_alpha(strat, bench, min_periods=252)
    expected = annualized_excess_arithmetic([strat[d] - bench[d] for d in common])

    assert report["annualized_excess_estimate"] == expected


def test_helper_returns_zero_for_empty_input():
    """空输入返回 0.0 —— 与既有调用点 `if common else 0.0` 语义一致。

    注意这是「无对齐样本」与「超额恰好为 0」的混同，属**已知取舍**：
    沿用既有行为以免改动已发布结果，调用方须自行确保样本非空。
    """
    assert annualized_excess_arithmetic([]) == 0.0
    assert annualized_excess_arithmetic(iter([])) == 0.0


def test_arithmetic_and_geometric_diverge_under_volatility():
    """算术年化 ≥ 几何年化，波动越大差距越大 —— 证明两种口径**不可互换**。

    取 +3% / −3% 交替 252 天：日均超额恰好为 0（算术年化 = 0），
    但复利结果为负（波动拖累），故几何年化 < 0。
    这正是 A/B 报告（几何）与其他报告（算术）数字不可直接比较的原因。
    """
    rets = [0.03, -0.03] * 126  # 252 个交易日，日均为 0

    arithmetic = annualized_excess_arithmetic(rets)

    equity = 1.0
    for r in rets:
        equity *= 1.0 + r
    years = len(rets) / 252
    geometric = equity ** (1 / years) - 1

    assert arithmetic == 0.0
    assert geometric < 0, "波动拖累未体现，用例构造有误"
    assert arithmetic > geometric


def test_study_scripts_do_not_reinline_the_annualization():
    """4 个研究脚本不得再内联 `mean(日超额) * 252 * 100`。

    此前同一公式在 4 个文件里各写一遍 —— 4 个分叉点。
    本守卫把「单一口径来源」固化下来，避免将来改一处漏三处。
    """
    offenders = []
    for name in ARITHMETIC_STUDY_SCRIPTS:
        text = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
        if "annualized_excess_arithmetic" not in text:
            offenders.append(f"{name}: 未使用统一函数 annualized_excess_arithmetic")
        if re.search(r"\*\s*252\s*\*\s*100", text):
            offenders.append(f"{name}: 仍存在内联年化 `* 252 * 100`")

    assert offenders == [], "年化口径未单一化:\n  - " + "\n  - ".join(offenders)
