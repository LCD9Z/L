"""C2 A/B 入口（`scripts/run_c2_ab.py`）的守卫。

守两件事：
1. **变体定义不得偏离 `EXPERT_FILTER_C2_PREREG.md` §五** —— 一旦有人「顺手」把 D 与 E
   合并、或改掉 base 的口径，A/B 的 Δ 就不再对应预注册的判据，而**结果照样能出**。
2. **「排除持续性」必须真按交易日算** —— 首版把相邻日期**字符串**判等，
   集合去重后恒不相等，`streak_max` 永远输出 1：不报错、像结果、实则未测。

`test_streak_logic_detects_old_string_comparison` 是**反向验证**：
把旧写法复刻一遍，断言它给出 1，从而证明本守卫确实能分辨两种实现。
"""

from __future__ import annotations

import importlib.util
import sys
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "run_c2_ab", ROOT / "scripts" / "run_c2_ab.py")
assert _spec is not None and _spec.loader is not None
run_c2_ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_c2_ab)


# --------------------------------------------------------------------------
# 一、变体必须与 PREREG §五 一致
# --------------------------------------------------------------------------

def test_variants_match_prereg_list():
    """PREREG §五 的 5 个变体（base + D×2 + E×2），顺序与命名都要一致。"""
    assert [v[0] for v in run_c2_ab.VARIANTS] == [
        "base", "D_level", "D_ratio", "E_pe", "E_pb"]


def test_base_is_tail_exclusion_only():
    """PREREG：`base` = 尾部剔除（既有基线）。多开任何条件都会改掉 Δ 的基准。"""
    kwargs = dict(run_c2_ab.VARIANTS)["base"]
    assert kwargs == {"use_tail": True}, kwargs


def test_d_and_e_are_never_combined():
    """PREREG §五：D、E **各自独立跑**；`D+E` 须按 D 的结论另跑，不得混进本轮。"""
    bad = [label for label, kw in run_c2_ab.VARIANTS
           if kw.get("use_industry_crowding") and kw.get("use_valuation_cap")]
    assert bad == [], f"这些变体同时开了 D 与 E：{bad}"


def test_d_variants_cover_both_normalizations():
    """两个归一化口径都预注册、各自独立报告（PREREG §二「两种归一化口径」）。"""
    norms = {kw.get("ind_normalize") for label, kw in run_c2_ab.VARIANTS
             if kw.get("use_industry_crowding")}
    assert norms == {"level", "ratio"}, norms


def test_e_variants_cover_pe_and_pb():
    """`pe_ttm` 与 `pb` 两个指标都要跑（不得只挑先看起来好的那个）。"""
    metrics = {kw.get("valuation_metric") for label, kw in run_c2_ab.VARIANTS
               if kw.get("use_valuation_cap")}
    assert metrics == {"pe_ttm", "pb"}, metrics


# --------------------------------------------------------------------------
# 二、持续性口径（含反向验证）
# --------------------------------------------------------------------------

def test_streak_counts_consecutive_trading_days():
    """连续 3 个交易日 → 3；孤立一天 → 1。"""
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-08"]
    idx = {d: i for i, d in enumerate(days)}
    got = run_c2_ab._max_streaks(
        {"A": days[:3], "B": ["2024-01-08"]}, idx)
    assert sorted(got) == [1, 3], got


def test_streak_skips_non_trading_day_gaps():
    """跨周末/停牌不算连续：01-04 → 01-08 中间隔了交易日，段长为 1。"""
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    idx = {d: i for i, d in enumerate(days)}
    got = run_c2_ab._max_streaks({"A": ["2024-01-04", "2024-01-08"]}, idx)
    assert got == [1], got


def test_streak_logic_detects_old_string_comparison():
    """⚠️ 反向验证：旧写法（相邻日期字符串判等）必须给出错误答案 1。

    若哪天有人把实现改回去，本文件第一个断言（应为 3）会失败；
    而这里断言「旧写法 = 1」，确保两版确实不同 —— 守卫不是摆设。
    """
    days = ["2024-01-02", "2024-01-03", "2024-01-04"]
    idx = {d: i for i, d in enumerate(days)}
    assert run_c2_ab._max_streaks({"A": days}, idx) == [3]

    old = 1
    for a, b in pairwise(sorted(days)):
        old = old + 1 if b == a else 1
    assert old == 1, "旧写法的错误答案应为 1"


# --------------------------------------------------------------------------
# 三、分位工具
# --------------------------------------------------------------------------

def test_pct_handles_empty_and_single():
    assert run_c2_ab._pct([], 0.5) is None
    assert run_c2_ab._pct([5.0], 0.9) == 5.0


def test_pct_interpolates():
    assert run_c2_ab._pct([1, 2, 3], 0.5) == 2
    assert abs(run_c2_ab._pct([0, 10], 0.9) - 9.0) < 1e-9
