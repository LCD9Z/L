# -*- coding: utf-8 -*-
"""V3.7 two-level full-market screening with resumable checkpoints.

Pipeline:
  universe -> hard gates -> cross-sectional factors -> Top-N
  -> optional event/flow enrichment -> Top-M for AI deep review.

No LLM is called here.  This is intentional: AI is reserved for a small,
high-information candidate set.
"""
from __future__ import annotations
import json, os, time, tempfile
from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, Iterable, Optional

from ashare.ashare_universe import screen_row
from ashare.ashare_cross_section import rank_candidates
from stage2_scoring import rank_stage2_candidates


@dataclass
class ScreenConfig:
    stage1_keep: int = 300
    stage2_keep: int = 50
    ai_keep: int = 20
    min_amount: Optional[float] = None
    checkpoint_every: int = 250
    max_errors: int = 50


class CheckpointStore:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".checkpoint_", dir=os.path.dirname(os.path.abspath(self.path)))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _factor_row(row: Dict[str, Any]) -> Dict[str, Any]:
    q = row.get("quote") or row
    f = row.get("factors") or row.get("factor") or {}
    if "factors" in f:
        f = f["factors"]
    out = dict(row)
    out["factors"] = f
    out["screen"] = screen_row(row)
    amount = q.get("amount")
    if amount is not None:
        try:
            out["amount"] = float(amount)
        except (TypeError, ValueError):
            pass
    return out


def _atomic_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".json_", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def run_screen(universe: Iterable[Dict[str, Any]], out_dir: str,
               config: Optional[ScreenConfig] = None,
               enrich: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
               resume: bool = False) -> Dict[str, Any]:
    cfg = config or ScreenConfig()
    os.makedirs(out_dir, exist_ok=True)
    ck = CheckpointStore(os.path.join(out_dir, "checkpoint.json"))
    state = ck.load() if resume else {}
    rows = []
    counts = dict(state.get("counts", {"seen": 0, "eligible": 0, "errors": 0}))
    start = int(state.get("processed", 0)) if resume else 0
    # A checkpoint must preserve the already-screened rows; otherwise a resume
    # would silently re-rank only the tail of the universe.  The full A-share
    # universe is small enough for this durable JSON checkpoint and it also
    # keeps resume deterministic across process restarts.
    if resume:
        prior_rows = state.get("eligible_rows")
        if isinstance(prior_rows, list):
            rows.extend(prior_rows)

    for idx, raw in enumerate(universe):
        if idx < start:
            continue
        counts["seen"] += 1
        try:
            row = _factor_row(raw)
            if row["screen"]["eligible"]:
                amount = row.get("amount")
                if cfg.min_amount is not None and (amount is None or amount < cfg.min_amount):
                    continue
                counts["eligible"] += 1
                rows.append(row)
        except Exception as exc:
            counts["errors"] += 1
            if counts["errors"] > cfg.max_errors:
                raise RuntimeError(f"screening aborted: too many row errors; last={exc}") from exc
        processed = idx + 1
        if processed % max(1, cfg.checkpoint_every) == 0:
            ck.save({"version": 2, "processed": processed, "counts": counts,
                     "eligible_rows": rows, "updated_at": time.time()})

    ranked = rank_candidates(rows)
    stage1 = ranked[:cfg.stage1_keep]
    if enrich:
        enriched = []
        for row in stage1:
            try:
                x = dict(row); x.update(enrich(row) or {}); enriched.append(x)
            except Exception as exc:  # keep batch alive, preserve provenance
                x = dict(row); x["enrich_error"] = str(exc); enriched.append(x)
        stage2_ranked = rank_stage2_candidates(enriched)
    else:
        stage2_ranked = stage1
    stage2 = stage2_ranked[:cfg.stage2_keep]
    ai = stage2[:cfg.ai_keep]

    result = {
        "version": "3.7",
        "config": asdict(cfg),
        "counts": counts,
        "stage1": stage1,
        "stage2": stage2,
        "ai_candidates": ai,
        "resumable": True,
    }
    _atomic_json(os.path.join(out_dir, "screen_snapshot.json"), result)
    ck.save({"version": 2, "processed": counts["seen"], "counts": counts,
             "eligible_rows": rows, "status": "complete", "updated_at": time.time()})
    return result
