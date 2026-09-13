# -*- coding: utf-8 -*-
"""A股日线事件驱动回测引擎（无第三方依赖）。
信号在T日收盘后生成，默认T+1开盘成交，严格避免未来函数。
"""
import math
from dataclasses import dataclass
from exchange_rules import limit_ratio as _exchange_limit_ratio, limit_prices as _exchange_limit_prices

@dataclass
class Costs:
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_duty_sell: float = 0.0005
    slippage_rate: float = 0.0005


def _trade_cost(notional, side, c):
    commission = max(c.min_commission, notional * c.commission_rate)
    tax = notional * c.stamp_duty_sell if side == 'sell' else 0.0
    return commission + tax


def _valid_bar(b):
    return all(b.get(k) is not None for k in ('date','open','high','low','close')) and b['open'] > 0 and b['close'] > 0


def _limit_ratio(code, bar=None):
    return _exchange_limit_ratio(code, bar)

def _limit_prices(prev_close, code, bar=None):
    return _exchange_limit_prices(prev_close, code, bar)

def _is_unbuyable_limit(bar, prev_close, code):
    up,_=_limit_prices(float(prev_close),code,bar)
    if up is None: return False
    return float(bar.get('open') or 0) >= up*0.999 and float(bar.get('low') or 0) >= up*0.999


def _is_unsellable_limit(bar, prev_close, code):
    _,down=_limit_prices(float(prev_close),code,bar)
    if down is None: return False
    return float(bar.get('open') or 0) <= down*1.001 and float(bar.get('high') or 0) <= down*1.001


def _signal(closes):
    """示例基线策略：20日趋势 + 5日突破。只用T日及以前数据。"""
    if len(closes) < 21: return False
    ma20=sum(closes[-20:])/20
    prior=max(closes[-6:-1]) if len(closes)>=6 else max(closes[:-1])
    return closes[-1] > ma20 and closes[-1] > prior


def backtest(code, bars, horizon=5, initial_capital=100000.0, costs=None, signal_func=None):
    costs=costs or Costs(); signal_func=signal_func or _signal
    bars=[b for b in bars if _valid_bar(b)]
    trades=[]; equity=initial_capital; curve=[{'date':bars[0]['date'],'equity':equity}] if bars else []
    i=21
    while i < len(bars)-1:
        closes=[float(x['close']) for x in bars[:i+1]]
        if not signal_func(closes):
            curve.append({'date':bars[i]['date'],'equity':equity}); i+=1; continue
        entry_i=i+1
        if _is_unbuyable_limit(bars[entry_i], bars[i]['close'], code):
            trades.append({'signal_date':bars[i]['date'],'status':'skipped_limit_up'}); i+=1; continue
        due_i=min(entry_i+horizon-1, len(bars)-1)
        # Import lazily to avoid a circular import: execution_rules reuses limit checks.
        from execution_rules import first_sellable_index
        exit_i=first_sellable_index(code, bars, due_i)
        if exit_i is None:
            trades.append({'signal_date':bars[i]['date'],'entry_date':bars[entry_i]['date'],'status':'open_unsellable_at_end'})
            break
        entry=float(bars[entry_i]['open'])*(1+costs.slippage_rate)
        exitp=float(bars[exit_i]['close'])*(1-costs.slippage_rate)
        shares=math.floor(equity/entry/100)*100
        if shares<=0: break
        buy_notional=shares*entry; buy_cost=_trade_cost(buy_notional,'buy',costs)
        sell_notional=shares*exitp; sell_cost=_trade_cost(sell_notional,'sell',costs)
        pnl=sell_notional-sell_cost-buy_notional-buy_cost
        equity += pnl
        ret=pnl/(buy_notional+buy_cost)*100
        trades.append({'signal_date':bars[i]['date'],'entry_date':bars[entry_i]['date'],'exit_date':bars[exit_i]['date'],'entry':round(entry,3),'exit':round(exitp,3),'return_pct':round(ret,3),'pnl':round(pnl,2),'status':'closed'})
        curve.append({'date':bars[exit_i]['date'],'equity':round(equity,2)})
        i=exit_i+1
    closed=[t for t in trades if t.get('status')=='closed']
    returns=[t['return_pct'] for t in closed]
    peak=initial_capital; max_dd=0.0
    for p in curve:
        peak=max(peak,p['equity']); max_dd=max(max_dd,(peak-p['equity'])/peak*100)
    win=sum(r>0 for r in returns)/len(returns)*100 if returns else 0.0
    gross_win=sum(r for r in returns if r>0); gross_loss=abs(sum(r for r in returns if r<0))
    return {'code':code,'initial_capital':initial_capital,'final_equity':round(equity,2),'total_return_pct':round((equity/initial_capital-1)*100,2),'trades':len(closed),'win_rate_pct':round(win,2),'avg_trade_return_pct':round(sum(returns)/len(returns),3) if returns else 0.0,'profit_factor':round(gross_win/gross_loss,3) if gross_loss else None,'max_drawdown_pct':round(max_dd,2),'trade_log':trades,'equity_curve':curve}


def summarize(results):
    valid=[x for x in results if x.get('trades',0)>0]
    return {'symbols':len(results),'active_symbols':len(valid),'avg_total_return_pct':round(sum(x['total_return_pct'] for x in results)/len(results),2) if results else 0.0,'avg_win_rate_pct':round(sum(x['win_rate_pct'] for x in valid)/len(valid),2) if valid else 0.0,'worst_max_drawdown_pct':round(max((x['max_drawdown_pct'] for x in results),default=0.0),2)}
