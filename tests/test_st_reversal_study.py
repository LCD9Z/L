# -*- coding: utf-8 -*-
"""守卫：H-D3 的判定逻辑必须**严格匹配事前登记**。

## 为什么需要

H-D2 的执行暴露过一个真实缺陷：判定逻辑内联在 `main()` 里，
把「子窗口符号相反」误判为「弱支持」——**方向是放宽结论**。
H-D3 因此一开始就把判定抽成纯函数 `decide_verdict` 并在此锁住。

## 本文件重点锁住两件事

1. **可实现性未通过 → 不得判「强支持」**（登记 §5.1 的硬条件）。
   ST 股票的"超额"极易不可实现（机构禁买、流动性差、涨跌停受限），
   若不把该门槛写进判定，就会把一个不可实现的价差报成 Alpha。
2. **Δ ≤ 0 → 不成立**，不得表述为「反向有效」（禁止事后翻转方向）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_st_reversal_study import decide_verdict  # noqa: E402


def _sub(a: float, ta: float, b: float, tb: float):
    return [{"delta": a, "t": ta}, {"delta": b, "t": tb}]


# ---------------------------------------------------------------------------
# 强支持 —— 必须同时满足「显著 + 子窗口同号 + 可实现」
# ---------------------------------------------------------------------------

def test_strong_when_all_conditions_and_realizable():
    assert decide_verdict(+0.005, 3.0, _sub(0.006, 2.5, 0.004, 1.5), True) == "强支持"


def test_not_strong_when_not_realizable():
    """⚠️ 核心守卫：方向为正、统计显著，但**可实现性未通过** → 只能弱支持。

    这正是登记 §5.1 的设计意图：不可实现的价差不等于 Alpha。
    """
    v = decide_verdict(+0.005, 3.0, _sub(0.006, 2.5, 0.004, 1.5), False)
    assert v == "弱支持", f"不可实现时不得判强支持，实际 {v}"


def test_not_strong_when_no_subwindow_significant():
    assert decide_verdict(+0.005, 3.0, _sub(0.006, 1.5, 0.004, 1.0), True) == "弱支持"


def test_not_strong_when_subwindows_opposite():
    assert decide_verdict(+0.005, 3.0, _sub(0.006, 2.5, -0.004, -1.0), True) == "不成立"


# ---------------------------------------------------------------------------
# 不成立
# ---------------------------------------------------------------------------

def test_negative_delta_is_not_established():
    """H-D3 的实际结果：Δ = −0.2192%，两子窗口同号为负。"""
    v = decide_verdict(-0.002192, -1.65, _sub(-0.002230, -1.20, -0.001894, -0.96), False)
    assert v == "不成立"


def test_opposite_subwindows_is_not_established():
    assert decide_verdict(+0.005, 3.0, _sub(+0.006, 2.5, -0.004, -1.0), True) == "不成立"


def test_zero_delta_is_not_established():
    assert decide_verdict(0.0, 0.0, _sub(0.0, 0.0, 0.0, 0.0), True) == "不成立"


def test_none_delta_is_not_established():
    assert decide_verdict(None, None, [], False) == "不成立"


# ---------------------------------------------------------------------------
# 弱支持
# ---------------------------------------------------------------------------

def test_weak_when_positive_but_not_significant():
    assert decide_verdict(+0.001, 1.2, _sub(0.001, 1.0, 0.001, 0.8), True) == "弱支持"


def test_realizable_flag_does_not_affect_non_strong_verdicts():
    """可实现性只在「是否够得上强支持」上起作用，不改变不成立的判定。"""
    assert decide_verdict(-0.002, -3.0, _sub(-0.002, -2.5, -0.002, -1.5), True) == "不成立"
    assert decide_verdict(-0.002, -3.0, _sub(-0.002, -2.5, -0.002, -1.5), False) == "不成立"


@pytest.mark.parametrize("realizable", [True, False])
def test_strong_requires_both_subwindows_positive(realizable):
    """子窗口只要有一个 ≤ 0，就够不上强支持。"""
    assert decide_verdict(+0.005, 3.0, _sub(+0.006, 2.5, 0.0, 0.0), realizable) != "强支持"
