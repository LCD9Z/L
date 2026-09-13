"""Phase 61: evidence-first corporate-action CSV ingestion and coverage audit.

Accepts a provider-exported CSV without requiring credentials in the research
runtime. The adapter never invents an ex-date and never treats a missing row as
an event. It is intentionally provider-neutral so Tushare/official exports can
be certified before entering the PIT factor lab.
"""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
from corporate_action_provider import normalize_tushare_dividend, audit_action_coverage


def read_codes_from_tdx(path: str | Path) -> set[str]:
    codes: set[str] = set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            code = str(row.get("code", "")).zfill(6)
            market = str(row.get("market", ""))
            c = code
            if ((market == "sh" and c.startswith(("600","601","603","605","688","689"))) or
                (market == "sz" and c.startswith(("000","001","002","003","300","301","302"))) or
                (market == "bj" and c.startswith(("43","83","87","88","92")))):
                codes.add(c)
    return codes


def read_tushare_csv(path: str | Path):
    actions = []
    rejected = 0
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            a = normalize_tushare_dividend(row)
            if a is None:
                rejected += 1
            else:
                actions.append(a)
    return actions, rejected


def audit(tdx_path: str | Path, action_csv: str | Path, out: str | Path) -> dict:
    requested = read_codes_from_tdx(tdx_path)
    actions, rejected = read_tushare_csv(action_csv)
    a = audit_action_coverage(requested, actions)
    dates = sorted({x.ex_date for x in actions})
    report = {
        "status": "complete" if a.has_complete_coverage else "incomplete",
        "requested_stock_codes": len(requested),
        "returned_action_codes": a.returned_codes,
        "event_rows": a.event_rows,
        "rejected_rows": rejected,
        "coverage_ratio": a.returned_codes / len(requested) if requested else 0.0,
        "earliest_ex_date": dates[0] if dates else None,
        "latest_ex_date": dates[-1] if dates else None,
        "missing_codes_count": len(a.missing_codes),
        "missing_codes_sample": list(a.missing_codes[:50]),
        "alpha_claim_eligible": False,
        "reason": "complete corporate-action history is not certified merely by row coverage; PIT publication/as-of evidence and lifecycle coverage are still required",
    }
    Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("tdx_csv")
    p.add_argument("action_csv")
    p.add_argument("-o", "--output", default="PHASE61_CORPORATE_ACTION_COVERAGE.json")
    args = p.parse_args()
    print(json.dumps(audit(args.tdx_csv, args.action_csv, args.output), ensure_ascii=False, indent=2))
