# -*- coding: utf-8 -*-
"""Phase 11 A股组合回测：逐股票交易日、T+1、流动性和限板可执行性。"""
import math,statistics
from backtest_engine import Costs,_trade_cost,_is_unbuyable_limit,_is_unsellable_limit
from walk_forward import score_history
from risk.liquidity import is_liquid,dynamic_slippage,sqrt_impact
from typing import Any, Dict, List

def _by_date(bars): return {str(b['date']):b for b in bars if b.get('date')}
def _dates(data):
    return sorted(set().union(*(set(_by_date(v)) for v in data.values() if v))) if data else []
def _next_bar(bars, day):
    for b in bars:
        if str(b['date'])>day: return b
    return None
def _atr(bars, n):
    """平均真实波幅（True Range 均值）。**只用传入的 bars** —— PIT 由调用方保证。

    窗口不足 ``n+1`` 根或缺 OHLC 时返回 ``None``（缺失即不干预，不猜）。
    """
    if len(bars) < n + 1:
        return None
    trs = []
    prev = bars[0].get('close')
    for r in bars[1:]:
        h, l, c = r.get('high'), r.get('low'), r.get('close')
        if None in (h, l, c, prev):
            return None
        trs.append(max(float(h) - float(l), abs(float(h) - float(prev)),
                       abs(float(l) - float(prev))))
        prev = c
    return sum(trs) / len(trs) if trs else None


def _horizon_date(bars, entry_date, horizon):
    future=[b for b in bars if str(b['date'])>=entry_date]
    return str(future[min(horizon-1,len(future)-1)]['date']) if future else entry_date

