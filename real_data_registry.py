# -*- coding: utf-8 -*-
"""Phase 22 real-data registry and point-in-time audit.

No provider data are fabricated here. A dataset must carry provenance and an
as-of/available timestamp. Data failing the audit are rejected from Alpha tests.
"""
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
from typing import Any, Dict, List

REQUIRED_FIELDS = {'date','code','open','high','low','close','volume'}

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def build_manifest(path, provider, dataset_type, available_at=None, adjusted=False, notes=''):
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(path)
    return {'path':str(p), 'sha256':sha256_file(p), 'provider':provider,
            'dataset_type':dataset_type, 'available_at':available_at,
            'adjusted':bool(adjusted), 'notes':notes}

def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if not rows: raise ValueError('empty dataset')
    missing=REQUIRED_FIELDS-set(rows[0])
    if missing: raise ValueError('missing required fields: '+','.join(sorted(missing)))
    return rows

def audit_price_dataset(path, manifest=None):
    rows=read_csv(path); errors: List[str]=[]; seen: set=set(); prev_by_code: Dict[str, Any]={}
    for i,r in enumerate(rows,2):
        key=(r['date'],r['code'])
        if key in seen: errors.append(f'line {i}: duplicate date/code')
        seen.add(key)
        try:
            vals=[float(r[x]) for x in ('open','high','low','close','volume')]
            if any(v < 0 for v in vals): errors.append(f'line {i}: negative value')
            if float(r['high']) < max(float(r['open']),float(r['close']),float(r['low'])): errors.append(f'line {i}: invalid high')
            if float(r['low']) > min(float(r['open']),float(r['close']),float(r['high'])): errors.append(f'line {i}: invalid low')
        except Exception: errors.append(f'line {i}: non-numeric OHLCV')
        prev=prev_by_code.get(r['code'])
        if prev and r['date'] <= prev: errors.append(f'line {i}: non-monotonic date for code')
        prev_by_code[r['code']]=r['date']
    if manifest and manifest.get('sha256') != sha256_file(path): errors.append('manifest checksum mismatch')
    return {'passed':not errors,'rows':len(rows),'errors':errors[:100]}

def save_manifest(manifest, path): Path(path).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
