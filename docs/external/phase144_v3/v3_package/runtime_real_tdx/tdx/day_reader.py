# -*- coding: utf-8 -*-
"""Memory-conscious reader for TongdaXin .day daily bars."""
from __future__ import annotations
import struct
from pathlib import Path
from typing import Dict, Iterator, List, Optional

REC = struct.Struct('<IIIIIfII')
SIZE = 32

STOCK_PREFIXES = {'600','601','603','605','688','689','000','001','002','003','300','301','430','920'}
BJ_OLD = list(range(830,840)) + list(range(870,874))


def classify(code: str, market: str) -> str:
    code = str(code).zfill(6)
    m = market.lower()
    p3 = code[:3]
    if m == 'sh' and code in {'000001','000300','000905','000016','000688'}:
        return 'index'
    if m == 'sz' and p3 == '399':
        return 'index'
    if p3 in STOCK_PREFIXES:
        return 'stock'
    try:
        if int(p3) in BJ_OLD:
            return 'stock'
    except ValueError:
        pass
    if code[:2] in {'15','16'} or p3 in {'501','502','510','511','512','513','515','516','518','520','560','561','562','563','588','589','159'}:
        return 'fund'
    if code[:2] in {'11','12','13'}:
        return 'bond'
    return 'other'


def parse_file(path: Path, limit: Optional[int] = None) -> Iterator[Dict]:
    size = path.stat().st_size
    if size % SIZE != 0:
        raise ValueError(f'bad_size_not_multiple_of_32:{path}:{size}')
    count = size // SIZE
    start = max(0, count - limit) if limit else 0
    with path.open('rb') as f:
        f.seek(start * SIZE)
        for _ in range(count - start):
            raw = f.read(SIZE)
            if len(raw) != SIZE:
                break
            date, op, hi, lo, cl, amount, volume, reserved = REC.unpack(raw)
            yield {
                'date': int(date), 'open': op / 100.0, 'high': hi / 100.0,
                'low': lo / 100.0, 'close': cl / 100.0,
                'amount': float(amount), 'volume': float(volume), 'reserved': reserved,
            }


def latest_bars(path: Path, n: int = 40) -> List[Dict]:
    return list(parse_file(path, limit=n))


def scan(root: Path):
    rows = []
    for market in ('sh','sz','bj'):
        d = root / market / 'lday'
        if not d.exists():
            continue
        for p in d.glob('*.day'):
            code = p.stem[-6:]
            if len(code) != 6 or classify(code, market) != 'stock':
                continue
            rows.append((market, code, p))
    return rows
