# -*- coding: utf-8 -*-
"""Bounded-memory Top-K heap for market-wide screening."""
from __future__ import annotations
import heapq
from typing import Any, Callable, Iterable, List


class TopK:
    def __init__(self, k: int, key: Callable[[Any], float]):
        if k < 1:
            raise ValueError("k must be >= 1")
        self.k = k
        self.key = key
        self._heap: list = []
        self._seq = 0

    def push(self, item: Any) -> None:
        self._seq += 1
        score = float(self.key(item))
        entry = (score, self._seq, item)
        if len(self._heap) < self.k:
            heapq.heappush(self._heap, entry)
        elif score > self._heap[0][0]:
            heapq.heapreplace(self._heap, entry)

    def extend(self, items: Iterable[Any]) -> None:
        for item in items:
            self.push(item)

    def items(self) -> List[Any]:
        return [x[2] for x in sorted(self._heap, key=lambda x: (-x[0], x[1]) )]
