# -*- coding: utf-8 -*-
"""Historical universe helpers for A-share portfolio research.
A point-in-time universe must be supplied by the caller when available; this module
never silently assumes today's watchlist represents the past."""
import json
from pathlib import Path


def load_codes(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(data,dict):
        data=data.get('stocks') or data.get('codes') or data.get('items') or []
    out=[]
    for x in data:
        c=x.get('code') if isinstance(x,dict) else x
        if c is not None: out.append(str(c).zfill(6))
    return sorted(set(out))


def validate_snapshot_map(snapshot_map):
    if not isinstance(snapshot_map, dict):
        raise TypeError('snapshot_map must be {YYYY-MM-DD: [codes]}')
    for d, codes in snapshot_map.items():
        if not isinstance(codes, list):
            raise ValueError(f'snapshot {d} must contain a list of codes')


def point_in_time_universe(snapshot_map, date):
    """snapshot_map: {YYYY-MM-DD: [codes]}; return latest snapshot <= date."""
    validate_snapshot_map(snapshot_map)
    eligible=[d for d in snapshot_map if str(d)<=str(date)]
    if not eligible: return []
    return list(snapshot_map[max(eligible)])
