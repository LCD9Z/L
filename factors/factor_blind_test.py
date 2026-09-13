# -*- coding: utf-8 -*-
"""Phase 45 streaming price-factor blind test.

Builds as-of-t factor observations and attaches T+h forward returns only when
those future bars arrive. No future value is used to construct the t factors.
Designed for day-file data and 8GB machines.
"""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict

from ashare.ashare_factor_engine import compute_factors
from daily_csv_adapter import parse_row

HORIZONS = (1, 3, 5, 10, 20)


def _day_files(root: Path):
    return sorted(root.rglob("stock_price_????_??_??.csv"))


def run_blind_test(root: str | Path, output: str | Path, *, min_history: int = 61, horizons=HORIZONS) -> Dict[str, Any]:
    root = Path(root); output = Path(output)
    files = _day_files(root)
    if not files:
        return {"status": "insufficient_data", "files": 0, "rows": 0}

    histories: Dict[str, deque] = defaultdict(lambda: deque(maxlen=min_history + 1))
    pending: Dict[str, deque] = defaultdict(deque)
    rows_written = 0; prices_seen = 0; b_excluded = 0; days = set(); symbols = set()
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as out:
        for file in files:
            for raw in file.read_text(encoding="utf-8-sig").splitlines():
                if not raw.strip():
                    continue
                try:
                    row = parse_row(next(csv.reader([raw])))
                except ValueError as exc:
                    if str(exc).startswith("non_ashare_symbol:"):
                        b_excluded += 1; continue
                    raise
                code, d, close = row["code"], row["date"], row["close"]
                prices_seen += 1; days.add(d); symbols.add(code)

                # Future-return completion uses only the newly arrived future bar.
                q = pending[code]
                if q:
                    keep: deque[Dict[str, Any]] = deque()
                    for obs in q:
                        delta = obs["age"] + 1
                        obs["age"] = delta
                        if delta in horizons and obs["close"] and close:
                            obs["fwd"][str(delta)] = close / obs["close"] - 1.0
                        if delta < max(horizons):
                            keep.append(obs)
                        else:
                            if all(str(h) in obs["fwd"] for h in horizons):
                                rec = dict(obs["factors"])
                                rec.update({"date": obs["date"], "code": code, "close": obs["close"], "forward_returns": obs["fwd"]})
                                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            elif delta >= max(horizons):
                                # Still emit partial horizons to preserve evidence; missing remains explicit.
                                rec = dict(obs["factors"])
                                rec.update({"date": obs["date"], "code": code, "close": obs["close"], "forward_returns": obs["fwd"]})
                                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            rows_written += 1
                    pending[code] = keep

                histories[code].append(row)
                if len(histories[code]) < min_history + 1:
                    continue
                pack = compute_factors(list(histories[code]))
                pending[code].append({
                    "date": d, "close": close, "age": 0,
                    "factors": pack.get("factors", {}), "fwd": {},
                })

    return {
        "status": "ok" if rows_written else "insufficient_data",
        "files": len(files), "days": len(days), "symbols": len(symbols),
        "prices_seen": prices_seen, "factor_rows": rows_written,
        "b_share_rows_excluded": b_excluded, "output": str(output),
        "horizons": list(horizons),
        "research_boundary": "Blind price-factor test only. No PIT universe/ST/suspension/delist/corporate-action certification and no final Alpha claim.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir"); ap.add_argument("-o", "--output", default="blind_factor_rows.jsonl")
    ap.add_argument("--min-history", type=int, default=61)
    args = ap.parse_args()
    report = run_blind_test(args.input_dir, args.output, min_history=args.min_history)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 2

if __name__ == "__main__":
    raise SystemExit(main())
