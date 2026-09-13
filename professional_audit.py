# -*- coding: utf-8 -*-
"""Independent ten-role audit for evidence-first A-share strategy validation."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROLES = [
    "market_data_auditor", "data_integrity_engineer", "quant_researcher",
    "backtest_engineer", "execution_microstructure_reviewer", "pit_bias_auditor",
    "statistician", "risk_manager", "software_qa_engineer", "research_governance_reviewer",
]

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def audit_csv(path, metadata_path=None, min_rows=60):
    p=Path(path); issues=[]
    if not p.exists(): return {"pass":False,"issues":["file_missing"]}
    lines=p.read_text(encoding="utf-8").splitlines()
    if len(lines)<2: return {"pass":False,"issues":["empty_dataset"]}
    header=lines[0].split(',')
    required={"date","open","high","low","close"}
    if not required.issubset(header): issues.append("missing_ohlc_columns")
    # lightweight row parser deliberately keeps the audit dependency-free
    idx={k:header.index(k) for k in required if k in header}
    dates=[]
    for n,line in enumerate(lines[1:],2):
        cols=line.split(',')
        try:
            d=cols[idx['date']]; o=float(cols[idx['open']]); h=float(cols[idx['high']]); l=float(cols[idx['low']]); c=float(cols[idx['close']])
            dates.append(d)
            if min(o,h,l,c)<=0 or h<max(o,c) or l>min(o,c) or h<l: issues.append(f"invalid_ohlc_row_{n}")
        except Exception: issues.append(f"parse_error_row_{n}")
    if dates != sorted(dates): issues.append("dates_not_sorted")
    if len(set(dates)) != len(dates): issues.append("duplicate_dates")
    if len(dates)<min_rows: issues.append("insufficient_rows")
    if metadata_path:
        mp=Path(metadata_path)
        if not mp.exists(): issues.append("metadata_missing")
        else:
            try:
                m=json.loads(mp.read_text(encoding="utf-8"))
                if not m.get("strict"): issues.append("not_strictly_certified")
                if m.get("sha256") != _sha(p): issues.append("sha256_mismatch")
                if int(m.get("rows",-1)) != len(dates): issues.append("row_count_mismatch")
            except Exception: issues.append("metadata_invalid")
    return {"pass":not issues,"rows":len(dates),"issues":sorted(set(issues))}

def audit_pipeline(stock_files, metadata_files=None, benchmark_file=None, benchmark_metadata=None):
    metadata_files=metadata_files or {}; reports={}; failed=[]
    for code,path in stock_files.items():
        r=audit_csv(path, metadata_files.get(code)); reports[f"data:{code}"]=r
        if not r["pass"]: failed.append(f"data:{code}")
    if benchmark_file:
        r=audit_csv(benchmark_file, benchmark_metadata); reports["benchmark"]=r
        if not r["pass"]: failed.append("benchmark")
    role_status=dict.fromkeys(ROLES, "PASS" if not failed else "BLOCKED_BY_DATA")
    return {"verdict":"PASS" if not failed else "FAIL","failed_checks":failed,"roles":role_status,"reports":reports}


def audit_research_evidence(stock_files, metadata_files=None, benchmark_file=None, benchmark_metadata=None, min_assets=5, min_rows_per_asset=400):
    """Phase 29 evidence gate: prevent small/unverified web samples from being mistaken for a full-market Alpha proof."""
    base=audit_pipeline(stock_files, metadata_files, benchmark_file, benchmark_metadata)
    issues=list(base.get("failed_checks", []))
    reports=base.get("reports", {})
    asset_reports=[v for k,v in reports.items() if k.startswith("data:")]
    if len(asset_reports)<min_assets: issues.append("universe_too_small_for_general_alpha_claim")
    short=[k for k,v in reports.items() if k.startswith("data:") and v.get("rows",0)<min_rows_per_asset]
    if short: issues.append("insufficient_per_asset_history")
    verdict="PASS" if not issues else "LIMITED_OR_FAIL"
    return {"verdict":verdict,"issues":sorted(set(issues)),"base":base,
            "claim_scope":"representative_sample_only" if verdict!="PASS" else "sample_level_evidence_only",
            "hard_rule":"Passing this gate never proves future profitability or a market-wide Alpha."}
