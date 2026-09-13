# -*- coding: utf-8 -*-
"""Lightweight, leakage-aware cross-sectional factor validation for A-shares.

The module expects point-in-time factor observations. Forward returns are built
strictly from later closes, so the observation at date t can never consume the
close at t+h as an input factor. It is intentionally dependency-free for the
8GB local runtime.
"""
from __future__ import annotations
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Sequence


def _num(v):
    try:
        if v in (None, "", "-"):
            return None
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _pearson(a: Sequence[float], b: Sequence[float]) -> float | None:
    if len(a) < 2:
        return None
    ma, mb = mean(a), mean(b)
    da = [x - ma for x in a]
    db = [y - mb for y in b]
    den = (sum(x*x for x in da) * sum(y*y for y in db)) ** 0.5
    return None if den == 0 else sum(x*y for x, y in zip(da, db, strict=True)) / den


def _rank(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j+1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def _icir(series: Sequence[float | None]) -> float | None:
    x = [v for v in series if v is not None]
    if len(x) < 2:
        return None
    sd = pstdev(x)
    return None if sd == 0 else mean(x) / sd


def build_forward_returns(rows: Iterable[Dict[str, Any]], horizons=(1, 3, 5, 10, 20)) -> List[Dict[str, Any]]:
    """Build future close-to-close returns by code/date without look-ahead leakage."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        code = str(row.get("code", ""))
        date = str(row.get("trade_date", row.get("date", "")))
        close = _num(row.get("close"))
        if code and date and close is not None and close > 0:
            item = dict(row)
            item["_date"] = date
            item["_close"] = close
            grouped.setdefault(code, []).append(item)
    out = []
    hs = tuple(int(h) for h in horizons if int(h) > 0)
    for _code, seq in grouped.items():
        seq.sort(key=lambda r: r["_date"])
        for i, row in enumerate(seq):
            item = dict(row)
            for h in hs:
                j = i + h
                item[f"forward_return_{h}d"] = (seq[j]["_close"] / row["_close"] - 1.0) if j < len(seq) else None
            item.pop("_date", None); item.pop("_close", None)
            out.append(item)
    return out


def validate_factor(rows: Iterable[Dict[str, Any]], factor: str, horizons=(1, 3, 5, 10, 20), min_assets=20) -> Dict[str, Any]:
    """Return cross-sectional IC/RankIC, ICIR and top-vs-bottom spread by horizon.

    Rows must contain code, trade_date/date, the factor, and close. The factor
    is read only at t; forward returns use closes strictly after t.
    """
    prepared = build_forward_returns(rows, horizons=horizons)
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for r in prepared:
        if _num(r.get(factor)) is not None:
            by_date.setdefault(str(r.get("trade_date", r.get("date", ""))), []).append(r)

    result: Dict[str, Any] = {"factor": factor, "observations": len(prepared), "dates": len(by_date), "horizons": {}}
    for h in horizons:
        ics: List[float] = []
        ranks: List[float] = []
        spreads: List[float] = []
        wins = 0
        valid_dates = 0
        for _date, group in sorted(by_date.items()):
            pairs = [(float(r[factor]), _num(r.get(f"forward_return_{h}d"))) for r in group]
            pairs = [(x, y) for x, y in pairs if y is not None]
            if len(pairs) < min_assets:
                continue
            xs, ys = zip(*pairs, strict=True)
            ic = _pearson(xs, ys)
            ric = _pearson(_rank(xs), _rank(ys))
            if ic is not None: ics.append(ic)
            if ric is not None: ranks.append(ric)
            ordered = sorted(pairs, key=lambda p: p[0])
            q = max(1, len(ordered) // 5)
            low = mean(y for _, y in ordered[:q])
            high = mean(y for _, y in ordered[-q:])
            spreads.append(high - low)
            wins += int(high > low)
            valid_dates += 1
        result["horizons"][str(h)] = {
            "valid_dates": valid_dates,
            "ic_mean": mean(ics) if ics else None,
            "rank_ic_mean": mean(ranks) if ranks else None,
            "icir": _icir(ics),
            "rank_icir": _icir(ranks),
            "ic_positive_ratio": (sum(v > 0 for v in ics) / len(ics)) if ics else None,
            "rank_ic_positive_ratio": (sum(v > 0 for v in ranks) / len(ranks)) if ranks else None,
            "top_bottom_spread_mean": mean(spreads) if spreads else None,
            "top_bottom_win_rate": wins / valid_dates if valid_dates else None,
        }
    return result
