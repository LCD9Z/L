# -*- coding: utf-8 -*-
"""Evidence-based factor gate: quality + redundancy, not blind factor stacking."""
from __future__ import annotations
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence

from data_contracts import to_float_or_none as _num  # noqa: F401 — 唯一标准实现（CODE_REDUNDANCY_AUDIT P1）


def _pearson(a: Sequence[float], b: Sequence[float]):
    if len(a) < 2:
        return None
    ma, mb = mean(a), mean(b)
    da = [x - ma for x in a]; db = [y - mb for y in b]
    den = (sum(x*x for x in da) * sum(y*y for y in db)) ** 0.5
    return None if den == 0 else sum(x*y for x, y in zip(da, db, strict=True)) / den


def correlation_matrix(rows: Iterable[Dict[str, Any]], factors: List[str]) -> Dict[str, Dict[str, float | None]]:
    rows = list(rows)
    out: Dict[str, Dict[str, float | None]] = {a: {} for a in factors}
    for i, a in enumerate(factors):
        for b in factors[i:]:
            pairs = [(_num(r.get(a)), _num(r.get(b))) for r in rows]
            pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
            # 下一行的 if 是**类型窄化**（pairs 已过滤 None，运行时 no-op）——
            # to_float_or_none 有返回类型标注后，mypy 不再把 _num 结果当 Any。
            c = (_pearson([x for x, _ in pairs if x is not None],
                          [y for _, y in pairs if y is not None])
                 if len(pairs) >= 2 else None)
            out[a][b] = c; out[b][a] = c
    return out


def gate_factors(
    validation: Dict[str, Dict[str, Any]],
    rows: Iterable[Dict[str, Any]] | None = None,
    horizon: int = 5,
    min_rank_ic: float = 0.02,
    min_rank_icir: float = 0.30,
    min_positive_ratio: float = 0.52,
    corr_cutoff: float = 0.80,
) -> Dict[str, Any]:
    """Return keep/reject/watch decisions.

    Thresholds are deliberately softer than production targets. The gate is a
    screening device; final acceptance still requires Walk-Forward + OOS + cost.
    """
    scored: List[Dict[str, Any]] = []
    for name, report in validation.items():
        h = (report.get("horizons") or {}).get(str(horizon), {})
        ric = _num(h.get("rank_ic_mean")); rir = _num(h.get("rank_icir")); pos = _num(h.get("rank_ic_positive_ratio"))
        spread = _num(h.get("top_bottom_spread_mean"))
        if ric is None or rir is None or pos is None:
            decision = "watch"
            reason = "证据不足"
        elif ric >= min_rank_ic and rir >= min_rank_icir and pos >= min_positive_ratio and (spread is None or spread > 0):
            decision = "pass"
            reason = "RankIC/IR/胜率达到预筛门槛"
        else:
            decision = "reject"
            reason = "未达到预筛门槛"
        scored.append({"factor": name, "rank_ic": ric, "rank_icir": rir, "positive_ratio": pos, "spread": spread, "decision": decision, "reason": reason})

    passed = [x["factor"] for x in scored if x["decision"] == "pass"]
    pruned = []
    if rows is not None and len(passed) > 1:
        corr = correlation_matrix(rows, passed)
        # Keep the stronger factor when two factors are highly redundant.
        rank = {x["factor"]: (x["rank_icir"] or -999, x["rank_ic"] or -999) for x in scored}
        keep: List[str] = []
        for f in sorted(passed, key=lambda n: rank[n], reverse=True):
            if any(abs(corr.get(f, {}).get(k) or 0) >= corr_cutoff for k in keep):
                pruned.append(f)
            else:
                keep.append(f)
        passed = keep

    return {"selected": passed, "pruned_redundant": pruned, "all": scored, "horizon": horizon}
