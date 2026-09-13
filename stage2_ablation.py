# -*- coding: utf-8 -*-
"""Lightweight Stage-2 ablation experiment runner for A-share research.

Each model is built cross-sectionally on date t only. Forward returns are
computed by factor_validation.py from later closes. The runner is intended to
answer one question: which Stage-2 information adds independent signal beyond
Stage-1, rather than merely making the score more complicated?
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Sequence

from factors.factor_validation import validate_factor


def _num(v):
    try:
        if v in (None, "", "-"):
            return None
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _cross_rank(values: Sequence[float | None]) -> List[float | None]:
    valid = sorted((v, i) for i, v in enumerate(values) if v is not None)
    out: List[float | None] = [None] * len(values)
    n = len(valid)
    if n == 0:
        return out
    if n == 1:
        out[valid[0][1]] = 0.5
        return out
    for pos, (_, idx) in enumerate(valid):
        out[idx] = pos / (n - 1)
    return out


def _field(row: Dict[str, Any], path: str):
    cur: Any = row
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    if path.endswith(".high_risk_flags") and isinstance(cur, list):
        return float(len(cur))
    return _num(cur)


# A factor is expressed as (path, higher_is_better).  We keep the first
# version deliberately small and interpretable; future factors can be added
# only after passing the ablation/OOS gate.
FACTOR_GROUPS = {
    "flow": [
        ("moneyflow.net_flow_mean", True),
        ("moneyflow.net_flow_positive_ratio", True),
    ],
    "top_list": [
        ("top_list.net_buy_total", True),
        ("top_list.net_buy_positive_ratio", True),
    ],
    "microstructure": [
        ("microstructure.max_limit_up_streak", True),
        ("microstructure.limit_down_days", False),
        ("microstructure.failed_limit_up_proxy_days", False),
    ],
    "event_risk": [
        ("event_risk.high_risk_count", False),
        ("event_risk.high_risk_flags", False),
    ],
}


def _score_group(rows: List[Dict[str, Any]], specs) -> List[float | None]:
    parts: List[List[float | None]] = []
    for path, higher in specs:
        vals = [_field(r, path) for r in rows]
        ranked = _cross_rank(vals)
        if not higher:
            ranked = [None if x is None else 1.0 - x for x in ranked]
        parts.append(ranked)
    out: List[float | None] = []
    for i in range(len(rows)):
        xs: List[float] = []
        for p in parts:
            v = p[i]
            if v is not None:
                xs.append(v)
        out.append(sum(xs) / len(xs) if xs else None)
    return out


def add_group_scores(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add date-wise Stage-2 group scores; no future data are consulted."""
    src = [dict(r) for r in rows]
    dates: Dict[str, List[int]] = {}
    for i, r in enumerate(src):
        d = str(r.get("trade_date", r.get("date", "")))
        dates.setdefault(d, []).append(i)

    for _, idxs in sorted(dates.items()):
        block = [src[i] for i in idxs]
        for group, specs in FACTOR_GROUPS.items():
            scores = _score_group(block, specs)
            for i, s in zip(idxs, scores, strict=True):
                src[i][f"ablation_{group}"] = s
        # Full Stage-2 uses equal group weights here. This is an experiment
        # harness, not the production scorer, so the weighting is explicit.
        groups = ["flow", "top_list", "microstructure", "event_risk"]
        for i in idxs:
            xs: List[float] = []
            for g in groups:
                v = src[i].get(f"ablation_{g}")
                if v is not None:
                    xs.append(float(v))
            src[i]["ablation_stage2_full"] = sum(xs) / len(xs) if xs else None
    return src


def _blend(base: float | None, overlay: float | None, weight: float) -> float | None:
    if base is None and overlay is None:
        return None
    if base is None:
        return overlay
    if overlay is None:
        return base
    return (1.0 - weight) * base + weight * overlay


def run_stage2_ablation(
    rows: Iterable[Dict[str, Any]],
    horizons=(1, 3, 5, 10, 20),
    min_assets: int = 20,
    overlay_weight: float = 0.35,
) -> Dict[str, Any]:
    """Validate Stage-1, each incremental group, and full Stage-2.

    Stage-1 is supplied by ``cross_section_score``. Incremental models are
    Stage-1 blended with one group; full Stage-2 blends all groups. This makes
    the experiment directly comparable with the production architecture.
    """
    src = add_group_scores(rows)
    base = []
    for r in src:
        x = dict(r)
        x["ablation_stage1"] = _num(x.get("cross_section_score"))
        base.append(x)

    models = {"stage1": "ablation_stage1"}
    for group in FACTOR_GROUPS:
        key = f"stage1_plus_{group}"
        models[key] = key
        for r in base:
            r[key] = _blend(r.get("ablation_stage1"), r.get(f"ablation_{group}"), overlay_weight)
    models["stage2_full"] = "stage2_full_score"
    for r in base:
        r["stage2_full_score"] = _blend(r.get("ablation_stage1"), r.get("ablation_stage2_full"), overlay_weight)

    report: Dict[str, Any] = {"overlay_weight": overlay_weight, "models": {}}
    for name, factor in models.items():
        report["models"][name] = validate_factor(base, factor, horizons=horizons, min_assets=min_assets)

    # Convenience deltas versus Stage-1. Keep them numeric only when both
    # sides have evidence; otherwise return None rather than manufacturing a 0.
    base_h = report["models"]["stage1"]["horizons"]
    for name, item in report["models"].items():
        if name == "stage1":
            continue
        for h, stats in item["horizons"].items():
            b = base_h.get(h, {})
            stats["delta_rank_ic_mean_vs_stage1"] = (
                stats["rank_ic_mean"] - b["rank_ic_mean"]
                if stats.get("rank_ic_mean") is not None and b.get("rank_ic_mean") is not None else None
            )
            stats["delta_top_bottom_spread_vs_stage1"] = (
                stats["top_bottom_spread_mean"] - b["top_bottom_spread_mean"]
                if stats.get("top_bottom_spread_mean") is not None and b.get("top_bottom_spread_mean") is not None else None
            )
    return report
