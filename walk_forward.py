# -*- coding: utf-8 -*-
"""Walk-forward validation for A-share daily-bar strategies.
Strictly uses information available at each signal day's close.
"""
import math, statistics
from backtest_engine import Costs, _trade_cost, _is_unbuyable_limit
from execution_rules import first_sellable_index
from cycle_price_action import locate_cycle_phase, _STAGE_SCORE, _STAGE_RISK
from typing import List


def _slice_vals(bars, key): return [float(b[key]) for b in bars if b.get(key) is not None]
def _turnover(bar):
    for k in ('turnover','turnover_rate'):
        if bar.get(k) is not None: return float(bar[k])
    return None

def score_history(bars, legacy=False):
    """Pure historical score; bars end on signal day. No quote/network access."""
    if len(bars) < 30: return {'score':0.0,'risk':9.0,'reason':['insufficient_history']}
    closes=_slice_vals(bars,'close'); highs=_slice_vals(bars,'high'); lows=_slice_vals(bars,'low')
    if len(closes)<30 or len(highs)<30 or len(lows)<30: return {'score':0.0,'risk':9.0,'reason':['invalid_history']}
    score=50.0; risk=5.0; reason: List[str]=[]
    prev=closes[-2]; pct=(closes[-1]/prev-1)*100 if prev else 0.0
    if legacy:
        if pct>0: score += min(pct*3,30)
        else: score -= min(abs(pct)*2,20)
    else:
        if 0<pct<=3: score += pct*2
        elif pct>3: score += min(6+(pct-3)*.5,10); risk += 1
        else: score -= min(abs(pct)*2,20)
        if pct>=5: risk += 2
        elif pct<=-5: risk += 3
    t=_turnover(bars[-1])
    if t is not None:
        if 1<=t<=8: score+=10
        elif t>8: score+=5; risk+=1
        else: score-=5
    trend=(closes[-1]/closes[-6]-1)*100
    if legacy:
        if trend>5: score+=15
        elif trend>0: score+=8
        elif trend<-5: score-=15; risk+=2
        else: score-=5
    else:
        if 5<trend<=12: score+=10
        elif trend>12: score+=4; risk+=2
        elif trend>0: score+=8
        elif trend<-5: score-=15; risk+=2
        else: score-=5
    if closes[-1] >= max(highs[-6:-1]): score+=10
    stage=locate_cycle_phase(closes,highs,lows)
    if stage:
        sid=stage[0]; score += _STAGE_SCORE.get(sid,0); risk += _STAGE_RISK.get(sid,0)
    return {'score':max(0,min(100,score)),'risk':max(1,min(9,risk)),'reason':reason}


def walk_forward(code,bars,threshold=70.0,horizon=5,initial_capital=100000.0,costs=None,legacy=False):
    costs=costs or Costs(); bars=[b for b in bars if all(b.get(k) is not None for k in ('date','open','high','low','close'))]
    equity=initial_capital; trades=[]; curve=[]; i=30
    while i < len(bars)-1:
        sig=score_history(bars[:i+1],legacy=legacy)
        if sig['score'] < threshold or sig['risk'] > 7:
            curve.append({'date':bars[i]['date'],'equity':equity}); i+=1; continue
        entry_i=i+1
        if _is_unbuyable_limit(bars[entry_i],bars[i]['close'],code):
            trades.append({'signal_date':bars[i]['date'],'score':round(sig['score'],2),'status':'skipped_limit_up'}); i+=1; continue
        due_i=min(entry_i+horizon-1,len(bars)-1)
        exit_i=first_sellable_index(code,bars,due_i)
        if exit_i is None:
            trades.append({'signal_date':bars[i]['date'],'score':round(sig['score'],2),'status':'open_unsellable_at_end'})
            break
        entry=float(bars[entry_i]['open'])*(1+costs.slippage_rate); exitp=float(bars[exit_i]['close'])*(1-costs.slippage_rate)
        shares=math.floor(equity/entry/100)*100
        if shares<=0: break
        bn=shares*entry; sn=shares*exitp; pnl=sn-_trade_cost(sn,'sell',costs)-bn-_trade_cost(bn,'buy',costs)
        equity+=pnl; ret=pnl/(bn+_trade_cost(bn,'buy',costs))*100
        trades.append({'signal_date':bars[i]['date'],'entry_date':bars[entry_i]['date'],'exit_date':bars[exit_i]['date'],'score':round(sig['score'],2),'risk':round(sig['risk'],2),'return_pct':round(ret,4),'pnl':round(pnl,2),'status':'closed'})
        curve.append({'date':bars[exit_i]['date'],'equity':equity}); i=exit_i+1
    return metrics(code,initial_capital,equity,trades,curve)


def metrics(code,initial,equity,trades,curve):
    closed=[x for x in trades if x.get('status')=='closed']; rs=[x['return_pct'] for x in closed]
    peak=initial; dd=0
    for p in curve: peak=max(peak,p['equity']); dd=max(dd,(peak-p['equity'])/peak*100 if peak else 0)
    gross_win=sum(r for r in rs if r>0); gross_loss=abs(sum(r for r in rs if r<0))
    pf=(gross_win/gross_loss) if gross_loss else None
    sharpe=None
    if len(rs)>1 and statistics.pstdev(rs)>0: sharpe=statistics.mean(rs)/statistics.pstdev(rs)*math.sqrt(252/5)
    return {'code':code,'final_equity':round(equity,2),'total_return_pct':round((equity/initial-1)*100,3),'trades':len(closed),'win_rate_pct':round(100*sum(r>0 for r in rs)/len(rs),2) if rs else 0,'avg_trade_return_pct':round(statistics.mean(rs),3) if rs else 0,'profit_factor':round(pf,3) if pf else None,'max_drawdown_pct':round(dd,3),'trade_sharpe':round(sharpe,3) if sharpe is not None else None,'trade_log':trades,'equity_curve':curve}


def compare(code,bars,**kwargs):
    legacy=walk_forward(code,bars,legacy=True,**kwargs); optimized=walk_forward(code,bars,legacy=False,**kwargs)
    return {'code':code,'legacy':legacy,'optimized':optimized,'delta_total_return_pct':round(optimized['total_return_pct']-legacy['total_return_pct'],3),'delta_max_drawdown_pct':round(optimized['max_drawdown_pct']-legacy['max_drawdown_pct'],3)}
