# -*- coding: utf-8 -*-
"""参数稳健性扫描：避免只依赖单一“最佳参数”。"""
def scan_thresholds(data, backtest_func, thresholds=range(55,81,5), **kwargs):
    rows=[]
    for t in thresholds:
        r=backtest_func(data, threshold=t, **kwargs)
        rows.append({'threshold':t,'return_pct':r.get('total_return_pct'),
                     'max_drawdown_pct':r.get('max_drawdown_pct'),
                     'sharpe':r.get('daily_sharpe'),'trades':r.get('trades')})
    return rows

def is_stable(rows, min_points=3):
    vals=[r['return_pct'] for r in rows if r.get('return_pct') is not None]
    if len(vals)<min_points: return False
    mean=sum(vals)/len(vals)
    spread=max(vals)-min(vals)
    return mean>0 and spread <= max(20.0, abs(mean)*2.5)
