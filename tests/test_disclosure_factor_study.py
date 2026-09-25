# -*- coding: utf-8 -*-
"""守卫：H-D2 的判定逻辑必须**严格匹配事前登记**。

## 为什么需要

2026-09-25 首次执行 H-D2 时暴露了一个真实缺陷：判定逻辑内联在 `main()` 里，
把「两个子窗口 IC 符号相反」误判为**弱支持** —— 而事前登记
（`ALPHA_HYPOTHESIS_PREREG_HD2.md`）明确写着「符号相反 → 不成立」。

原登记表本身还有一处**自相矛盾**：弱支持写「子窗口符号不一致」，
不成立又写「两子窗口符号相反」—— 两句指同一情形。
已按**更严**方向勘误（符号相反一律归「不成立」），并把判定抽成纯函数
`decide_verdict` 由本文件锁住。

**这个缺陷的要害**：它会把一个「不成立」的结论误报成「弱支持」，
即**放宽**结论。事前登记的全部意义就是防止这种事，所以必须用断言守住。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_disclosure_factor_study import decide_verdict  # noqa: E402


def _sub(a: float, ta: float, b: float, tb: float):
    return [{"ic_mean": a, "t": ta}, {"ic_mean": b, "t": tb}]


# ---------------------------------------------------------------------------
# 强支持
# ---------------------------------------------------------------------------

def test_strong_when_all_conditions_met():
    assert decide_verdict(-0.01, -3.0, _sub(-0.012, -2.5, -0.008, -1.5), -0.002) == "强支持"


def test_not_strong_when_group_diff_positive():
    """组差与假设方向相反 → 不满足强支持（组差是强支持的必需条件之一）。"""
    assert decide_verdict(-0.01, -3.0, _sub(-0.012, -2.5, -0.008, -1.5), +0.002) != "强支持"


def test_not_strong_when_no_subwindow_reaches_t2():
    assert decide_verdict(-0.01, -3.0, _sub(-0.012, -1.5, -0.008, -1.0), -0.002) == "弱支持"


# ---------------------------------------------------------------------------
# 不成立 —— 本文件的核心守卫
# ---------------------------------------------------------------------------

def test_opposite_subwindows_is_not_established_not_weak():
    """⚠️ 核心回归：子窗口符号相反 → **不成立**，不得判「弱支持」。

    这正是 2026-09-25 的真实缺陷（实际结果 −0.0090 vs +0.0012）。
    """
    v = decide_verdict(-0.0034, -1.65, _sub(-0.0090, -2.85, +0.0012, +0.43), +0.00026)
    assert v == "不成立", f"符号相反必须判不成立，实际 {v}"


def test_opposite_subwindows_blocks_even_strong_ic():
    """即使全样本 IC 很负，只要子窗口反号，也不得判「强支持」。"""
    v = decide_verdict(-0.05, -5.0, _sub(-0.09, -4.0, +0.01, +0.5), -0.01)
    assert v == "不成立"


@pytest.mark.parametrize("mean_ic", [0.0, +0.001, +0.05])
def test_positive_ic_is_not_established(mean_ic):
    """IC ≥ 0 → 不成立（禁止事后翻转方向）。"""
    assert decide_verdict(mean_ic, +3.0, _sub(+0.01, +2.5, +0.02, +2.0), +0.01) == "不成立"


def test_none_ic_is_not_established():
    assert decide_verdict(None, None, [], None) == "不成立"


# ---------------------------------------------------------------------------
# 弱支持
# ---------------------------------------------------------------------------

def test_weak_when_same_sign_but_not_significant():
    assert decide_verdict(-0.002, -1.2, _sub(-0.003, -1.0, -0.001, -0.8), -0.0001) == "弱支持"


def test_weak_requires_same_sign_subwindows():
    """两子窗口同为负是「弱支持」的前提；一旦反号即降级为不成立。"""
    assert decide_verdict(-0.002, -1.2, _sub(-0.003, -1.0, -0.001, -0.8), -0.0001) == "弱支持"
    assert decide_verdict(-0.002, -1.2, _sub(-0.003, -1.0, +0.001, +0.3), -0.0001) == "不成立"


# ---------------------------------------------------------------------------
# H-D1 与「因子退化」门槛（2026-09-25 新增）
#
# H-D4 的教训：判定表未预设「因子退化」，于是一个**不具实质意义的判定**
# 被机械产出（原始 IC t=-9.02 而残差 IC t=+9.73 的剧烈符号反转，
# 根因是因子在 97.8% 的观测上取同一值）。
# H-D1 登记因此**前置**写入可用性门槛：非零占比中位 < 5% → 判「因子退化，不可检验」。
# 本组测试锁住该门槛与方向参数。
# ---------------------------------------------------------------------------

def test_degenerate_factor_gets_its_own_verdict():
    """⚠️ 核心守卫：退化时不得输出强/弱/不成立，必须单列「因子退化」。"""
    v = decide_verdict(+0.06, +9.0, _sub(+0.06, +7.0, +0.06, +6.0), +0.01,
                       direction="negative", degenerate=True)
    assert v == "因子退化", f"退化时必须单列，实际 {v}"


def test_degeneracy_gate_overrides_everything():
    """退化门槛优先于所有其他条件 —— 无论统计量多显著。"""
    for ic, t in ((+0.10, +20.0), (-0.10, -20.0), (0.0, 0.0)):
        assert decide_verdict(ic, t, _sub(ic, t, ic, t), ic,
                              direction="positive", degenerate=True) == "因子退化"


# ---- 方向参数：H-D1 为正，H-D2 为负 ----

def test_positive_direction_strong_support():
    assert decide_verdict(+0.01, +3.0, _sub(+0.012, +2.5, +0.008, +1.5), +0.002,
                          direction="positive") == "强支持"


def test_positive_direction_negative_ic_is_not_established():
    """H-D1 的实际结果：IC 为正但子窗口符号相反 → 不成立。"""
    v = decide_verdict(+0.00197, +1.00, _sub(+0.00353, +1.21, -0.00027, -0.10), -0.000447,
                       direction="positive")
    assert v == "不成立", f"子窗口符号相反必须判不成立，实际 {v}"


def test_direction_flag_flips_the_verdict():
    """同一个 IC，方向设定不同 → 判定不同。"""
    sub = _sub(-0.012, -2.5, -0.008, -1.5)
    assert decide_verdict(-0.01, -3.0, sub, -0.002, direction="negative") == "强支持"
    assert decide_verdict(-0.01, -3.0, sub, -0.002, direction="positive") == "不成立"


def test_positive_direction_requires_positive_group_diff():
    """强支持要求组差方向也正确。"""
    v = decide_verdict(+0.01, +3.0, _sub(+0.012, +2.5, +0.008, +1.5), -0.002,
                       direction="positive")
    assert v != "强支持"
