# -*- coding: utf-8 -*-
"""A股策略风控层：市场环境、ATR、仓位与交易可执行性。"""

def _ma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None

def atr(rows, n=14):
    if len(rows) < n + 1:
        return None
    trs=[]
    prev=rows[-n-1].get('close')
    for r in rows[-n:]:
        h,l,c=r.get('high'),r.get('low'),r.get('close')
        if None in (h,l,c,prev): return None
        trs.append(max(h-l, abs(h-prev), abs(l-prev)))
        prev=c
    return sum(trs)/len(trs)

def market_multiplier(regime):
    return {'STRONG':1.0,'RANGE':0.65,'WEAK':0.25,'UNKNOWN':0.40}.get(regime,0.40)

def position_plan(rows, regime, risk_score, max_single=0.20):
    closes=[r.get('close') for r in rows if r.get('close') is not None]
    if len(closes)<20: return {'position_pct':0.0,'reason':'K线不足'}
    a=atr(rows)
    last=closes[-1]
    if not a or last<=0: return {'position_pct':0.0,'reason':'ATR不足'}
    atr_pct=a/last*100
    volatility_factor=max(0.25,min(1.0,3.0/max(atr_pct,0.1)))
    risk_factor=max(0.20,min(1.0,(10-float(risk_score))/5.0))
    pct=max_single*market_multiplier(regime)*volatility_factor*risk_factor
    return {
      'position_pct':round(max(0,min(max_single,pct))*100,1),
      'atr':round(a,4),'atr_pct':round(atr_pct,2),
      'stop_loss':round(last-2*a,2),'trailing_reference':round(last-3*a,2),
      'reason':'按市场环境、ATR波动率和个股风险动态计算，非固定满仓。'
    }

def regime_adjustment(regime, score, risk):
    if regime=='WEAK':
        return score-12, min(9,risk+2), '弱市显著降权，原则上不追涨新开仓'
    if regime=='RANGE':
        return score-4, min(9,risk+0.5), '震荡市降低突破追涨权重'
    if regime=='STRONG':
        return score+2, risk, '强势市场允许趋势策略，但仍执行风控'
    return score-6, min(9,risk+1), '市场状态未知，采取保守处理'
