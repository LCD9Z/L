# -*- coding: utf-8 -*-
"""守卫：sqrt 冲击成本模型（H-IMPACT）与「必报」量级统计。

## 背景

`IMPACT_COST_PREREG.md`（H-IMPACT）要求用 Almgren-Chriss sqrt 律
（`impact = k · σ_daily · √(Q/V)`，k=1.0，地板 1bp）替换阶梯滑点，
并在登记 §四「必报」中要求：**sqrt 冲击的平均/最大 bps（买入端与卖出端分开）**。

回测引擎原先只把 slip 用于定价、不留痕，无法回答「模型量级是多少」。
本文件锁住两点：
1. `risk.liquidity.sqrt_impact` 本身的行为（地板、单调性、缺失兜底）；
2. `portfolio_backtest(impact_model=True)` 在结果里回报的 `impact_stats`。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from portfolio_backtest import portfolio_backtest  # noqa: E402
from risk.liquidity import sqrt_impact  # noqa: E402


def _mk_bars(closes, *, spread=0.05, amount=1e8, start="2024-01-01"):
    """由收盘序列造 OHLC。high=close+spread/2, low=close−spread/2。"""
    out = []
    y, m, d = 2024, 1, 1
    for c in closes:
        out.append({"date": f"{y}-{m:02d}-{d:02d}",
                    "open": c, "high": c + spread / 2, "low": c - spread / 2,
                    "close": c, "volume": 1e6, "amount": amount,
                    "limit_ratio": "0.10"})
        d += 1
        if d > 28:
            d = 1
            m += 1
            if m > 12:
                m = 1
                y += 1
    return out


def _oscillating(n=80, base=10.0, amp=0.1):
    return [base + amp * ((-1) ** i) for i in range(n)]


# ---------------------------------------------------------------------------
# sqrt_impact 本身
# ---------------------------------------------------------------------------

def test_sqrt_impact_floor_is_one_bp():
    """notional 极小时冲击低于地板 → 必须返回 1bp，不得返回 0（否则成本被静默抹掉）。"""
    assert sqrt_impact(_mk_bars([10.0] * 25), 1e-9) == pytest.approx(0.0001)


def test_sqrt_impact_is_monotone_in_notional():
    """√(Q/V) 律：名义金额越大，冲击越大。"""
    bars = _mk_bars(_oscillating(25))
    assert sqrt_impact(bars, 1e6) > sqrt_impact(bars, 1e4)


def test_sqrt_impact_falls_back_when_amount_missing():
    """无成交额数据 → 无法算 V，返回 30bp 兜底（不得静默返回 0）。"""
    bars = [{"date": f"2024-01-{i + 1:02d}", "close": 10.0} for i in range(25)]
    assert sqrt_impact(bars, 1e5) == pytest.approx(0.0030)


def test_sqrt_impact_zero_sigma_hits_floor():
    """价格恒定 → σ=0 → 冲击为 0 → 落到 1bp 地板。"""
    assert sqrt_impact(_mk_bars([10.0] * 25), 1e6) == pytest.approx(0.0001)


# ---------------------------------------------------------------------------
# 回测回报的 impact_stats（H-IMPACT 登记 §四「必报」项）
# ---------------------------------------------------------------------------

def _run(**kw):
    """⚠️ 单仓上限用 0.5 而非 1.0 —— 与 tests/test_atr_stop.py 同一构造陷阱：
    `max_position_pct=1.0` 时预算吃满现金、加佣金后 `total > cash`，
    仓位被静默跳过（`trades == 0`），看起来像「模型没生效」。"""
    bars = {"000001": _mk_bars(_oscillating(80))}
    return portfolio_backtest(bars, threshold=0, top_n=1, horizon=10,
                              max_position_pct=0.5, min_avg_amount=0, **kw)


def test_impact_stats_present_even_when_model_off():
    """字段必须恒存在（值为 0/None）—— 否则下游脚本会 KeyError。"""
    st = _run()["impact_stats"]
    assert st["impact_model"] is False
    assert st["buy"] == {"n": 0, "mean_bps": None, "max_bps": None, "min_bps": None}
    assert st["sell"]["n"] == 0


def test_impact_stats_recorded_when_model_on():
    """开启后买入端与卖出端都必须有记录，且不低于 1bp 地板。"""
    st = _run(impact_model=True)["impact_stats"]
    assert st["impact_model"] is True
    assert st["buy"]["n"] > 0, "买入端未记录冲击"
    assert st["sell"]["n"] > 0, "卖出端未记录冲击"
    assert st["buy"]["min_bps"] >= 1.0
    assert st["sell"]["min_bps"] >= 1.0
    assert st["buy"]["max_bps"] >= st["buy"]["mean_bps"] >= st["buy"]["min_bps"]


def test_impact_stats_above_floor_when_sigma_positive():
    """价格有波动 → σ>0 → 均值必须高于 1bp 地板（否则说明 σ 没被用上）。"""
    st = _run(impact_model=True)["impact_stats"]
    assert st["buy"]["mean_bps"] > 1.0


def test_ladder_slippage_run_has_no_impact_records():
    """对照组（阶梯滑点）不得留下冲击记录 —— 防止两条成本路径被混淆。"""
    st = _run(impact_model=False)["impact_stats"]
    assert st["buy"]["n"] == 0 and st["sell"]["n"] == 0
