# -*- coding: utf-8 -*-
"""Apply verified PIT event evidence to a tradability universe.

Conservative by design: only verified events are acted on. Missing event history
never becomes a synthetic suspension/ST flag.
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List

from .pit_event_master import active_event_types


def trading_eligible(
    code: str,
    date: str,
    *,
    events: Iterable[Any],
    exclude_risk_warning: bool = False,
) -> bool:
    active = active_event_types(code, date, events)
    if "suspension" in active:
        return False
    return not (exclude_risk_warning and "risk_warning" in active)


def filter_snapshot(
    snapshot: Iterable[str],
    date: str,
    *,
    events: Iterable[Any],
    exclude_risk_warning: bool = False,
) -> List[str]:
    return sorted(
        code for code in snapshot
        if trading_eligible(
            str(code).zfill(6), date, events=events,
            exclude_risk_warning=exclude_risk_warning,
        )
    )


def annotate_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    events: Iterable[Any],
    exclude_risk_warning: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        code = str(item.get("code", "")).zfill(6)
        date = str(item.get("date", item.get("trade_date", "")))[:10]
        item["pit_trading_eligible"] = trading_eligible(
            code, date, events=events, exclude_risk_warning=exclude_risk_warning
        ) if code and date else False
        out.append(item)
    return out
