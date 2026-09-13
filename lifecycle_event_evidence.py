# -*- coding: utf-8 -*-
"""Certified lifecycle event overlay for observed TDX trading history.

Only events backed by exchange/public evidence are recorded.  Absence of an
observed bar is never converted into a delisting event automatically.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class LifecycleEvent:
    code: str
    event: str
    effective_date: str
    source: str
    confidence: str = "certified_public"


# Verified against exchange/public notices during Phase 53 research.
# effective_date is the first date on which the security is no longer a normal
# listed A-share for PIT-universe purposes (the delisting/removal date).
VERIFIED_2026_DELISTINGS = (
    LifecycleEvent("000004", "delisted", "2026-07-14", "SZSE/public notice"),
    LifecycleEvent("002808", "delisted", "2026-07-14", "SZSE/public notice"),
    LifecycleEvent("002898", "delisted", "2026-07-17", "SZSE/public notice"),
    LifecycleEvent("300029", "delisted", "2026-07-10", "SZSE/public notice"),
    LifecycleEvent("920305", "delisted", "2026-07-30", "BSE/public notice"),
    LifecycleEvent("600193", "delisted", "2026-07-06", "SSE/public notice"),
    LifecycleEvent("600421", "delisted", "2026-06-26", "SSE/public notice"),
    LifecycleEvent("600599", "delisted", "2026-06-26", "SSE/public notice"),
    LifecycleEvent("600608", "delisted", "2026-07-03", "SSE/public notice"),
    LifecycleEvent("600636", "delisted", "2026-06-26", "SSE/public notice"),
    LifecycleEvent("600696", "delisted", "2026-06-29", "SSE/public notice"),
    LifecycleEvent("605081", "delisted", "2026-07-03", "SSE/public notice"),
)


def verified_events() -> list[LifecycleEvent]:
    return list(VERIFIED_2026_DELISTINGS)


def event_map(events: Iterable[LifecycleEvent] = VERIFIED_2026_DELISTINGS) -> dict[str, LifecycleEvent]:
    return {e.code: e for e in events}


def apply_verified_delistings(
    observed: Iterable[Mapping[str, object]],
    *,
    events: Iterable[LifecycleEvent] = VERIFIED_2026_DELISTINGS,
) -> list[dict[str, object]]:
    """Attach certified delisting date without altering observed dates."""
    emap = event_map(events)
    out: list[dict[str, object]] = []
    for row in observed:
        item = dict(row)
        code = str(item.get("code", "")).zfill(6)
        ev = emap.get(code)
        item["certified_delist_date"] = ev.effective_date if ev else ""
        item["lifecycle_status"] = ev.event.upper() if ev else "OBSERVED_ONLY"
        item["lifecycle_source"] = ev.source if ev else "tdx_observed_history_only"
        out.append(item)
    return out


def lifecycle_evidence_report(observed_codes: Iterable[str]) -> dict[str, object]:
    codes = {str(c).zfill(6) for c in observed_codes}
    matched = sorted(c for c in codes if c in event_map())
    return {
        "verified_event_count": len(VERIFIED_2026_DELISTINGS),
        "matched_observed_codes": len(matched),
        "matched_codes": matched,
        "unresolved_observed_end_codes": sorted(codes - set(matched)),
        "alpha_claim_eligible": False,
        "reason": "lifecycle evidence is still incomplete for the full historical universe",
    }
