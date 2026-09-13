# -*- coding: utf-8 -*-
"""Cross-sectional factor ranking, independent of pandas/numpy."""
from __future__ import annotations
from typing import Any, Dict, List


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


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


def rank_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank candidates cross-sectionally; lower volatility/drawdown are better.

    Missing factors do not receive fabricated values. The score is the mean of
    available ranked factors, with a small completeness penalty.
    """
    fields = {
        "momentum_5d": True,
        "momentum_20d": True,
        "realized_vol_20d": False,
        "drawdown_20d": True,  # closer to zero is better; rank lower is better
        "volume_ratio_5d": True,
        "amount_ratio_5d": True,
    }
    ranks = {f: _rank([_num((r.get("factors") or {}).get(f)) for r in rows], hi) for f, hi in fields.items()}
    out = []
    for i, row in enumerate(rows):
        vals = [ranks[f][i] for f in fields if ranks[f][i] is not None]
        completeness = len(vals) / len(fields)
        score = (sum(vals) / len(vals) * 100.0) if vals else 0.0
        score *= 0.90 + 0.10 * completeness
        item = dict(row)
        item["cross_section_score"] = round(score, 4)
        item["factor_completeness"] = round(completeness, 4)
        out.append(item)
    out.sort(key=lambda x: (-x["cross_section_score"], str(x.get("code", ""))))
    return out
