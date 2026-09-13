# -*- coding: utf-8 -*-
"""Phase 14 research-integrity utilities: deterministic fingerprints and provenance."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone

def canonical_hash(obj):
    payload=json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def build_manifest(*, strategy_config=None, universe=None, bars=None, code_version='phase14'):
    return {
        'schema_version':'1.0',
        'code_version':code_version,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'strategy_config_sha256':canonical_hash(strategy_config or {}),
        'universe_sha256':canonical_hash(universe or []),
        'bars_sha256':canonical_hash(bars or []),
        'reproducibility_note':'A matching manifest proves identical inputs/configuration, not economic validity.'
    }

def assert_manifest_match(expected, actual, keys=('strategy_config_sha256','universe_sha256','bars_sha256')):
    mismatches=[k for k in keys if expected.get(k)!=actual.get(k)]
    return {'ok':not mismatches,'mismatches':mismatches}
