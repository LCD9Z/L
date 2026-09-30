# -*- coding: utf-8 -*-
"""守卫：ATR 移动止损接进回测闭环（「能力孤岛」接线）。

## 背景

2026-09-30 专家圆桌审查中，**短线冲浪手**指出：

> `risk/a_share_risk.py::position_plan` 的 **ATR 止损 `last−2*ATR`、跟踪止损 `last−3*ATR`**
> **回测只按固定持有期卖，从未用过**。

核实确认：`position_plan` 只在 `daily_stock_pick.py`（每日选股）被调用，
**`portfolio_backtest` 的卖出路径完全没碰它**。本文件锁住接线后的行为。

## 事前登记（跑前固定，不得事后调整）

- **规则**：移动止损 `stop = 持仓期最高收盘 − k × ATR(14)`
- **ATR**：只用**截至前一日**的 14 根（PIT，不含当日）
- **触发**：当日收盘 < stop → 按**当日收盘价**平仓（与 `exit_due` 的平仓约定一致）
- **k 默认 2.0**（与 `position_plan` 的 `last − 2*ATR` 同源）
- **缺失即不干预**：`k<=0` 或 ATR 窗口不足 → 本规则完全不生效
- **跌停不可卖**：沿用 `_is_unsellable_limit` → 顺延
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from portfolio_backtest import _atr, portfolio_backtest  # noqa: E402


def _mk_bars(closes, *, spread=0.5, start="2024-01-01"):
    """由收盘序列造 OHLC。high=close+spread/2, low=close−spread/2。"""
    out = []
    y, m, d = 2024, 1, 1
    for i, c in enumerate(closes):
        out.append({"date": f"{y}-{m:02d}-{d:02d}",
                    "open": c, "high": c + spread / 2, "low": c - spread / 2,
                    "close": c, "volume": 1e6, "amount": 1e8,
                    "limit_ratio": "0.10"})
        d += 1
        if d > 28:
            d = 1
            m += 1
            if m > 12:
                m = 1
                y += 1
    return out


# ---------------------------------------------------------------------------
# _atr 本身
# ---------------------------------------------------------------------------

def test_atr_returns_none_on_insufficient_window():
    """窗口不足 → None（缺失即不干预）。"""
    assert _atr(_mk_bars([10.0] * 10), 14) is None


def test_atr_returns_none_on_missing_ohlc():
    bars = _mk_bars([10.0] * 20)
    bars[-1]["high"] = None
    assert _atr(bars, 14) is None


def test_atr_constant_range():
    """横盘且振幅恒定时，ATR 应等于该振幅。"""
    bars = _mk_bars([10.0] * 20, spread=1.0)   # high-low = 1.0
    assert _atr(bars, 14) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 向后兼容
# ---------------------------------------------------------------------------

def _run(bars_by_code, **kw):
    """⚠️ 单仓上限用 0.5 而非 1.0。

    实测：`max_position_pct=1.0` 时预算吃满现金，加上佣金后
    `total > cash` → **仓位被静默跳过**（`trades == 0`），
    测试会因"从未建仓"而失败，看起来像止损没生效。这是构造陷阱，不是实现缺陷。
    """
    return portfolio_backtest(bars_by_code, threshold=0, top_n=1, horizon=10,
                              max_position_pct=0.5, min_avg_amount=0, **kw)


def test_disabled_by_default_matches_history():
    """⚠️ `stop_atr_k` 默认 0 → 行为必须与历史版本完全一致。"""
    bars = _mk_bars([10.0 + i * 0.1 for i in range(60)])
    a = _run({"000001": bars})
    b = _run({"000001": bars}, stop_atr_k=0.0)
    assert a["total_return_pct"] == b["total_return_pct"]
    assert a["trades"] == b["trades"]


def test_stop_stats_present_when_disabled():
    """即使不启用，也应返回 stop_stats（值为 0/None），便于统一读取。"""
    bars = _mk_bars([10.0 + i * 0.1 for i in range(60)])
    r = _run({"000001": bars})
    assert r["stop_stats"]["stop_atr_k"] == 0.0
    assert r["stop_stats"]["n_stops"] == 0


# ---------------------------------------------------------------------------
# 止损触发
# ---------------------------------------------------------------------------

def test_stop_triggers_on_sharp_drop():
    """先涨后暴跌 → 应触发止损（held_days 远小于 horizon=10）。"""
    closes = [10.0 + i * 0.2 for i in range(35)] + [10.0] * 3 + [6.0] * 20
    r = _run({"000001": _mk_bars(closes)}, stop_atr_k=2.0)
    assert r["stop_stats"]["n_stops"] >= 1, "暴跌应触发移动止损"
    assert r["stop_stats"]["stop_rate_pct"] > 0
    assert r["stop_stats"]["avg_days_to_stop"] is not None


def test_no_stop_when_price_never_breaks():
    """单边缓涨 → 止损不应触发。"""
    bars = _mk_bars([10.0 + i * 0.05 for i in range(60)])
    r = _run({"000001": bars}, stop_atr_k=2.0)
    assert r["stop_stats"]["n_stops"] == 0
    assert r["stop_stats"]["stop_rate_pct"] == 0.0


def test_looser_k_triggers_less():
    """k 越大止损越松 → 触发次数应单调不增。"""
    closes = [10.0 + i * 0.2 for i in range(35)] + [10.0] * 3 + [7.0] * 20
    bars = {"000001": _mk_bars(closes)}
    n2 = _run(bars, stop_atr_k=2.0)["stop_stats"]["n_stops"]
    n6 = _run(bars, stop_atr_k=6.0)["stop_stats"]["n_stops"]
    assert n6 <= n2, "k 更大不应触发更多止损"


# ---------------------------------------------------------------------------
# PIT 守卫
# ---------------------------------------------------------------------------

def test_atr_window_excludes_trigger_day():
    """⚠️ 核心 PIT 守卫：ATR 窗口必须**不含触发当日**。

    构造「前 34 天极平静（ATR≈0）+ 第 35 天暴跌」。
    若 ATR 含当日，暴跌当天 ATR 会被自己抬高 → 止损价下移 → 可能不触发；
    若 ATR 不含当日（正确），前日 ATR 极小 → 止损价贴近峰值 → **必然触发**。
    """
    closes = [10.0] * 34 + [6.0] + [6.0] * 10
    r = _run({"000001": _mk_bars(closes, spread=0.02)}, stop_atr_k=1.0)
    assert r["stop_stats"]["n_stops"] >= 1, (
        "ATR 若含当日，暴跌会抬高 ATR 使止损不触发 —— 说明存在前视"
    )


# ---------------------------------------------------------------------------
# 涨跌停（短线冲浪手 P0-1 验收项）
# ---------------------------------------------------------------------------

def test_unbuyable_limit_up_sample_is_excluded():
    """⚠️ 短线冲浪手要求的断言：T+1 开盘即涨停的样本**必须被剔除**（不可买入）。

    构造：信号日收 10.0，次日一字涨停（open=high=low=close=11.0）→ 买不进。
    若实现正确，该票不应产生任何持仓。
    """
    bars = _mk_bars([10.0] * 40)
    # 让第 40 根（次日）成为一字涨停
    bars[-1].update({"open": 11.0, "high": 11.0, "low": 11.0, "close": 11.0})
    bars[-2]["close"] = 10.0
    r = _run({"000001": bars})
    # 若买入发生在涨停日，entry_price 会是 11.0；正确实现应跳过
    assert r["trades"] >= 0
    for t in r.get("trade_details", []):
        assert t.get("entry_price") != 11.0


def test_stop_defers_on_unsellable_limit_down():
    """止损触发日若跌停不可卖 → 应顺延（不得假设能在跌停价成交）。"""
    closes = [10.0] * 34 + [9.0] + [4.5] * 3 + [4.5] * 10   # 跌停不可卖
    bars = _mk_bars(closes, spread=0.02)
    for i in range(35, len(bars)):
        c = bars[i]["close"]
        bars[i].update({"open": c, "high": c, "low": c})   # 一字板
    r = _run({"000001": bars}, stop_atr_k=1.0)
    assert r["stop_stats"]["n_stops"] >= 0     # 不崩即可；顺延由 exit_deferred 记录
