# -*- coding: utf-8 -*-
"""Evidence-first A-share corporate-action and adjustment layer.

Raw TDX prices are intentionally kept unadjusted.  This module represents
corporate actions explicitly and derives price-adjustment factors without
inventing missing events.  It supports cash dividends, bonus shares, rights
issues, splits/consolidations, and combined cash+bonus events.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import isfinite
from typing import Iterable, Any


@dataclass(frozen=True)
class CorporateAction:
    code: str
    ex_date: str
    event_type: str
    cash_dividend: float = 0.0
    bonus_ratio: float = 0.0
    rights_ratio: float = 0.0
    rights_price: float = 0.0
    shares_before: float | None = None
    shares_after: float | None = None
    source: str = "unknown"
    confidence: str = "unverified"

    def normalized_code(self) -> str:
        return str(self.code).zfill(6)

    def validate(self) -> None:
        if not self.normalized_code().isdigit() or len(self.normalized_code()) != 6:
            raise ValueError("invalid_code")
        if len(self.ex_date) != 10:
            raise ValueError("invalid_ex_date")
        if self.event_type not in {
            "cash_dividend", "bonus", "cash_bonus", "rights_issue",
            "split", "consolidation", "other"
        }:
            raise ValueError("unsupported_event_type")
        nums = (self.cash_dividend, self.bonus_ratio, self.rights_ratio, self.rights_price)
        if not all(isfinite(float(x)) for x in nums):
            raise ValueError("non_finite_action_value")
        if any(float(x) < 0 for x in nums):
            raise ValueError("negative_action_value")

    def ex_price(self, previous_close: float) -> float:
        """Return theoretical ex-right/ex-dividend price.

        Formula follows the standard A-share/CSI treatment: cash dividend is
        subtracted; bonus/rights shares enlarge the denominator; rights issue
        contributes rights_price * rights_ratio to the numerator.
        """
        self.validate()
        p = float(previous_close)
        if p <= 0 or not isfinite(p):
            raise ValueError("invalid_previous_close")
        if self.event_type in {"split", "consolidation"}:
            if self.shares_before is None or self.shares_after is None:
                raise ValueError("share_counts_required_for_split")
            if self.shares_before <= 0 or self.shares_after <= 0:
                raise ValueError("invalid_share_counts")
            return p * self.shares_before / self.shares_after
        denominator = 1.0 + self.bonus_ratio + self.rights_ratio
        numerator = p - self.cash_dividend + self.rights_price * self.rights_ratio
        if denominator <= 0 or numerator < 0:
            raise ValueError("invalid_ex_price_inputs")
        return numerator / denominator

    def price_factor(self, previous_close: float) -> float:
        """Factor applied to pre-event raw prices for a continuous back-adjusted series."""
        ex = self.ex_price(previous_close)
        factor = ex / float(previous_close)
        if factor <= 0 or not isfinite(factor):
            raise ValueError("invalid_price_factor")
        return factor

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["code"] = self.normalized_code()
        return d


def validate_actions(actions: Iterable[CorporateAction]) -> list[CorporateAction]:
    out = list(actions)
    for action in out:
        action.validate()
    keys = [(a.normalized_code(), a.ex_date, a.event_type) for a in out]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate_corporate_action")
    return sorted(out, key=lambda a: (a.normalized_code(), a.ex_date, a.event_type))


def build_back_adjustment_factors(
    bars: Iterable[dict[str, Any]],
    actions: Iterable[CorporateAction],
) -> list[dict[str, Any]]:
    """Attach deterministic backward-adjustment factors to raw bars.

    The action must be effective on its ex-date.  Missing actions are not
    inferred.  Multiple actions on one date are applied in sequence in the
    supplied validated order; callers should prefer a single authoritative
    consolidated action when available.
    """
    rows = sorted((dict(r) for r in bars), key=lambda r: str(r["date"]))
    acts = validate_actions(actions)
    by_date: dict[str, list[CorporateAction]] = {}
    for a in acts:
        by_date.setdefault(a.ex_date, []).append(a)

    # Derive each event factor from the last raw close before the event date.
    event_factor: dict[str, float] = {}
    prev_close: float | None = None
    for row in rows:
        d = str(row["date"])[:10]
        if d in by_date and prev_close is not None:
            factor = 1.0
            for action in by_date[d]:
                factor *= action.price_factor(prev_close * factor)
            event_factor[d] = factor
        close = row.get("close")
        if close not in (None, ""):
            prev_close = float(close)

    # A back-adjusted series multiplies prices before each event by the
    # cumulative factor of all later events.
    future_factor = 1.0
    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        d = str(row["date"])[:10]
        item = dict(row)
        item["back_adjustment_factor"] = future_factor
        if row.get("close") not in (None, ""):
            item["adjusted_close"] = float(row["close"]) * future_factor
        item["corporate_action_on_date"] = d in event_factor
        out.append(item)
        # The ex-date itself is the new price regime; only earlier dates are
        # multiplied by the event factor.
        if d in event_factor:
            future_factor *= event_factor[d]
    return list(reversed(out))


def evidence_summary(actions: Iterable[CorporateAction]) -> dict[str, Any]:
    items = validate_actions(actions)
    return {
        "event_count": len(items),
        "codes": sorted({a.normalized_code() for a in items}),
        "event_types": sorted({a.event_type for a in items}),
        "verified_event_count": sum(a.confidence == "verified_public" for a in items),
        "complete_historical_corporate_actions": False,
        "alpha_claim_eligible": False,
        "reason": "corporate-action evidence is not yet a complete historical master",
    }


def adjust_execution_price(price: float, action: dict[str, Any]) -> float:
    """Backward-compatible execution-price helper retained from earlier phases.

    `split_ratio` is interpreted as the multiplier of share count; the legacy
    project contract applies the cash dividend after dividing the nominal price.
    New research code should prefer :class:`CorporateAction` for explicit
    ex-right/ex-dividend calculations.
    """
    p = float(price)
    ratio = float(action.get("split_ratio", 1.0) or 1.0)
    cash = float(action.get("cash_dividend", 0.0) or 0.0)
    if p <= 0 or ratio <= 0:
        raise ValueError("invalid_execution_price_inputs")
    return p / ratio - cash
