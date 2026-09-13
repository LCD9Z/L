# -*- coding: utf-8 -*-
"""Phase 17: market-regime segmented validation."""
import statistics
from typing import Dict, List

def classify_return_regime(returns, threshold=0.01):
    out=[]
    for r in returns:
        x=float(r)
        out.append('bull' if x>threshold else 'bear' if x<-threshold else 'range')
    return out

def summarize_by_regime(returns, regimes):
    groups: Dict[str, List[float]]={}
    for r,g in zip(returns,regimes, strict=True): groups.setdefault(g,[]).append(float(r))
    return {g:{'count':len(v),'mean':round(statistics.mean(v),6),'positive_rate':round(sum(x>0 for x in v)/len(v),4)} for g,v in groups.items() if v}
