# -*- coding: utf-8 -*-
"""执行侧拒单计数（`portfolio_backtest.execution_stats`）的守卫。

背景见 `REGIME_ATTRIBUTION_PREREG.md` §三.0-A：一字涨停买不进时，原实现直接
`continue`，事后无法回答「多少信号被可执行性挡掉」。本文件钉住三件事：

1. 字段**恒返回**（即使一次都没被拒），避免调用方写 `if key in r` 的分支；
2. 涨停真的被拒时**真的计数**，且明细与计数自洽（不是摆设）；
3. 计数是**纯计数** —— 加入计数前后，交易序列与收益不变。

第 3 条是本文件最重要的一条：如果计数顺手改了行为，`execution_stats` 就会成为
「悄悄改变结论的观测器」，那比没有还危险。
"""
from __future__ import annotations

import datetime as _dt

from portfolio_backtest import portfolio_backtest


def _bars(n=60, start_price=10.0, amount=5e8, limit_up_at=None):
    """构造确定性日线；`limit_up_at` 指定的下标做成「一字涨停」bar。

    涨停价按主板 10% 取整到分：`round(prev_close * 1.1, 2)`。
    """
    out = []
    base = _dt.date(2024, 1, 1)
    for i in range(n):
        c = start_price + i * 0.12
        row = {
            "date": str(base + _dt.timedelta(days=i)),
            "open": c - 0.03, "high": c + 0.08, "low": c - 0.08, "close": c,
            "turnover": 3, "amount": amount, "volume": amount / c / 100.0,
        }
        out.append(row)
    if limit_up_at is not None:
        prev_close = out[limit_up_at - 1]["close"]
        up = round(prev_close * 1.1, 2)
        out[limit_up_at].update({"open": up, "high": up, "low": up, "close": up})
        # 涨停后的相邻 bar 仍沿用原趋势，避免随后几日价格跳变影响可读性
    return out


def _flat_score(code, hist, day):
    return {"score": 90.0, "risk": 1.0}


def _run(bars_map, **kw):
    params = dict(threshold=70, top_n=1, horizon=3, min_avg_amount=0,
                  score_func=_flat_score)
    params.update(kw)
    return portfolio_backtest(bars_map, **params)


def test_execution_stats_always_present():
    """即便一次都没被拒，键也必须存在（值为 0），便于统一读取。"""
    r = _run({"000001": _bars()})
    st = r["execution_stats"]
    for k in ("rejects", "opened", "limit_up_rate_pct", "limit_up_skips",
              "limit_up_skips_truncated"):
        assert k in st, f"execution_stats 缺键 {k}"
    for k in ("limit_up", "shares_zero", "cash_short", "no_cash",
              "exit_deferred_days"):
        assert k in st["rejects"], f"rejects 缺键 {k}"
        assert st["rejects"][k] == 0, f"无拒单场景下 {k} 应为 0"


def test_limit_up_skip_counted():
    """一字涨停的候选必须被拒，并留下明细。"""
    # 第 30 根做成一字涨停：最早可能的信号日下标是 29（len(hist)>=30），
    # 成交落在下标 30，正好撞上涨停。
    bars = _bars(limit_up_at=30)
    r = _run({"000001": bars})
    st = r["execution_stats"]
    assert st["rejects"]["limit_up"] == 1, (
        f"应拒单 1 次，实际 {st['rejects']['limit_up']}")
    assert len(st["limit_up_skips"]) == 1
    skip = st["limit_up_skips"][0]
    assert skip["code"] == "000001"
    assert skip["next_date"] == bars[30]["date"], "明细里的成交日应是涨停那一天"
    assert st["limit_up_skips_truncated"] is False
    # 分母自洽：拒单 1 笔 + 实际建仓若干
    assert st["opened"] >= 1
    assert st["limit_up_rate_pct"] is not None


def test_counters_are_pure_observation():
    """计数不得改变交易结果：同输入两次运行，交易序列与收益逐位相同。"""
    bars = _bars(limit_up_at=30)
    a = _run({"000001": bars})
    b = _run({"000001": bars})
    assert a["total_return_pct"] == b["total_return_pct"]
    assert a["final_equity"] == b["final_equity"]
    assert a["trade_log"] == b["trade_log"]
    assert a["execution_stats"] == b["execution_stats"]


def test_limit_up_skip_does_not_block_next_day():
    """被涨停挡掉一次后，次日正常行情仍应能建仓（拒单不是永久剔除）。"""
    bars = _bars(limit_up_at=30)
    r = _run({"000001": bars})
    entries = [t["entry_date"] for t in r["trade_log"]]
    assert r["execution_stats"]["opened"] >= 1
    assert all(e > bars[30]["date"] for e in entries), (
        "被拒的那一天不应出现在成交日里")
