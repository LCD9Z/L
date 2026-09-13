# -*- coding: utf-8 -*-
"""Immutable experiment specification for Phase 22 Alpha trials."""
from __future__ import annotations
import hashlib,json
from pathlib import Path

REQUIRED={'name','strategy_version','data_manifest_hashes','oos_start','oos_end','benchmarks','entry_rules','exit_rules','cost_model','alpha_gate'}

def canonical(spec): return json.dumps(spec,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def spec_hash(spec): return hashlib.sha256(canonical(spec).encode()).hexdigest()
def validate(spec):
    missing=REQUIRED-set(spec)
    if missing: raise ValueError('missing preregistration fields: '+','.join(sorted(missing)))
    if not spec['benchmarks']: raise ValueError('at least one benchmark required')
    return True

def save(spec,path):
    validate(spec); payload={'spec':spec,'sha256':spec_hash(spec)}
    Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); return payload

def load_and_verify(path):
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    validate(payload['spec'])
    if payload.get('sha256') != spec_hash(payload['spec']): raise ValueError('preregistration was modified')
    return payload
