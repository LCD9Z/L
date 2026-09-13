# -*- coding: utf-8 -*-
"""V3.2 A股资金/龙虎榜确定性特征层。

只做可复核的比率和标签；不把资金流直接解释成“主力买入”，避免把数据语义扩大化。
"""
from __future__ import annotations
from statistics import mean
from typing import Any, Dict, Iterable


def _f(v):
    try:
        return None if v in (None, "", "-") else float(v)
    except (TypeError, ValueError):
        return None


def moneyflow_features(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows or [])
    nets = []
    amounts = []
    for r in rows:
        net = _f(r.get("net_mf_amount") or r.get("net_amount") or r.get("net_flow"))
        amt = _f(r.get("amount") or r.get("trade_amount"))
        if net is not None: nets.append(net)
        if amt is not None: amounts.append(amt)
    if not nets:
        return {"status": "insufficient_data", "rows": len(rows)}
    return {
        "status": "ok",
        "rows": len(rows),
        "net_flow_latest": nets[-1],
        "net_flow_mean": mean(nets),
        "net_flow_positive_ratio": sum(1 for x in nets if x > 0) / len(nets),
        "amount_mean": mean(amounts) if amounts else None,
    }


def top_list_features(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows or [])
    reasons = []
    net_buy = []
    for r in rows:
        reason = str(r.get("reason") or r.get("name") or "").strip()
        if reason: reasons.append(reason)
        v = _f(r.get("net_amount") or r.get("net_buy") or r.get("net_mf_amount"))
        if v is not None: net_buy.append(v)
    return {
        "status": "ok" if rows else "insufficient_data",
        "rows": len(rows),
        "distinct_reasons": list(dict.fromkeys(reasons)),
        "net_buy_total": sum(net_buy) if net_buy else None,
        "net_buy_positive_ratio": (sum(1 for x in net_buy if x > 0) / len(net_buy)) if net_buy else None,
    }
