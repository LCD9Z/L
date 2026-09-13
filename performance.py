# -*- coding: utf-8 -*-
"""回测绩效指标，避免只看收益率。"""
import math, statistics

def metrics(equity_curve, periods_per_year=252, risk_free_rate=0.0):
    eq=[float(x['equity']) for x in equity_curve if x.get('equity') is not None]
    if len(eq)<2: return {'observations':len(eq),'cagr_pct':None,'volatility_pct':None,'sharpe':None,'max_drawdown_pct':0.0}
    rets=[eq[i]/eq[i-1]-1 for i in range(1,len(eq)) if eq[i-1]>0]
    peak=eq[0]; mdd=0.0
    for x in eq: peak=max(peak,x); mdd=max(mdd,(peak-x)/peak if peak else 0)
    n=len(rets); years=n/periods_per_year
    cagr=(eq[-1]/eq[0])**(1/years)-1 if years>0 and eq[0]>0 else None
    vol=statistics.pstdev(rets)*math.sqrt(periods_per_year) if len(rets)>1 else 0.0
    excess=statistics.mean(rets)-risk_free_rate/periods_per_year if rets else 0
    sharpe=excess/(statistics.pstdev(rets) or 1e-12)*math.sqrt(periods_per_year) if len(rets)>1 else None
    return {'observations':len(eq),'cagr_pct':round(cagr*100,3) if cagr is not None else None,'volatility_pct':round(vol*100,3),'sharpe':round(sharpe,3) if sharpe is not None else None,'max_drawdown_pct':round(mdd*100,3)}
