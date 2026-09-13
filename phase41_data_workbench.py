# -*- coding: utf-8 -*-
"""Phase 41: memory-bounded real A-share research data workbench.

Pipeline:
certified per-stock CSV -> PIT membership filter -> rolling factors -> JSONL rows.
No current-universe substitution and no synthetic factor fill.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from ashare_factor_engine import compute_factors
from historical_universe import point_in_time_universe
from pit_integrity import audit_pit_rows
from real_data_integrity import verify_report


_REQUIRED = ("date", "open", "close", "high", "low", "volume")


def _load_stock_csv(path: str | Path) -> List[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    missing = [x for x in _REQUIRED if not rows or x not in rows[0]]
    if missing:
        raise ValueError(f"missing_columns:{','.join(missing)}")
    out = []
    for r in rows:
        row = dict(r)
        for k in ("open", "close", "high", "low", "volume", "amount", "turnover"):
            if row.get(k) in (None, "", "-"):
                row[k] = None
            elif k in row:
                row[k] = float(row[k])
        out.append(row)
    return sorted(out, key=lambda x: str(x["date"]))


def build_factor_rows_for_stock(code: str, bars: List[dict], pit_map: Dict[str, List[str]], min_history: int = 61) -> List[dict]:
    """Process one stock at a time to stay friendly to an 8GB machine."""
    rows: List[dict] = []
    ordered = sorted(bars, key=lambda x: str(x["date"]))
    for idx in range(max(0, min_history), len(ordered)):
        b = ordered[idx]
        d = str(b["date"])
        try:
            allowed = set(point_in_time_universe(pit_map, d))
        except Exception:
            allowed = set()
        if code not in allowed:
            continue
        window = ordered[max(0, idx - min_history): idx + 1]
        pack = compute_factors(window)
        row = {"date": d, "code": code, "close": float(b["close"])}
        row.update(pack.get("factors", {}))
        rows.append(row)
    return rows


def run_workbench(
    stock_files: Dict[str, str],
    reports: Dict[str, dict],
    pit_map: Dict[str, List[str]],
    output_jsonl: str | Path,
    *,
    min_history: int = 61,
) -> Dict[str, Any]:
    if not stock_files:
        return {"status": "insufficient_data", "stocks": 0, "factor_rows": 0}
    required_dates: List[str] = []
    for path in stock_files.values():
        rows = _load_stock_csv(path)
        required_dates.extend(str(r["date"]) for r in rows if str(r["date"]))
    coverage = {"required_dates": len(set(required_dates)), "missing_snapshot_dates": [d for d in sorted(set(required_dates)) if d not in pit_map]}
    if coverage["missing_snapshot_dates"]:
        return {"status": "INCONCLUSIVE", "reason": "pit_snapshot_coverage_gap", "coverage": coverage}

    out = Path(output_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    per_stock = {}
    with out.open("w", encoding="utf-8") as f:
        for code, path in sorted(stock_files.items()):
            report = reports.get(code)
            if report is not None:
                vr = verify_report(report)
                if not vr["passed"]:
                    return {"status": "INCONCLUSIVE", "reason": "certified_file_verification_failed", "code": code, "detail": vr}
            bars = _load_stock_csv(path)
            audit = audit_pit_rows(
                [{"code": code, **b} for b in bars],
                cutoff=None,
                require_timestamp=False,
            )
            if not audit["ok"]:
                return {"status": "INCONCLUSIVE", "reason": "pit_integrity_failed", "code": code, "detail": audit}
            rows = build_factor_rows_for_stock(code, bars, pit_map, min_history=min_history)
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            total += len(rows)
            per_stock[code] = len(rows)
    return {"status": "ok", "stocks": len(stock_files), "factor_rows": total, "per_stock": per_stock, "output": str(out)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 41 real A-share factor workbench")
    ap.add_argument("--stock-map", required=True, help="JSON mapping code -> certified CSV path")
    ap.add_argument("--pit-map", required=True, help="JSON mapping trade date -> active codes")
    ap.add_argument("-o", "--output", default="research_factor_rows.jsonl")
    ap.add_argument("--min-history", type=int, default=61)
    args = ap.parse_args()
    stock_map = json.loads(Path(args.stock_map).read_text(encoding="utf-8"))
    pit_map = json.loads(Path(args.pit_map).read_text(encoding="utf-8"))
    report = run_workbench(stock_map, {}, pit_map, args.output, min_history=args.min_history)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
