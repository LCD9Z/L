"""Independent integrity checks for frozen real-data manifests."""
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path

def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_report(report):
    if not report.get('verified'): return {'passed':False,'reason':'report_not_verified'}
    path=report.get('path'); expected=report.get('sha256')
    if not path or not Path(path).exists(): return {'passed':False,'reason':'data_file_missing'}
    actual=sha256(path)
    if actual!=expected: return {'passed':False,'reason':'sha256_mismatch','expected':expected,'actual':actual}
    with open(path,encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
    if len(rows)!=int(report.get('rows',-1)): return {'passed':False,'reason':'row_count_mismatch'}
    dates=[r['date'] for r in rows]
    if dates!=sorted(dates) or len(dates)!=len(set(dates)): return {'passed':False,'reason':'date_integrity_failure'}
    return {'passed':True,'rows':len(rows),'sha256':actual}

def verify_manifest(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    results={r['symbol']:verify_report(r) for r in data.get('reports',[])}
    return {'passed':bool(results) and all(x['passed'] for x in results.values()),'results':results}
