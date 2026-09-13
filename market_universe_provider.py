# -*- coding: utf-8 -*-
"""A-share universe provider contracts.

The live adapter is deliberately not bundled with a hard-coded crawler.  A
provider must return rows that are already as-of the requested cutoff.  This
keeps PIT semantics explicit and lets users plug in Tushare/TDX/other sources.
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, Iterator, Optional, Protocol


class UniverseProvider(Protocol):
    def iter_rows(self, asof: Optional[str] = None, batch_size: int = 500) -> Iterable[Dict[str, Any]]: ...


def iter_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    """Stream JSONL universe rows without loading the whole market into RAM."""
    import json
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row