def portfolio_backtest(data,threshold=70,top_n=5,horizon=5,initial_capital=1_000_000,costs=None,max_position_pct=0.25,legacy=False,min_avg_amount=100_000_000,universe_snapshot_map=None,start_signal_date=None,candidate_filter=None,position_scaler=None,score_func=None,max_participation=0.0,impact_model=False,stop_atr_k=0.0,weight_func=None):
    """组合回测。

    candidate_filter: 可选回调 ``(code, hist, day) -> bool``；返回 False 时该标的
        在当日不进入候选池。默认 None → 行为与历史版本完全一致（向后兼容）。
        用于做**事前设定**的因子剔除实验（如剔除动量极端分位），而非事后调参。
    position_scaler: 可选回调 ``day -> float``（0~1），按交易日缩放**新开仓预算**；
        不改信号/阈值/持仓周期/成本，仅用于市场状态仓位叠加层实验（如 ADX 路由）。
        默认 None → 行为与历史版本完全一致。
    score_func: 可选回调 ``(code, hist, day) -> {'score': float, 'risk': float}``，
        用于替换内置的 `walk_forward.score_history` 打分（如横截面因子组合）。
        默认 None → 行为与历史版本完全一致（用于 A/B 对照实验，唯一变量是信号）。
    max_participation: 容量约束——单笔买入名义金额 ≤ **信号日**成交额 × 该比例
        （如 0.05）。用信号日成交额而非成交日全天成交额，避免盘中前视。
        默认 0.0 = 不约束。受约束的建仓会计入返回的 `capacity_capped_buys`。
    impact_model: True 时用 sqrt 冲击成本（`risk.liquidity.sqrt_impact`，
        k·σ·√(Q/V)）替换阶梯滑点 `dynamic_slippage`；佣金/印花税/过户费不变。
        默认 False → 行为与历史版本完全一致。
    """
    costs=costs or Costs(); cash=float(initial_capital); positions: List[Dict[str, Any]]=[]; trades: List[Dict[str, Any]]=[]; curve: List[Dict[str, Any]]=[]
    capacity_capped=0
    stop_triggered=0; stop_days: List[int]=[]
    # ---- 执行侧拒单计数（REGIME_ATTRIBUTION_PREREG §三.0-A）----
    # **纯计数**：只累加整数/明细，不改变任何 `continue`/`break` 的条件与顺序，
    # 因此不改变交易序列、不改变收益。存在意义：此前「一字涨停买不进」在第 128 行
    # 直接 `continue`，事后无法回答「有多少信号被可执行性挡掉」，Critic 的失败单
    # 惩罚统计也就无从做起。
    rejects: Dict[str, int]={'limit_up':0,'shares_zero':0,'cash_short':0,'no_cash':0,
                             'exit_deferred_days':0}
    limit_up_skips: List[Dict[str, Any]]=[]
    _MAX_SKIP_DETAIL=5000   # 上限：防止极端参数下明细无限增长
    n_opened=0              # 实际建仓笔数（与 rejects 一起构成「拒单率」的分母）

    # sqrt 冲击成本的**实际取值**记录（H-IMPACT 登记 §四「必报」项）：
    # 只在 impact_model=True 时累积，单位 bps。默认关闭 → 行为与历史版本完全一致。
    impact_buy_bps: List[float]=[]; impact_sell_bps: List[float]=[]
    dates=_dates(data); cal_pos={str(d):i for i,d in enumerate(dates)}; indexed={c:_by_date(v) for c,v in data.items()}
    for day in dates:
        still=[]
        for p in positions:
            b=indexed[p['code']].get(day)
            if b: p['last_close']=float(b['close'])
            # ---- ATR 移动止损（能力孤岛接线）----
            # 事前登记：stop = 持仓期最高收盘 − k×ATR(14)，ATR **只用截至前一日**的数据；
            # 触发条件为当日收盘 < stop，按当日收盘价平仓（与 exit_due 的平仓约定一致）。
            # 缺失即不干预：ATR 不足 15 根 / k<=0 时本规则完全不生效。
            stop_hit=False
            if b and stop_atr_k>0:
                bars_s=data[p['code']]
                pos_s=next((i for i,x in enumerate(bars_s) if str(x['date'])==day),None)
                if pos_s is not None and pos_s>=15:
                    a=_atr(bars_s[pos_s-15:pos_s],14)
                    peak=p.get('peak_close',p['entry_price'])
                    p['peak_close']=max(peak,float(b['close']))
                    if a and a>0 and float(b['close']) < p['peak_close']-stop_atr_k*a:
                        stop_hit=True
            if b and (day>=p['exit_due'] or stop_hit):
                bars=data[p['code']]; pos=next((i for i,x in enumerate(bars) if str(x['date'])==day),None)
                prev=float(bars[pos-1]['close']) if pos and pos>0 else None
                if prev and _is_unsellable_limit(b,prev,p['code']): p['exit_deferred']=True; rejects['exit_deferred_days']+=1; still.append(p); continue
                slip=dynamic_slippage([x for x in bars if str(x['date'])<=day],costs.slippage_rate)
                if impact_model:
                    slip=sqrt_impact([x for x in bars if str(x['date'])<=day],
                                     p['shares']*float(b['close']))
                if impact_model: impact_sell_bps.append(slip*10000.0)
                gross=p['shares']*float(b['close'])*(1-slip); proceeds=gross-_trade_cost(gross,'sell',costs,day); cash+=proceeds
                _ed=cal_pos.get(day,0)-cal_pos.get(p['entry_date'],0)
                if stop_hit:
                    stop_triggered+=1; stop_days.append(_ed)
                trades.append({**p,'exit_date':day,'exit_price':round(gross/p['shares'],4),'return_pct':round((proceeds-p['cost_basis'])/p['cost_basis']*100,4),'status':'closed','exit_reason':('stop' if stop_hit else 'horizon'),'held_days':_ed})
            else: still.append(p)
        positions=still
        candidates=[]
        held={p['code'] for p in positions}
        allowed=None
        if start_signal_date is not None and str(day) < str(start_signal_date):
            equity=cash+sum(p['shares']*p['last_close'] for p in positions)
            continue
        if universe_snapshot_map is not None:
            from historical_universe import point_in_time_universe
            allowed=set(point_in_time_universe(universe_snapshot_map, day))
        for code,bars in data.items():
            if code in held or (allowed is not None and code not in allowed): continue
            hist=[b for b in bars if str(b['date'])<=day]
            nxt=_next_bar(bars,day)
            if len(hist)<30 or not nxt or not is_liquid(hist,min_avg_amount): continue
            # 停牌/缺行情当日不建仓：成交K线必须恰好是全池的下一个交易日，
            # 否则该标的当日没有真实行情（停牌或数据缺口），信号与成交脱节。
            d_idx=cal_pos.get(day)
            if d_idx is not None and d_idx+1<len(dates) and str(nxt['date'])!=dates[d_idx+1]: continue
            if candidate_filter is not None and not candidate_filter(code,hist,day): continue
            s = score_func(code,hist,day) if score_func is not None else score_history(hist,legacy=legacy)
            if s['score']>=threshold and s['risk']<=7: candidates.append((s['score'],s['risk'],code,hist,nxt))
        candidates.sort(key=lambda x:(x[0],-x[1]),reverse=True)
        scale=1.0
        if position_scaler is not None: scale=max(0.0,min(1.0,float(position_scaler(day))))
        slots=max(0,top_n-len(positions))
        if scale<=0: slots=0  # 状态路由要求当日停开新仓
        for score,risk,code,hist,nxt in candidates[:slots]:
            if cash<=0: rejects['no_cash']+=1; break
            if _is_unbuyable_limit(nxt,hist[-1]['close'],code):
                rejects['limit_up']+=1
                if len(limit_up_skips)<_MAX_SKIP_DETAIL:
                    limit_up_skips.append({'date':day,'code':code,'score':round(score,2),
                                           'next_date':str(nxt['date'])})
                continue
            slip=dynamic_slippage(hist,costs.slippage_rate)
            if impact_model:
                # 买入冲击用目标仓位预算作名义（initial_capital×max_position_pct），
                # 避免与 entry/shares 相互依赖；事前近似，与卖出一致用单边冲击。
                slip=sqrt_impact(hist, initial_capital*max_position_pct)
            entry=float(nxt['open'])*(1+slip)
            w=1.0
            if weight_func is not None:
                try: w=float(weight_func(code,hist,day))
                except Exception: w=1.0
                if w!=w or w<0: w=1.0             # NaN / 负数 → 不干预
            budget=min(initial_capital*max_position_pct,cash/max(1,slots))*scale*w
            capped=False
            if max_participation>0:
                cap_notional=float(hist[-1].get('amount') or 0)*max_participation
                if cap_notional>0 and cap_notional<budget:
                    budget=cap_notional; capped=True
            shares=math.floor(budget/entry/100)*100
            if shares<=0: rejects['shares_zero']+=1; continue
            if capped: capacity_capped+=1
            gross=shares*entry; total=gross+_trade_cost(gross,'buy',costs,nxt['date'])
            if total>cash: rejects['cash_short']+=1; continue
            if impact_model: impact_buy_bps.append(slip*10000.0)
            cash-=total; entry_date=str(nxt['date']); due=_horizon_date(data[code],entry_date,horizon)
            n_opened+=1
            positions.append({'code':code,'signal_date':day,'entry_date':entry_date,'entry_price':round(entry,4),'shares':shares,'score':round(score,2),'risk':round(risk,2),'cost_basis':total,'exit_due':due,'last_close':float(nxt['close']),
                              'peak_close':float(nxt['close'])})
        equity=cash+sum(p['shares']*p['last_close'] for p in positions); curve.append({'date':day,'equity':round(equity,2),'cash':round(cash,2),'positions':len(positions)})
    # 不强制把不可卖的跌停仓位当作可成交；期末仅按市值计价
    final=curve[-1]['equity'] if curve else initial_capital
    out=summarize_portfolio(initial_capital,final,trades,curve)
    out['capacity_capped_buys']=capacity_capped
    # 止损路径的必报项（短线冲浪手 P0-2 验收要求）：止损率 + 平均触发天数
    n_closed=len([t for t in trades if t.get('status')=='closed'])
    out['stop_stats']={
        'stop_atr_k':stop_atr_k,
        'n_stops':stop_triggered,
        'stop_rate_pct':round(stop_triggered/n_closed*100,2) if n_closed else None,
        'avg_days_to_stop':round(sum(stop_days)/len(stop_days),2) if stop_days else None,
        'n_closed':n_closed,
    }
    # sqrt 冲击成本的量级核对（H-IMPACT 登记 §四「必报」）：买入端与卖出端**分开**报。
    def _bps(v: List[float]) -> Dict[str, Any]:
        if not v:
            return {'n': 0, 'mean_bps': None, 'max_bps': None, 'min_bps': None}
        return {'n': len(v), 'mean_bps': round(sum(v)/len(v), 2),
                'max_bps': round(max(v), 2), 'min_bps': round(min(v), 2)}

    out['impact_stats']={
        'impact_model':impact_model,
        'buy':_bps(impact_buy_bps),
        'sell':_bps(impact_sell_bps),
    }
    # 执行侧拒单统计（REGIME_ATTRIBUTION_PREREG §三.0-A）：恒返回，字段只增不改。
    # `limit_up_rate_pct` = 涨停被拒 / (涨停被拒 + 实际建仓) —— 回答「策略收益里
    # 有多少是被可执行性挡掉后才得到的结果」，是本轮归因的必要背景，不进任何判据。
    _denom=rejects['limit_up']+n_opened
    out['execution_stats']={
        'rejects':dict(rejects),
        'opened':n_opened,
        'limit_up_rate_pct':round(rejects['limit_up']/_denom*100,2) if _denom else None,
        'limit_up_skips':limit_up_skips,
        'limit_up_skips_truncated':rejects['limit_up']>len(limit_up_skips),
    }
    return out

def summarize_portfolio(initial,final,trades,curve):
    rs=[t['return_pct'] for t in trades if 'return_pct' in t]; peak=initial;mdd=0
    for x in curve: peak=max(peak,x['equity']);mdd=max(mdd,(peak-x['equity'])/peak*100 if peak else 0)
    wins=sum(r>0 for r in rs); losses=[-r for r in rs if r<0]; gw=sum(r for r in rs if r>0); pf=gw/sum(losses) if losses else None
    daily=[curve[i]['equity']/curve[i-1]['equity']-1 for i in range(1,len(curve)) if curve[i-1]['equity']>0]
    sd=statistics.pstdev(daily) if len(daily)>1 else 0; sharpe=statistics.mean(daily)/sd*math.sqrt(252) if sd else None
    return {'initial_capital':initial,'final_equity':round(final,2),'total_return_pct':round((final/initial-1)*100,3),'trades':len(rs),'win_rate_pct':round(wins/len(rs)*100,2) if rs else 0,'profit_factor':round(pf,3) if pf is not None else None,'max_drawdown_pct':round(mdd,3),'daily_sharpe':round(sharpe,3) if sharpe is not None else None,'trade_log':trades,'equity_curve':curve}
