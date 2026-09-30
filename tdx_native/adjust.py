# -*- coding: utf-8 -*-
"""前复权（qfq）：基于通达信原生权息事件，纯标准库。

除权除息事件（每 10 股口径已在缓存中换算为每股）：

    除权因子 k = (前收盘 − 每股派息 + 配股价×每股配股)
                 / (前收盘 × (1 + 每股送转股 + 每股配股))

前复权：以**最后一根**为基准，事件日**之前**的价格乘以该事件及之后所有事件的 k 连乘。
成交额不受复权影响，故只用价格列。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

Event = Tuple[str, float, float, float, float]   # date, cash_ps, bonus_ps, rights_price, rights_ps


def event_factor(prev_close: float, ev: Event) -> float:
    """单个除权除息事件的 k 因子。"""
    _, cash, bonus, rprice, rshares = ev
    if prev_close <= 0:
        return 1.0
    num = prev_close - cash + rprice * rshares
    den = prev_close * (1.0 + bonus + rshares)
    if den <= 0 or num <= 0:
        return 1.0
    return num / den


def qfq_factors(bars: List[Dict[str, Any]], events: List[Event]) -> Dict[str, float]:
    """返回 {date: 前复权因子}（乘在原价上得复权价）。

    `events` 需按日期升序，且应包含与 bars 时间范围相交的全部事件。
    """
    if not bars:
        return {}
    dates = [b["date"] for b in bars]
    # 每个事件的 k 与其生效日期
    eff: List[Tuple[str, float]] = []
    for ev in events:
        ed = ev[0]
        # 找到事件日之前最后一个交易日的收盘价
        prev_close = None
        for i in range(len(dates) - 1, -1, -1):
            if dates[i] < ed:
                prev_close = bars[i]["close"]
                break
        if prev_close is None or prev_close <= 0:
            continue
        eff.append((ed, event_factor(prev_close, ev)))
    if not eff:
        return dict.fromkeys(dates, 1.0)
    # factor(date) = Π k_e ，对所有 ed > date
    eff.sort(key=lambda x: x[0])
    out: Dict[str, float] = {}
    running = 1.0
    j = len(eff) - 1
    for i in range(len(dates) - 1, -1, -1):
        d = dates[i]
        while j >= 0 and eff[j][0] > d:
            running *= eff[j][1]
            j -= 1
        out[d] = running
    return out


def apply_qfq(bars: List[Dict[str, Any]],
              events: List[Event]) -> List[Dict[str, Any]]:
    """返回复权后的 bar 副本（只改价格列，amount/volume 不变）。"""
    if not events:
        return bars
    fac = qfq_factors(bars, events)
    out = []
    for b in bars:
        f = fac.get(b["date"], 1.0)
        nb = dict(b)
        for k in ("open", "high", "low", "close"):
            nb[k] = b[k] * f
        out.append(nb)
    return out
