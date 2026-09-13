# -*- coding: utf-8 -*-
"""Simple deterministic stress tests; does not fabricate market data."""

def execution_stress(result, extra_slippage_bps=(0,5,10,20)):
    trades=max(int(result.get('trades',0)),0)
    base=float(result.get('total_return_pct',0.0))
    out=[]
    for bps in extra_slippage_bps:
        # Round-trip incremental cost approximation in percentage points.
        penalty=trades*2*bps/10000*100
        out.append({'extra_slippage_bps_per_side':bps,'approx_return_pct':round(base-penalty,3)})
    return {'assumption':'Approximate sensitivity only; re-run engine for authoritative result.','scenarios':out}
