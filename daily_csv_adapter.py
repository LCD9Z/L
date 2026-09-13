# -*- coding: utf-8 -*-
"""Adapter for public daily-file A-share datasets (e.g. guidebee/china-stock-data).

The source format is one file per trading day, no header:
symbol,date,open,close,high,low,volume,amount

This adapter normalizes symbols without silently inventing turnover or corporate
-action fields. B-shares are excluded explicitly. It is a source adapter only;
it does not claim PIT universe coverage.
"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import Any, Dict, Iterator, List

_COLUMNS = ("symbol", "date", "open", "close", "high", "low", "volume", "amount")


def normalize_code(symbol: str) -> str:
    s = str(symbol or "").strip().lower()
    for p in ("sh", "sz", "bj"):
        if s.startswith(p):
            s = s[2:]
            break
    return s.zfill(6)


def is_ashare_code(code: str) -> bool:
    c = str(code).zfill(6)
    # Keep ordinary A-share prefixes, including Beijing 92xxxx; exclude SZ 20xxxx and SH 90xxxx B-shares.
    return c.startswith(("0", "3", "4", "6", "8")) or c.startswith("92")


def parse_row(fields: List[str]) -> Dict[str, Any]:
    if len(fields) != 8:
        raise ValueError(f"unexpected_field_count:{len(fields)}")
    symbol, date, opn, close, high, low, volume, amount = fields
    code = normalize_code(symbol)
    if not is_ashare_code(code):
        raise ValueError(f"non_ashare_symbol:{symbol}")
    return {
        "symbol": symbol.strip().lower(),
        "code": code,
        "date": date.strip(),
        "open": float(opn),
        "close": float(close),
        "high": float(high),
        "low": float(low),
        "volume": float(volume),
        "amount": float(amount),
    }


def iter_daily_file(path: str | Path, *, skip_b_shares: bool = True) -> Iterator[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            fields = next(csv.reader([line]))
            try:
                yield parse_row(fields)
            except ValueError as exc:
                if skip_b_shares and str(exc).startswith("non_ashare_symbol:"):
                    continue
                raise ValueError(f"{Path(path).name}:line={line_no}:{exc}") from exc


def iter_daily_dir(path: str | Path) -> Iterator[Dict[str, Any]]:
    """Iterate day files in lexical/date order, source remains one-row-per-stock/day."""
    root = Path(path)
    files = sorted(root.rglob("stock_price_????_??_??.csv"))
    for file in files:
        yield from iter_daily_file(file)
