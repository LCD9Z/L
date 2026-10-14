# -*- coding: utf-8 -*-
"""`scripts/run_tdx_universe_ic._factors_at` 与生产口径的一致性对照测试。

## 为什么有这个测试

2026-10-07 发现：`run_tdx_universe_ic.py:47` 的注释声称「与
`five_factor.compute_factors` **逐字一致**」，但**实测不成立** ——
amihud 有两处偏差：

| 项 | 原 IC 实现 | 生产 `compute_factors` |
|---|---|---|
| 取值分母 | `sum(amihud)/len(amihud)`（随停牌数变） | `sum(amihud[-20:])/20.0`（固定 20） |
| 样本门槛 | `len < 15` | `len < 20` |

实测影响：无停牌 0.00%；窗口内 1 天 `amount=0` 时 0.26%。

已修正。本测试**锁死**「同输入 → 同输出」，防止将来任一侧被改坏。

## 口径约定

生产 `compute_factors(bars)` 接收**窗口切片** `bars[i-21:i+1]`（22 根）；
`_factors_at(closes, amounts, i)` 接收**完整数组 + 下标**。
两者在无门槛口径下必须给出相同结果，故对比时
`_factors_at(..., liq_min=None)` 对 `compute_factors(...)`。
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from tdx_native import day_reader, five_factor  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "ic_mod", os.path.join(ROOT, "scripts", "run_tdx_universe_ic.py"))
assert _spec is not None and _spec.loader is not None
ic_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic_mod)

FACTOR_KEYS = ("ret20", "vol20", "amihud20", "loga20", "maxret20")
FIELDS = ("date", "open", "high", "low", "close", "amount", "volume")


def _mkbars(n: int, pause_at=None, amp: float = 0.03, amount: float = 3e8):
    """合成 bar 序列。pause_at 中的下标 amount 置 0（模拟停牌）。"""
    out = []
    for k in range(n):
        px = 20.0 * (1.0 + amp * math.sin(k / 5.0))
        amt = 0.0 if (pause_at and k in pause_at) else amount
        out.append({"date": 20200101 + k, "open": px, "high": px, "low": px,
                    "close": px, "amount": amt, "volume": 1e6})
    return out


def _compare(bars, i, tol=1e-12):
    """分层对比生产与 IC 实现，返回差异字典（空 = 完全一致）。

    **为什么要分层**：生产 `compute_factors` 内置 `liq20 >= 1e8` 门槛，
    而 IC 的默认 `liq_min=None` 是**故意不过滤**（跨年代实验要靠截面筛选）。
    所以：

    - **门槛层**：用 IC(`liq_min=1e8`) 对比生产的 None/ok 判定
    - **因子值层**：仅在两者都通过时，对比 IC(`liq_min=None`) 的因子值

    实测教训：曾用 IC(`liq_min=None`) 直接对比生产，在 2003 年的中信证券
    （liq20=4.28e7 不过门槛）上误报「不一致」——那是预期差异，不是缺陷。
    """
    closes = [b["close"] for b in bars]
    amounts = [b["amount"] for b in bars]
    prod = five_factor.compute_factors(bars[max(0, i - 79):i + 1])
    ic_gated = ic_mod._factors_at(closes, amounts, i, liq_min=1e8)
    if (prod is None) != (ic_gated is None):
        return {"gate": (prod is None, ic_gated is None)}
    if prod is None:
        return {}                       # 双双拒绝 → 一致
    ic = ic_mod._factors_at(closes, amounts, i, liq_min=None)
    assert ic is not None, "门槛通过时无门槛口径也应通过"
    diff = {}
    for k in FACTOR_KEYS:
        a, b = prod.get(k), ic.get(k)
        if a is None or b is None:
            if a is not b:
                diff[k] = (a, b)
            continue
        if not math.isfinite(a) and not math.isfinite(b):
            continue
        if abs(a - b) > tol:
            diff[k] = (a, b)
    return diff


# ---------------------------------------------------------------------------
# 1. 合成场景：无停牌 + 各类停牌位置
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,pause", [
    ("无停牌", None),
    ("信号日停牌", {290}),
    ("前 2 日停牌", {289, 290}),
    ("窗口中部停牌", {280}),
    ("窗口最早停牌", {270}),
    ("连续 5 日停牌", {285, 286, 287, 288, 289}),
])
def test_consistency_synthetic(name, pause):
    """合成场景下两实现必须逐位一致（含各类停牌位置）。"""
    bars = _mkbars(300, pause)
    d = _compare(bars, 290)
    assert d == {}, f"[{name}] 生产与 IC 输出不一致：{d}"


def test_consistency_multi_pause_days():
    """多个分散停牌日也必须一致（这是原实现的偏差来源）。"""
    bars = _mkbars(300, {250, 260, 270, 275, 280})
    d = _compare(bars, 290)
    assert d == {}, f"多处停牌下不一致：{d}"


def test_consistency_recent_all_suspended():
    """最近 26 天全停牌 → liq20=0，两者判定必须一致（`_compare` 已含门槛层）。"""
    bars = _mkbars(300, set(range(265, 291)))
    d = _compare(bars, 290)
    assert d == {}, f"近期全停牌场景判定不一致：{d}"


def test_consistency_exactly_20_valid_days():
    """窗口内恰好 20 个有效日 → 两者都应通过（amihud 门槛边界）。

    `window=80` → amihud 候选 p=212..290（79 个）。
    停 59 天（212..270）→ 恰 20 个有效。
    """
    bars = _mkbars(300, set(range(212, 271)))
    d = _compare(bars, 290)
    assert d == {}, f"恰 20 个有效日下不一致：{d}"
    # 确认边界确实被踩到（否则断言无意义）
    amounts = [b["amount"] for b in bars]
    valid = [p for p in range(212, 291) if amounts[p] > 0]
    assert len(valid) == 20, f"夹具设计有误：有效日 {len(valid)} 个，应为 20"


def test_consistency_19_valid_days_rejected():
    """窗口内只有 19 个有效日 → 两者都应返回 None。

    原 IC 门槛是 15，会误通过；修正后为 20，与生产一致。
    """
    bars = _mkbars(300, set(range(212, 272)))      # 停 60 天 → 剩 19 个
    amounts = [b["amount"] for b in bars]
    valid = [p for p in range(212, 291) if amounts[p] > 0]
    assert len(valid) == 19, f"夹具设计有误：有效日 {len(valid)} 个，应为 19"
    closes = [b["close"] for b in bars]
    prod = five_factor.compute_factors(bars[211:291])
    ic = ic_mod._factors_at(closes, amounts, 290, liq_min=None)
    assert prod is None, "生产应因 amihud 不足 20 返回 None"
    assert ic is None, "修正后的 IC 实现也应返回 None（原门槛 15 会误通过）"


# ---------------------------------------------------------------------------
# 2. 边界条件
# ---------------------------------------------------------------------------


def test_consistency_at_minimum_index():
    """i=21 是最小合法下标（需 22 根 bar）。"""
    bars = _mkbars(60)
    d = _compare(bars, 21)
    assert d == {}, f"i=21 处不一致：{d}"


def test_consistency_index_below_minimum():
    """i < 21 → 两者都应返回 None。"""
    bars = _mkbars(60)
    for i in (0, 5, 20):
        prod = five_factor.compute_factors(bars[max(0, i - 21):i + 1])
        closes = [b["close"] for b in bars]
        amounts = [b["amount"] for b in bars]
        ic = ic_mod._factors_at(closes, amounts, i, liq_min=None)
        assert (prod is None) == (ic is None), f"i={i} 判定不一致"


# ---------------------------------------------------------------------------
# 3. 真实数据（关键：覆盖真实的零成交日与价格路径）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["600519", "601318", "600036", "000002", "600030"])
def test_consistency_real_data(code):
    """真实数据上逐信号日对比（门槛层 + 因子值层），必须一致。

    这是最强的一条：覆盖真实的停牌、除权跳空、极端价格路径。

    ⚠️ 样本里包含**早年流动性不足**的情形（如 2003 年的 600030，
    liq20=4.28e7 不过 1e8 门槛）—— 门槛层的判定也必须一致，
    这正是 `_compare` 分层的原因。
    """
    paths = [p for _c, _m, p in day_reader.scan_paths("D:/new_tdx/vipdoc")
             if os.path.basename(p)[2:8] == code]
    if not paths:
        pytest.skip(f"{code} 不在本机数据中")
    bars = day_reader.read_day_all(paths[0])
    if len(bars) < 300:
        pytest.skip(f"{code} 历史不足（{len(bars)} 根）")
    n_checked = 0
    n_gate = 0
    mismatches = []
    for i in range(200, len(bars) - 5, 7):
        d = _compare(bars, i)
        n_checked += 1
        if "gate" in d:
            n_gate += 1
        if d:
            mismatches.append((i, d))
    assert n_checked > 9, f"{code} 有效对比样本仅 {n_checked} 个，测试无意义"
    assert not mismatches, (
        f"{code} 有 {len(mismatches)}/{n_checked} 个信号日不一致"
        f"（其中门槛层分歧 {n_gate} 个）；前 3 个：{mismatches[:3]}")


# ---------------------------------------------------------------------------
# 4. 门槛参数行为
# ---------------------------------------------------------------------------


def test_liq_min_none_skips_gate():
    """liq_min=None 必须**不做**流动性过滤（跨年代实验依赖此行为）。"""
    bars = _mkbars(60, amount=1e5)          # 成交额远低于 1e8
    closes = [b["close"] for b in bars]
    amounts = [b["amount"] for b in bars]
    # 生产（含 1e8 门槛）会拒绝
    assert five_factor.compute_factors(bars[-80:]) is None
    # IC 传 None 应通过
    assert ic_mod._factors_at(closes, amounts, 59, liq_min=None) is not None
    # IC 传 1e8 应与生产一致地拒绝
    assert ic_mod._factors_at(closes, amounts, 59, liq_min=1e8) is None


def test_liq_min_matches_production_gate():
    """传 liq_min=1e8 时，门槛行为必须与生产完全一致。"""
    for amt in (9.9e7, 1.0e8, 1.01e8):
        bars = _mkbars(60, amount=amt)
        closes = [b["close"] for b in bars]
        amounts = [b["amount"] for b in bars]
        prod = five_factor.compute_factors(bars[-80:])
        ic = ic_mod._factors_at(closes, amounts, 59, liq_min=1e8)
        assert (prod is None) == (ic is None), (
            f"成交额 {amt:.2e} 时门槛判定不一致")
