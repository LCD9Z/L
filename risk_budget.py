# -*- coding: utf-8 -*-
"""Phase 16: simple volatility and concentration-aware position sizing."""

def inverse_vol_weights(volatilities, max_weight=0.35):
    vals={k:float(v) for k,v in volatilities.items() if v and float(v)>0}
    if not vals: return {}
    raw={k:1/v for k,v in vals.items()}; total=sum(raw.values())
    w={k:v/total for k,v in raw.items()}
    # iterative cap and redistribute
    for _ in range(len(w)+1):
        capped={k:min(v,max_weight) for k,v in w.items()}; rem=1-sum(capped.values())
        free=[k for k in w if w[k]<max_weight]
        if rem<=1e-12 or not free: return capped
        base=sum(raw[k] for k in free)
        if not base: return capped
        nw=dict(capped)
        for k in free: nw[k]+=rem*raw[k]/base
        if all(nw[k]<=max_weight+1e-12 for k in nw): return nw
        w=nw
    return w

def concentration_hhi(weights): return sum(float(w)**2 for w in weights.values())
