# -*- coding: utf-8 -*-
"""Benchmark and excess-return analytics without third-party dependencies."""
import math, statistics

def _clean_curve(curve):
    return [(str(x['date']), float(x['equity'])) for x in curve if x.get('date') is not None and x.get('equity') not in (None,0)]

def _returns(curve):
    pts=_clean_curve(curve)
    return {pts[i][0]: pts[i][1]/pts[i-1][1]-1 for i in range(1,len(pts)) if pts[i-1][1] > 0}

def benchmark_metrics(strategy_curve, benchmark_bars, annualization=252):
    """Compare strategy equity curve with benchmark close series on common dates."""
    sret=_returns(strategy_curve)
    bpts=[(str(b['date']), float(b['close'])) for b in benchmark_bars if b.get('date') is not None and b.get('close') not in (None,0)]
    bret={bpts[i][0]: bpts[i][1]/bpts[i-1][1]-1 for i in range(1,len(bpts)) if bpts[i-1][1] > 0}
    dates=sorted(set(sret)&set(bret))
    if len(dates)<2:
        return {'common_periods':len(dates),'alpha_annualized_pct':None,'beta':None,'information_ratio':None,'excess_return_pct':None}
    sr=[sret[d] for d in dates]; br=[bret[d] for d in dates]
    bm=statistics.mean(br); sm=statistics.mean(sr)
    var_b=statistics.pvariance(br) if len(br)>1 else 0
    cov=sum((x-sm)*(y-bm) for x,y in zip(sr,br, strict=True))/len(sr)
    beta=cov/var_b if var_b else None
    alpha_daily=sm-(beta*bm if beta is not None else bm)
    excess=[x-y for x,y in zip(sr,br, strict=True)]
    tracking=statistics.pstdev(excess) if len(excess)>1 else 0
    ir=statistics.mean(excess)/tracking*math.sqrt(annualization) if tracking else None
    strat_growth=math.prod(1+x for x in sr)-1
    bench_growth=math.prod(1+x for x in br)-1
    return {'common_periods':len(dates),'strategy_return_pct':round(strat_growth*100,3),'benchmark_return_pct':round(bench_growth*100,3),'excess_return_pct':round((strat_growth-bench_growth)*100,3),'alpha_annualized_pct':round(alpha_daily*annualization*100,3),'beta':round(beta,4) if beta is not None else None,'information_ratio':round(ir,4) if ir is not None else None}
