# -*- coding: utf-8 -*-
"""Phase 41: build point-in-time A-share universe snapshots from a dated security master.

The security master must describe listing/delisting dates as they were known for
research purposes. This module deliberately does not infer historical ST status,
suspension or corporate-action eligibility from today's metadata.
"""
from __future__ import annotations
from datetime import date
from typing import Any, Dict, Iterable, List


def _norm_code(v: Any) -> str:
    s = str(v or "").strip().lower()
    for p in ("sh", "sz", "bj"):
        if s.startswith(p):
            s = s[2:]
            break
    return s.zfill(6)


def _norm_date(v: Any) -> str:
    if v in (None, "", "-"):
        return ""
    s = str(v).strip().replace("/", "-")
    if len(s) == 8 and s.isdigit():
        s = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid_date:{v}") from exc


def _is_ashare_code(code: str) -> bool:
    # 2xxxxxx (SZ B-share) and 9xxxxxx (SH B-share) are excluded.
    return code.startswith(("0", "3", "4", "6", "8"))


def build_snapshot_map(
    security_master: Iterable[Dict[str, Any]],
    trade_dates: Iterable[str],
    *,
    include_delisted_on_date: bool = False,
) -> Dict[str, List[str]]:
    """Build {trade_date: [codes]} using listing/delisting boundaries only.

    Required columns per security: code, list_date.
    Optional: delist_date, market/security_type. Unknown historical ST or suspension
    state is *not* inferred here and must be supplied by a separate PIT source.
    """
    securities = []
    seen = set()
    for raw in security_master:
        code = _norm_code(raw.get("code") or raw.get("ts_code"))
        if not code or not _is_ashare_code(code) or code in seen:
            continue
        list_date = _norm_date(raw.get("list_date"))
        if not list_date:
            raise ValueError(f"missing_list_date:{code}")
        delist_date = _norm_date(raw.get("delist_date")) if raw.get("delist_date") else ""
        securities.append((code, list_date, delist_date))
        seen.add(code)

    out: Dict[str, List[str]] = {}
    for d in sorted({_norm_date(x) for x in trade_dates if x}):
        active = []
        for code, list_date, delist_date in securities:
            if d < list_date:
                continue
            if delist_date:
                if include_delisted_on_date:
                    if d > delist_date:
                        continue
                elif d >= delist_date:
                    continue
            active.append(code)
        out[d] = sorted(active)
    return out


def validate_snapshot_coverage(snapshot_map: Dict[str, List[str]], required_dates: Iterable[str]) -> Dict[str, Any]:
    required = sorted({_norm_date(x) for x in required_dates if x})
    missing = [d for d in required if d not in snapshot_map]
    empty = [d for d in required if d in snapshot_map and not snapshot_map[d]]
    return {
        "required_dates": len(required),
        "snapshot_dates": len(snapshot_map),
        "missing_dates": missing,
        "empty_dates": empty,
        "ok": not missing and not empty,
    }
