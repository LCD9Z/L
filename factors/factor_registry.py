# -*- coding: utf-8 -*-
"""A-share candidate factor registry and lightweight factor gate.

The registry separates *what we want to test* from *what the current data can
actually support*. No unavailable fundamental/event factor is silently filled.
Designed for the 8GB local research workflow.
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List


CANDIDATE_FACTORS: List[Dict[str, Any]] = [
    # Price / momentum
    {"name": "momentum_5d", "group": "momentum", "direction": 1, "source": "bars"},
    {"name": "momentum_10d", "group": "momentum", "direction": 1, "source": "bars"},
    {"name": "momentum_20d", "group": "momentum", "direction": 1, "source": "bars"},
    {"name": "momentum_60d", "group": "momentum", "direction": 1, "source": "bars"},
    {"name": "momentum_accel_5_20", "group": "momentum", "direction": 1, "source": "bars"},
    {"name": "breakout_20d", "group": "momentum", "direction": 1, "source": "bars"},
    # Risk / volatility
    {"name": "realized_vol_20d", "group": "risk", "direction": -1, "source": "bars"},
    {"name": "realized_vol_60d", "group": "risk", "direction": -1, "source": "bars"},
    {"name": "drawdown_20d", "group": "risk", "direction": 1, "source": "bars"},
    {"name": "range_pct_20d", "group": "risk", "direction": -1, "source": "bars"},
    # Liquidity / volume
    {"name": "volume_ratio_5d", "group": "liquidity", "direction": 1, "source": "bars"},
    {"name": "volume_ratio_20d", "group": "liquidity", "direction": 1, "source": "bars"},
    {"name": "amount_ratio_5d", "group": "liquidity", "direction": 1, "source": "bars"},
    {"name": "turnover_mean_20d", "group": "liquidity", "direction": 1, "source": "bars"},
    # Fundamentals: registry only until PIT snapshot provider is connected
    {"name": "pe_ttm", "group": "valuation", "direction": -1, "source": "pit_fundamentals"},
    {"name": "pb", "group": "valuation", "direction": -1, "source": "pit_fundamentals"},
    {"name": "ps_ttm", "group": "valuation", "direction": -1, "source": "pit_fundamentals"},
    {"name": "roe", "group": "quality", "direction": 1, "source": "pit_fundamentals"},
    {"name": "net_profit_growth", "group": "growth", "direction": 1, "source": "pit_fundamentals"},
    {"name": "operating_cashflow_growth", "group": "quality", "direction": 1, "source": "pit_fundamentals"},
    # A-share specific event / positioning inputs
    {"name": "margin_balance_change", "group": "ashare_event", "direction": 1, "source": "margin_history"},
    {"name": "unlock_ratio_20d", "group": "ashare_event", "direction": -1, "source": "unlock_history"},
    {"name": "insider_net_buy", "group": "ashare_event", "direction": 1, "source": "insider_history"},
    {"name": "pledge_ratio", "group": "ashare_event", "direction": -1, "source": "pledge_history"},
]


def registry() -> List[Dict[str, Any]]:
    return [dict(x) for x in CANDIDATE_FACTORS]


def availability(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    rows = list(rows)
    out = {}
    for spec in CANDIDATE_FACTORS:
        vals = []
        for row in rows:
            v = row.get(spec["name"])
            if v is not None:
                try:
                    x = float(v)
                    if x == x:
                        vals.append(x)
                except (TypeError, ValueError):
                    pass
        out[spec["name"]] = {
            "group": spec["group"],
            "source": spec["source"],
            "direction": spec["direction"],
            "available_rows": len(vals),
            "available_ratio": len(vals) / len(rows) if rows else 0.0,
            "status": "available" if vals else "missing_source",
        }
    return out


def select_available(rows: Iterable[Dict[str, Any]], min_coverage: float = 0.20) -> List[str]:
    info = availability(rows)
    return [name for name, meta in info.items() if meta["available_ratio"] >= min_coverage]
