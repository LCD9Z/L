# -*- coding: utf-8 -*-
"""Phase 39 factor empirical validation runner.

Consumes point-in-time research rows (JSONL or CSV), validates only factors
that are actually present at sufficient coverage, then applies the Phase 38
pre-screen gate. No data is fabricated and no Alpha claim is made by this
runner; final acceptance remains subject to PIT audit, Walk-Forward, OOS and
A-share trading-cost validation.
"""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from factor_gate import gate_factors
from factor_registry import availability, select_available
from factor_validation import validate_factor


def _load_rows(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    rows: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_factor_lab(
    rows: Iterable[Dict[str, Any]],
    horizons=(1, 3, 5, 10, 20),
    min_coverage: float = 0.20,
    min_assets: int = 20,
    gate_horizon: int = 5,
) -> Dict[str, Any]:
    rows = list(rows)
    avail = availability(rows)
    selected = select_available(rows, min_coverage=min_coverage)
    validation: Dict[str, Dict[str, Any]] = {}
    for factor in selected:
        validation[factor] = validate_factor(rows, factor, horizons=horizons, min_assets=min_assets)
    gate = gate_factors(validation, rows=rows, horizon=gate_horizon)
    return {
        "status": "ok" if rows else "insufficient_data",
        "rows": len(rows),
        "candidate_count": len(avail),
        "available_factors": selected,
        "availability": avail,
        "validation": validation,
        "gate": gate,
        "decision": "INCONCLUSIVE" if not rows or not gate["selected"] else "PRE_SCREEN_PASS",
        "research_boundary": "Pre-screen only; final Alpha acceptance requires certified PIT data, Walk-Forward/OOS, costs, benchmark, and A-share execution constraints.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 39 A-share factor empirical validation")
    ap.add_argument("input", help="JSONL or CSV research rows")
    ap.add_argument("-o", "--output", default="factor_lab_report.json")
    ap.add_argument("--min-coverage", type=float, default=0.20)
    ap.add_argument("--min-assets", type=int, default=20)
    ap.add_argument("--gate-horizon", type=int, default=5)
    args = ap.parse_args()
    report = run_factor_lab(_load_rows(args.input), min_coverage=args.min_coverage, min_assets=args.min_assets, gate_horizon=args.gate_horizon)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "rows": report["rows"], "available_factors": report["available_factors"], "selected": report["gate"]["selected"], "decision": report["decision"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
