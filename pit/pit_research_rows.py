"""Build research rows only from PIT-tradable observations.

Rows remain unchanged except for an explicit eligibility filter. Missing PIT
eligibility is never interpreted as eligible in strict mode.
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List


def filter_pit_research_rows(
    rows: Iterable[Dict[str, Any]], *, strict: bool = True
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        flag = row.get("pit_trading_eligible")
        if strict:
            if flag is True:
                out.append(dict(row))
        else:
            if flag is not False:
                out.append(dict(row))
    return out


def attach_research_price(
    rows: Iterable[Dict[str, Any]], *, prefer_adjusted: bool = True
) -> List[Dict[str, Any]]:
    """Expose a single research_price without mutating raw OHLC fields."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        raw = item.get("close")
        adjusted = item.get("adjusted_close")
        if prefer_adjusted and adjusted not in (None, ""):
            item["research_price"] = float(adjusted)
            item["research_price_source"] = "corporate_action_adjusted"
        elif raw not in (None, ""):
            item["research_price"] = float(raw)
            item["research_price_source"] = "raw_unadjusted"
        else:
            item["research_price"] = None
            item["research_price_source"] = "missing"
        out.append(item)
    return out
