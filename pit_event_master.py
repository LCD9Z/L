# -*- coding: utf-8 -*-
"""Conservative PIT event master for verified A-share risk/suspension events.

This module stores only externally verified events. It never converts a missing
TDX bar into a suspension/ST event automatically. Unknown history remains unknown.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PITEvent:
    code: str
    event_type: str
    start_date: str
    end_date: str = ""
    source: str = "public_notice"
    confidence: str = "verified_public"
    note: str = ""

    def contains(self, date: str) -> bool:
        return self.start_date <= date and (not self.end_date or date <= self.end_date)


# Phase 54 evidence sampled from public exchange/company notices during research.
# These are deliberately narrow: they are not claimed to be the complete ST or
# suspension history of the affected securities.
VERIFIED_EVENTS = (
    PITEvent("002731", "suspension", "2026-05-06", "2026-07-06", note="annual-report disclosure failure; resumed 2026-07-07"),
    PITEvent("002731", "risk_warning", "2026-07-07", "", note="*ST risk warning effective on resumption"),
    PITEvent("002731", "suspension", "2026-09-01", "", note="2026 interim report not disclosed by statutory deadline"),
    PITEvent("000016", "risk_warning", "2026-08-28", "", note="*ST status confirmed in voluntary delisting announcement"),
    PITEvent("000016", "suspension", "2026-09-04", "", note="voluntary termination-of-listing process"),
    PITEvent("301139", "suspension", "2026-05-11", "2026-05-11", note="one-day suspension before risk warning resumption"),
    PITEvent("301139", "risk_warning", "2026-05-12", "", note="*ST risk warning effective on resumption"),
    PITEvent("603159", "suspension", "2026-06-16", "", note="continuous suspension for material matter; end not encoded without verified resumption date"),
    PITEvent("002870", "suspension", "2026-09-01", "", note="material transaction planning"),
    PITEvent("002998", "suspension", "2026-09-04", "", note="control-change transaction planning"),
    PITEvent("600929", "suspension", "2026-08-31", "", note="control-change/asset acquisition planning"),
)


def verified_events() -> list[PITEvent]:
    return list(VERIFIED_EVENTS)


def events_for_code(code: str, events: Iterable[PITEvent] = VERIFIED_EVENTS) -> list[PITEvent]:
    code = str(code).zfill(6)
    return [e for e in events if e.code == code]


def active_event_types(code: str, date: str, events: Iterable[PITEvent] = VERIFIED_EVENTS) -> set[str]:
    return {e.event_type for e in events_for_code(code, events) if e.contains(date)}


def attach_pit_events(rows: Iterable[dict], events: Iterable[PITEvent] = VERIFIED_EVENTS) -> list[dict]:
    out = []
    for row in rows:
        item = dict(row)
        code = str(item.get("code", "")).zfill(6)
        date = str(item.get("date", item.get("trade_date", "")))[:10]
        active = sorted(active_event_types(code, date, events)) if date else []
        item["pit_event_types"] = active
        item["is_suspended"] = "suspension" in active
        item["risk_warning_active"] = "risk_warning" in active
        out.append(item)
    return out


def evidence_summary(events: Iterable[PITEvent] = VERIFIED_EVENTS) -> dict[str, object]:
    items = list(events)
    return {
        "verified_event_count": len(items),
        "codes": sorted({e.code for e in items}),
        "suspension_event_count": sum(e.event_type == "suspension" for e in items),
        "risk_warning_event_count": sum(e.event_type == "risk_warning" for e in items),
        "complete_historical_st": False,
        "complete_historical_suspension": False,
        "alpha_claim_eligible": False,
        "reason": "verified event sample is an evidence overlay, not a complete historical PIT master",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(evidence_summary(), ensure_ascii=False, indent=2))
