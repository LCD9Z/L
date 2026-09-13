# -*- coding: utf-8 -*-
"""Deterministic guard against survivorship-biased A-share research claims."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class SurvivorshipAudit:
    """Evidence required before a backtest may claim full-universe validity."""
    pit_universe_ok: bool
    lifecycle_ok: bool
    delisted_history_ok: bool
    st_history_ok: bool
    suspension_history_ok: bool
    corporate_actions_ok: bool
    missing_delisted_codes: int = 0

    @property
    def ok(self) -> bool:
        return all((
            self.pit_universe_ok,
            self.lifecycle_ok,
            self.delisted_history_ok,
            self.st_history_ok,
            self.suspension_history_ok,
            self.corporate_actions_ok,
        ))

    @property
    def status(self) -> str:
        return "OK" if self.ok else "INCONCLUSIVE"

    @property
    def reason(self) -> str:
        if self.ok:
            return "survivorship_and_lifecycle_evidence_complete"
        return "SURVIVORSHIP DATA INCOMPLETE"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.update({"ok": self.ok, "status": self.status, "reason": self.reason})
        return out


def audit_survivorship(
    *,
    pit_universe: bool,
    lifecycle: bool,
    delisted_history: bool,
    st_history: bool,
    suspension_history: bool,
    corporate_actions: bool,
    missing_delisted_codes: int = 0,
) -> SurvivorshipAudit:
    """Build a conservative audit; no missing evidence is inferred as valid."""
    return SurvivorshipAudit(
        pit_universe_ok=bool(pit_universe),
        lifecycle_ok=bool(lifecycle),
        delisted_history_ok=bool(delisted_history),
        st_history_ok=bool(st_history),
        suspension_history_ok=bool(suspension_history),
        corporate_actions_ok=bool(corporate_actions),
        missing_delisted_codes=max(0, int(missing_delisted_codes)),
    )


def guard_alpha_claim(audit: SurvivorshipAudit) -> dict[str, Any]:
    """Return a machine-readable decision for release/backtest callers."""
    if audit.ok:
        return {"allowed": True, "status": "ALPHA_EVIDENCE_ELIGIBLE", "reasons": []}
    return {
        "allowed": False,
        "status": "INCONCLUSIVE",
        "reasons": ["SURVIVORSHIP DATA INCOMPLETE"],
        "audit": audit.to_dict(),
    }
