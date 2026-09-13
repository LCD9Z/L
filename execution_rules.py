# -*- coding: utf-8 -*-
"""Shared A-share execution realism helpers used by all backtests."""
from backtest_engine import _is_unsellable_limit


def first_sellable_index(code, bars, due_index):
    """Return first executable sell bar on/after due_index, or None.

    A locked limit-down bar cannot be assumed executable.  The position is held
    until a later sellable trading day, avoiding optimistic forced exits.
    """
    start=max(0, int(due_index))
    for i in range(start, len(bars)):
        prev_close = float(bars[i-1]['close']) if i > 0 else None
        if prev_close is not None and _is_unsellable_limit(bars[i], prev_close, code):
            continue
        return i
    return None
