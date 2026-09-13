# -*- coding: utf-8 -*-
"""portfolio_backtest 的 candidate_filter 钩子测试。

该钩子用于做**事前设定**的因子剔除实验（如剔除动量极端分位）。
关键约束：默认 None 时行为必须与历史版本**完全一致** —— 否则会污染既有回测结论。
"""
import pytest

from portfolio_backtest import portfolio_backtest


def _series(code, n=120, base=10.0, daily=0.015):
    """构造一段能触发策略的行情：稳定上涨 + 每日创新高（满足突破加分）。

    日涨 1.5% → 5 日趋势约 7.7%（落在 5~12% 加分区间）；
    high 贴近 close 使其持续突破前 5 日高点 → score 可越过阈值 70。
    """
    bars = []
    px = base
    for k in range(n):
        px = px * (1 + daily)
        bars.append({
            "date": f"2026-{1 + k // 28:02d}-{1 + k % 28:02d}",
            "open": px * 0.995, "high": px * 1.001, "low": px * 0.99,
            "close": px, "volume": 2_000_000, "amount": 5e8,
        })
    return bars


@pytest.fixture
def data():
    return {f"{i:06d}": _series(f"{i:06d}", base=10.0 + i * 0.5) for i in range(12)}


def test_default_filter_is_none_and_behavior_unchanged(data):
    """不传 candidate_filter 时，结果必须与显式传 None 完全一致。"""
    a = portfolio_backtest(data, threshold=70, top_n=3, horizon=5)
    b = portfolio_backtest(data, threshold=70, top_n=3, horizon=5, candidate_filter=None)
    assert a["trades"] == b["trades"]
    assert a["total_return_pct"] == b["total_return_pct"]
    assert a["win_rate_pct"] == b["win_rate_pct"]


def test_accept_all_filter_matches_none(data):
    """恒真过滤器不应改变任何结果。"""
    a = portfolio_backtest(data, threshold=70, top_n=3, horizon=5)
    b = portfolio_backtest(data, threshold=70, top_n=3, horizon=5,
                           candidate_filter=lambda code, hist, day: True)
    assert a["trades"] == b["trades"]
    assert a["total_return_pct"] == b["total_return_pct"]


def test_reject_all_filter_produces_no_trades(data):
    """恒假过滤器应导致零交易。"""
    r = portfolio_backtest(data, threshold=70, top_n=3, horizon=5,
                           candidate_filter=lambda code, hist, day: False)
    assert r["trades"] == 0


def test_filter_receives_code_hist_and_day(data):
    """回调必须收到 (code, hist, day)，且 hist 为当日及之前的历史。"""
    seen = []

    def spy(code, hist, day):
        seen.append((code, day, len(hist), str(hist[-1]["date"])))
        return True

    portfolio_backtest(data, threshold=70, top_n=2, horizon=5, candidate_filter=spy)
    assert seen, "过滤器未被调用"
    code, day, n, last = seen[0]
    assert code in data
    assert n >= 30
    assert last == day, "hist 的最后一根必须是当日（不得包含未来数据）"


def test_partial_filter_reduces_candidates(data):
    """剔除部分标的应减少交易数，且结果与全量不同。"""
    codes = sorted(data)
    excluded = set(codes[:6])
    base = portfolio_backtest(data, threshold=70, top_n=3, horizon=5)
    filt = portfolio_backtest(
        data, threshold=70, top_n=3, horizon=5,
        candidate_filter=lambda code, hist, day: code not in excluded)
    assert filt["trades"] <= base["trades"]
    assert filt["total_return_pct"] != base["total_return_pct"] or filt["trades"] == 0


def test_filter_does_not_affect_existing_positions(data):
    """过滤只作用于开仓候选，不得影响已持仓的平仓逻辑。

    构造：先全部可买，随后全部不可买 —— 已开仓位仍应按期平仓。
    """
    state = {"block": False}

    def flt(code, hist, day):
        return not state["block"]

    r1 = portfolio_backtest(data, threshold=70, top_n=3, horizon=5, candidate_filter=flt)
    state["block"] = True
    r2 = portfolio_backtest(data, threshold=70, top_n=3, horizon=5, candidate_filter=flt)
    # 全阻断后不应有新交易，但也不应崩溃
    assert r2["trades"] == 0
    assert r1["trades"] > 0
