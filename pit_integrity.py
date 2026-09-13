# -*- coding: utf-8 -*-
"""Phase 40/41 PIT integrity checks for A-share research data.

Rejects duplicate observations, malformed chronology, and records whose
availability/publication/as-of timestamp is later than the research cutoff.
Designed to be dependency-free and light enough for 8 GB machines.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Iterable, Dict, List, Tuple


def _norm_ts(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s[:19] if s else None


def _parse_date(v: Any) -> str | None:
    s = _norm_ts(v)
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def audit_pit_rows(rows: Iterable[Dict[str, Any]], cutoff: str | None = None, *, require_timestamp: bool = False) -> Dict[str, Any]:
    """Audit rows for point-in-time integrity.

    A row is only usable on its trade date when every known availability field
    (available_at, published_at, asof) is not later than the cutoff/trade date.
    Missing timestamps are reported rather than silently accepted.
    """
    rows = list(rows)
    issues: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    last_by_code: Dict[str, str] = {}
    for i, r in enumerate(rows):
        code = str(r.get("code", "")).strip()
        trade = _norm_ts(r.get("trade_date") or r.get("date"))
        if not code or not trade:
            issues.append({"index": i, "type": "missing_code_or_trade_date"})
            continue
        key = (code, trade[:10])
        if key in seen:
            issues.append({"index": i, "type": "duplicate_code_trade_date", "key": key})
        seen.add(key)
        d = _parse_date(trade)
        if not d:
            issues.append({"index": i, "type": "invalid_trade_date", "value": trade})
        if code in last_by_code and trade[:10] < last_by_code[code]:
            issues.append({"index": i, "type": "non_monotonic_date", "code": code})
        last_by_code[code] = trade[:10]

        effective_cutoff = _norm_ts(cutoff) or trade[:10]
        availability_fields = ("available_at", "published_at", "asof")
        present = False
        for field in availability_fields:
            ts = _norm_ts(r.get(field))
            if ts is None:
                continue
            present = True
            if ts > effective_cutoff:
                issues.append({
                    "index": i,
                    "type": "future_available_data",
                    "field": field,
                    "available_at": ts,
                    "cutoff": effective_cutoff,
                })
        if not present and require_timestamp:
            issues.append({"index": i, "type": "missing_availability_timestamp"})

    types = sorted({x["type"] for x in issues})
    return {"ok": not issues, "rows": len(rows), "issues": issues[:200], "issue_types": types}


def require_pit_rows(rows: Iterable[Dict[str, Any]], cutoff: str, *, allow_missing_timestamp: bool = False) -> Dict[str, Any]:
    """Strict wrapper used by real Alpha pipelines."""
    result = audit_pit_rows(rows, cutoff=cutoff, require_timestamp=not allow_missing_timestamp)
    if allow_missing_timestamp:
        result["issues"] = [x for x in result["issues"] if x["type"] != "missing_availability_timestamp"]
        result["issue_types"] = sorted({x["type"] for x in result["issues"]})
        result["ok"] = not result["issues"]
    return result
