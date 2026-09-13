# -*- coding: utf-8 -*-
"""Phase 13 robustness, bootstrap and forward-window validation helpers."""
import random, statistics
from typing import Dict, List

def bootstrap_trade_returns(returns, iterations=1000, seed=42):
    vals=[float(x) for x in returns]
    if not vals: return {'iterations':0,'mean_return_pct':None,'p05_pct':None,'p50_pct':None,'p95_pct':None,'probability_positive':None}
    rng=random.Random(seed); totals=[]; n=len(vals)
    for _ in range(iterations):
        sample=[vals[rng.randrange(n)] for _ in range(n)]
        totals.append(sum(sample))
    totals.sort()
    def q(p): return totals[min(len(totals)-1, max(0, int((len(totals)-1)*p)))]
    return {'iterations':iterations,'mean_return_pct':round(statistics.mean(totals),4),'p05_pct':round(q(.05),4),'p50_pct':round(q(.5),4),'p95_pct':round(q(.95),4),'probability_positive':round(sum(x>0 for x in totals)/len(totals),4)}

def split_periods(bars, train_size, test_size, step=None):
    """Yield non-overlapping test windows after a rolling training history."""
    step=step or test_size
    start=0; out=[]
    while start+train_size+test_size <= len(bars):
        out.append({'train':bars[start:start+train_size], 'test':bars[start+train_size:start+train_size+test_size]})
        start += step
    return out

def parameter_surface(data, backtest_func, parameter_grid, metric='total_return_pct'):
    rows=[]
    for params in parameter_grid:
        result=backtest_func(data, **params)
        rows.append({'params':dict(params),'metric':result.get(metric),'trades':result.get('trades',0)})
    return rows

def regime_summary(results, regime_key='regime'):
    groups: Dict[str, List[float]]={}
    for r in results:
        groups.setdefault(r.get(regime_key,'unknown'),[]).append(float(r.get('return_pct',0)))
    return {k:{'count':len(v),'mean_return_pct':round(statistics.mean(v),4),'positive_rate':round(sum(x>0 for x in v)/len(v),4)} for k,v in groups.items() if v}
