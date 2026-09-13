# -*- coding: utf-8 -*-
"""Deterministic Stage-2 enrichment for the A-share screening pipeline.

No LLM and no invented values.  The function only consumes fields already
present in a research snapshot: money-flow rows, normalized events and daily
bars/quote microstructure.  Missing inputs remain explicitly missing.
"""
from __future__ import annotations
from typing import Any, Dict
from ashare.ashare_market import event_flags
from ashare.ashare_flow_engine import moneyflow_features, top_list_features
from ashare.ashare_event_engine import build_event_risk_pack


def enrich_candidate(row: Dict[str, Any], cutoff: str | None = None) -> Dict[str, Any]:
    quote = row.get("quote") or row
    bars = row.get("bars") or row.get("kline") or []
    flow = row.get("moneyflow") or row.get("money_flow") or []
    top_list = row.get("top_list") or row.get("dragon_tiger") or []
    events = row.get("events") or []

    out: Dict[str, Any] = {}
    if bars:
        out["microstructure"] = event_flags(str(row.get("code") or row.get("ts_code") or ""), bars)
    else:
        out["microstructure"] = {"status": "insufficient_data"}

    out["moneyflow"] = moneyflow_features(flow)
    out["top_list"] = top_list_features(top_list)
    out["event_risk"] = build_event_risk_pack(events, cutoff=cutoff)

    # Deterministic risk flags only. These are review signals, not trade calls.
    flags = []
    if quote.get("is_suspended") is True:
        flags.append("suspended")
    if quote.get("is_st") is True or quote.get("risk_warning") is True:
        flags.append("risk_warning")
    if out["microstructure"].get("limit_down_days", 0) > 0:
        flags.append("recent_limit_down")
    if out["microstructure"].get("failed_limit_up_proxy_days", 0) >= 2:
        flags.append("repeated_failed_limit_up")
    flags.extend(out["event_risk"].get("high_risk_flags", []))
    out["risk_flags"] = list(dict.fromkeys(flags))
    return out
