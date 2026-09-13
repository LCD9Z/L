# -*- coding: utf-8 -*-
"""Phase 9: robust backtest diagnostics: CAGR, benchmark excess and regime slices."""
import math, statistics
from typing import Dict, List

def _returns(curve):
    return [(curve[i]['date'], curve[i]['equity']/curve[i-1]['equity']-1) for i in range(1,len(curve)) if curve[i-1]['equity']>0]

def _cagr(curve):
    if len(curve)<2 or curve[0]['equity']<=0:return None
    years=max((len(curve)-1)/252,1/252)
    return (curve[-1]['equity']/curve[0]['equity'])**(1/years)-1

def evaluate_backtest(result, benchmark_curve=None, regime_by_date=None):
    curve=result.get('equity_curve',[]); rets=_returns(curve)
    out={'cagr_pct': round(_cagr(curve)*100,3) if _cagr(curve) is not None else None,
         'observations':len(curve)}
    if rets:
        vals=[x[1] for x in rets]; downside=[min(0,x) for x in vals]
        out['volatility_pct']=round(statistics.pstdev(vals)*math.sqrt(252)*100,3) if len(vals)>1 else 0
        dstd=math.sqrt(sum(x*x for x in downside)/len(downside))
        out['sortino']=round(statistics.mean(vals)/(dstd or 1e-12)*math.sqrt(252),3)
    if benchmark_curve and len(benchmark_curve)>=2:
        b0=benchmark_curve[0].get('close') or benchmark_curve[0].get('equity'); b1=benchmark_curve[-1].get('close') or benchmark_curve[-1].get('equity')
        if b0 and b1:
            br=b1/b0-1; out['benchmark_return_pct']=round(br*100,3); out['excess_return_pct']=round(result.get('total_return_pct',0)-br*100,3)
    if regime_by_date:
        buckets: Dict[str, List[float]]={}
        for i in range(1,len(curve)):
            reg=regime_by_date.get(str(curve[i]['date']),'UNKNOWN'); prev=curve[i-1]['equity']; cur=curve[i]['equity']
            if prev>0: buckets.setdefault(reg,[]).append(cur/prev-1)
        out['regime_slices']={k:{'days':len(v),'return_pct':round((math.prod([1+x for x in v])-1)*100,3),
                                 'daily_sharpe':round(statistics.mean(v)/(statistics.pstdev(v) or 1e-12)*math.sqrt(252),3) if len(v)>1 else None}
                              for k,v in buckets.items()}
    return out
