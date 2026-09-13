# -*- coding: utf-8 -*-
"""Phase 43 price-factor reconnaissance on real daily files.

This mode intentionally does NOT claim final Alpha validity: it has no PIT
security-master, ST/suspension history, delisting completeness, or corporate
-action normalization guarantee. It is a data reconnaissance / factor-shape
check only.

Memory model: process one symbol at a time using an in-memory rolling window
and write observations incrementally. Suitable for an 8GB machine.
"""
from __future__ import annotations
import argparse, json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List

from ashare_factor_engine import compute_factors


def _day_files(root: Path) -> List[Path]:
    return sorted(root.rglob("stock_price_????_??_??.csv"))


def build_recon_rows(root: str | Path, output: str | Path, *, min_history: int = 61) -> Dict[str, Any]:
    root = Path(root); out = Path(output)
    files = _day_files(root)
    if not files:
        return {"status": "insufficient_data", "files": 0, "rows": 0}
    histories: Dict[str, deque] = defaultdict(lambda: deque(maxlen=min_history + 1))
    rows_written = 0; symbols = set(); days = set(); b_excluded = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for file in files:
            for line in file.read_text(encoding="utf-8-sig").splitlines():
                if not line.strip():
                    continue
                try:
                    fields = __import__("csv").reader([line])
                    row = __import__("daily_csv_adapter", fromlist=["parse_row"]).parse_row(next(fields))
                except ValueError as exc:
                    if str(exc).startswith("non_ashare_symbol:"):
                        b_excluded += 1
                        continue
                    raise
                code = row["code"]; symbols.add(code); days.add(row["date"])
                histories[code].append(row)
                if len(histories[code]) < min_history + 1:
                    continue
                pack = compute_factors(list(histories[code]))
                obs = {"date": row["date"], "code": code, "close": row["close"]}
                obs.update(pack.get("factors", {}))
                f.write(json.dumps(obs, ensure_ascii=False) + "\n")
                rows_written += 1
    return {
        "status": "ok" if rows_written else "insufficient_data",
        "files": len(files), "days": len(days), "symbols": len(symbols),
        "factor_rows": rows_written, "b_share_rows_excluded": b_excluded,
        "output": str(out),
        "research_boundary": "Recon only; no PIT universe, ST/suspension history, delist completeness, corporate-action audit, costs or OOS validation.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="A-share real daily-file price factor reconnaissance")
    ap.add_argument("input_dir")
    ap.add_argument("-o", "--output", default="recon_factor_rows.jsonl")
    ap.add_argument("--min-history", type=int, default=61)
    args = ap.parse_args()
    report = build_recon_rows(args.input_dir, args.output, min_history=args.min_history)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 2

if __name__ == "__main__":
    raise SystemExit(main())
