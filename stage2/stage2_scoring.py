# -*- coding: utf-8 -*-
"""Stage-2 cross-sectional Alpha reranking for A-share candidates.

The scorer is deterministic and only uses observed Stage-2 outputs. Missing
inputs are omitted rather than imputed. It is deliberately a modest overlay
on Stage-1 so noisy event/flow fields cannot completely replace price/volume
structure.
"""
from __future__ import annotations
from typing import Any, Dict, List

from data_contracts import to_float_or_none as _num  # noqa: F401 — 唯一标准实现（CODE_REDUNDANCY_AUDIT P1）


def _rank(values, higher_better=True):
    valid = sorted((v, i) for i, v in enumerate(values) if v is not None)
    if not higher_better:
        valid.reverse()
    out: List[float | None] = [None] * len(values)
    n = len(valid)
    if n <= 1:
        return [0.5 if v is not None else None for v in values]
    for pos, (_, idx) in enumerate(valid):
        out[idx] = pos / (n - 1)
    return out


def rank_stage2_candidates(rows: List[Dict[str, Any]], overlay_weight: float = 0.35) -> List[Dict[str, Any]]:
    """Apply a 35% default Stage-2 Alpha overlay to Stage-1 score.

    Positive signals: persistent money flow, positive top-list buying, recent
    limit-up strength. Negative signals: limit-down days, repeated failed
    limit-ups and high-risk corporate events.
    """
    w = min(0.50, max(0.0, float(overlay_weight)))
    fields = {
        "mf_mean": (lambda r: _num((r.get("moneyflow") or {}).get("net_flow_mean")), True),
        "mf_positive": (lambda r: _num((r.get("moneyflow") or {}).get("net_flow_positive_ratio")), True),
        "tl_positive": (lambda r: _num((r.get("top_list") or {}).get("net_buy_positive_ratio")), True),
        "tl_total": (lambda r: _num((r.get("top_list") or {}).get("net_buy_total")), True),
        "limit_up_streak": (lambda r: _num((r.get("microstructure") or {}).get("max_limit_up_streak")), True),
        "limit_down": (lambda r: _num((r.get("microstructure") or {}).get("limit_down_days")), False),
        "failed_limit_up": (lambda r: _num((r.get("microstructure") or {}).get("failed_limit_up_proxy_days")), False),
        "event_risk": (lambda r: float(len((r.get("event_risk") or {}).get("high_risk_flags", []))), False),
    }
    ranks = {name: _rank([fn(r) for r in rows], hi) for name, (fn, hi) in fields.items()}
    out = []
    for i, row in enumerate(rows):
        positive = [ranks[k][i] for k in ("mf_mean", "mf_positive", "tl_positive", "tl_total", "limit_up_streak") if ranks[k][i] is not None]
        negative = [ranks[k][i] for k in ("limit_down", "failed_limit_up", "event_risk") if ranks[k][i] is not None]
        overlay_parts = positive + negative
        if overlay_parts:
            overlay = sum(overlay_parts) / len(overlay_parts)
            coverage = len(overlay_parts) / len(fields)
            # Sparse Stage-2 evidence should have less influence.
            overlay = 0.5 + (overlay - 0.5) * (0.75 + 0.25 * coverage)
            base = _num(row.get("cross_section_score"))
            base_norm = base / 100.0 if base is not None else 0.5
            score = ((1.0 - w) * base_norm + w * overlay) * 100.0
        else:
            score = _num(row.get("cross_section_score")) or 0.0
        item = dict(row)
        item["stage2_alpha_overlay"] = round(score - (_num(row.get("cross_section_score")) or 0.0), 4)
        item["stage2_alpha_score"] = round(score, 4)
        out.append(item)
    out.sort(key=lambda x: (-x["stage2_alpha_score"], str(x.get("code", ""))))
    return out
