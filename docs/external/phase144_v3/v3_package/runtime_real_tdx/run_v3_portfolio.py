# -*- coding: utf-8 -*-
"""A股量化 V3：真实TDX -> 五因子 -> Top20 -> T+1持仓 -> 每日净值。
仅模拟，不连接券商，不下真实订单。
"""
from __future__ import annotations
import argparse, csv, json, math, os, time
from pathlib import Path
from collections import defaultdict
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tdx.day_reader import scan, parse_file
from factor.factor_ic_lab import compute_factors, PRIOR_SIGN

FACTORS=('ret_20','vol_20','amihud_20','log_amount_20','max_ret_20')
LIQ_MIN=100_000_000.0
INITIAL_CASH=100_000.0
LOT=100
BUY_SLIP=0.0005
SELL_SLIP=0.0005
COMMISSION=0.0003
MIN_COMMISSION=5.0
STAMP=0.0005
REBALANCE_DAYS=20


def rank(vals, higher=True):
    valid=[(v,i) for i,v in enumerate(vals) if v is not None and math.isfinite(v)]
    valid.sort(key=lambda x:x[0], reverse=not higher)
    out=[None]*len(vals); n=len(valid)
    if n==0:return out
    if n==1:out[valid[0][1]]=50.0;return out
    for pos,(_,i) in enumerate(valid): out[i]=100.0*pos/(n-1)
    return out

def board_limit(market, code):
    c=str(code).zfill(6)
    if c.startswith(('688','689','300','301','302')): return 0.20
    if c.startswith('920') or market=='bj': return 0.30
    return 0.10

def read_all(path): return list(parse_file(path))

def fee_buy(gross): return max(gross*COMMISSION, MIN_COMMISSION)
def fee_sell(gross): return max(gross*COMMISSION, MIN_COMMISSION)+gross*STAMP

def write_csv(path, header, rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(header); w.writerows(rows)

def build_signal_panel(files, report):
    """两遍扫描：第一遍只收集交易日，第二遍逐股票滚动计算信号，避免8GB机器吃满内存。"""
    all_dates=set(); bad=0; insufficient=0
    for market,code,path in files:
        try:
            n=0
            for b in parse_file(path):
                if b['date']>0: all_dates.add(b['date']); n+=1
            if n<26: insufficient+=1
        except Exception: bad+=1
    dates=sorted(all_dates)
    if len(dates)<21: return {}, {}, [], bad, insufficient
    signal_dates=dates[20::REBALANCE_DAYS]
    signal_set=set(signal_dates)
    data_by_date=defaultdict(list)
    selected_paths={}
    for market,code,path in files:
        try:
            hist=[]
            found=False
            for b in parse_file(path):
                if b['date']<=0: continue
                hist.append(b)
                if len(hist)>26: hist.pop(0)
                d=b['date']
                if d not in signal_set or len(hist)<26: continue
                # compute_factors expects an index into the supplied history.
                f=compute_factors(hist,len(hist)-1)
                if f is None: continue
                avg_amt=math.exp(f['log_amount_20']) if math.isfinite(f['log_amount_20']) else 0.0
                if avg_amt < LIQ_MIN: continue
                data_by_date[d].append({'market':market,'code':code,'factor_score':None,'avg_amount_20':avg_amt,**f})
                selected_paths[(market,code)]=path
                found=True
        except Exception:
            bad+=1
    top_by_date={}
    for d in signal_dates:
        cur=data_by_date.get(d,[])
        if not cur: continue
        ranks={f:rank([r[f] for r in cur], higher=(PRIOR_SIGN[f]>0)) for f in FACTORS}
        for i,r in enumerate(cur):
            vals=[ranks[f][i] for f in FACTORS if ranks[f][i] is not None]
            r['factor_score']=sum(vals)/len(vals) if vals else None
        cur=[r for r in cur if r['factor_score'] is not None]
        cur.sort(key=lambda r:(-r['factor_score'],r['code']))
        top_by_date[d]=cur[:20]
    report['signal_dates']=len(top_by_date)
    report['avg_liquid_candidates']=round(sum(len(data_by_date[d]) for d in top_by_date)/max(1,len(top_by_date)),1)
    # Only selected stocks are re-read later for price/NAV simulation.
    return top_by_date, selected_paths, dates, bad, insufficient

def simulate(root, out):
    t0=time.time()
    report={'status':'STARTING','tdx_path':str(root),'strategy':'A股5Factor_RankTop20_20D',
            'factor_definition':list(FACTORS),'factor_direction':{k:PRIOR_SIGN[k] for k in FACTORS},
            'liquidity_min_avg_amount_20':LIQ_MIN,'simulation_only':True,
            'initial_cash':INITIAL_CASH,'lot_size':LOT,'rebalance_days':REBALANCE_DAYS,
            'buy_slippage':BUY_SLIP,'sell_slippage':SELL_SLIP,'commission':COMMISSION,
            'min_commission':MIN_COMMISSION,'stamp_duty':STAMP,'data_boundary':'RAW_TDX_UNADJUSTED',
            'alpha_claim':False}
    if not root.exists():
        report['status']='PATH_NOT_FOUND'; (out/'run_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)); return report
    files=scan(root); report['candidate_files']=len(files)
    top_by_date,selected_paths,dates,bad,insufficient=build_signal_panel(files,report)
    report.update(bad_files=bad,insufficient_history=insufficient)
    if not top_by_date:
        report['status']='NO_SIGNAL_DATA'; (out/'run_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)); return report

    # Compact price lookup only for codes that ever enter Top20.
    selected={(r['market'],r['code']) for top in top_by_date.values() for r in top}
    price={}
    for key in selected:
        path=selected_paths.get(key)
        if not path: continue
        price[key]={b['date']:{'open':b['open'],'high':b['high'],'low':b['low'],'close':b['close']} for b in parse_file(path)}

    signal_dates=sorted(top_by_date)
    date_index={d:i for i,d in enumerate(dates)}
    rebalance_exec={}
    for d in signal_dates:
        j=date_index[d]+1
        if j<len(dates): rebalance_exec[d]=dates[j]
    exec_dates=set(rebalance_exec.values())

    cash=INITIAL_CASH
    holdings={} # key -> shares, avg_cost
    nav_rows=[]; trade_rows=[]; rebalance_rows=[]
    peak=INITIAL_CASH; max_dd=0.0
    pending=0; skipped_buys=0; skipped_sells=0
    total_buy=0; total_sell=0

    def mark_nav(d):
        v=cash
        for key,pos in holdings.items():
            p=price.get(key,{}).get(d)
            if p: v += pos['shares']*p['close']
        return v

    for d in dates:
        # Execute scheduled rebalance at next-day open.
        sig_for_d=[s for s,e in rebalance_exec.items() if e==d]
        if sig_for_d:
            sig=sig_for_d[0]; targets=top_by_date[sig]
            # Sell everything first.
            for key,pos in list(holdings.items()):
                p=price.get(key,{}).get(d)
                if not p: continue
                prev=price[key].get(sig)
                lim=board_limit(key[0],key[1]); locked_down=False
                if prev:
                    limit_down=prev['close']*(1-lim)
                    locked_down=(p['high']<=limit_down*1.0005 and p['low']<=limit_down*1.0005 and p['open']<=limit_down*1.0005)
                if locked_down:
                    skipped_sells+=1; continue
                exec_px=p['open']*(1-SELL_SLIP); shares=pos['shares']; gross=shares*exec_px; fee=fee_sell(gross); cash+=gross-fee
                trade_rows.append([d,'SELL',key[0],key[1],shares,exec_px,gross,fee,'SIMULATED_REBALANCE'])
                total_sell+=1; del holdings[key]
            # Buy targets equal-weight from current total equity, respecting 100-share lots.
            target_nav=cash+sum(pos['shares']*price[key][d]['close'] for key,pos in holdings.items() if key in price and d in price[key])
            budget=target_nav/max(1,len(targets))
            for r in targets:
                key=(r['market'],r['code']); p=price.get(key,{}).get(d)
                if not p: pending+=1; continue
                prev=price[key].get(sig); lim=board_limit(*key); locked_up=False
                if prev:
                    limit_up=prev['close']*(1+lim)
                    locked_up=(p['high']>=limit_up*0.9995 and p['low']>=limit_up*0.9995 and p['open']>=limit_up*0.9995)
                exec_px=p['open']*(1+BUY_SLIP)
                shares=int(budget/exec_px//LOT*LOT) if exec_px>0 else 0
                if locked_up or shares<=0:
                    skipped_buys+=1; continue
                gross=shares*exec_px; fee=fee_buy(gross); total=gross+fee
                if total>cash:
                    # Recompute affordable lots from remaining cash.
                    shares=int(max(0,(cash-MIN_COMMISSION)/exec_px)//LOT*LOT)
                    gross=shares*exec_px; fee=fee_buy(gross); total=gross+fee
                if shares<=0 or total>cash:
                    skipped_buys+=1; continue
                cash-=total; holdings[key]={'shares':shares,'avg_cost':exec_px}
                trade_rows.append([d,'BUY',key[0],key[1],shares,exec_px,gross,fee,'SIMULATED_REBALANCE'])
                total_buy+=1
            rebalance_rows.append([sig,d,len(targets),len(holdings),cash])
        nav=mark_nav(d)
        peak=max(peak,nav); dd=(peak-nav)/peak if peak else 0.0; max_dd=max(max_dd,dd)
        nav_rows.append([d,nav,cash,len(holdings),peak,dd])

    final_nav=nav_rows[-1][1]
    total_ret=final_nav/INITIAL_CASH-1
    daily_rets=[]
    prev=None
    for row in nav_rows:
        if prev and prev>0: daily_rets.append(row[1]/prev-1)
        prev=row[1]
    mean=sum(daily_rets)/len(daily_rets) if daily_rets else 0
    sd=math.sqrt(sum((x-mean)**2 for x in daily_rets)/max(1,len(daily_rets)-1)) if len(daily_rets)>1 else 0
    sharpe=(mean/sd*math.sqrt(252)) if sd>0 else 0
    write_csv(out/'daily_nav.csv',['date','nav','cash','positions','peak_nav','drawdown'],nav_rows)
    write_csv(out/'trades.csv',['date','side','market','code','shares','execution_price','gross','fee','reason'],trade_rows)
    write_csv(out/'rebalance_log.csv',['signal_date','execution_date','target_count','held_count','cash_after'],rebalance_rows)
    top_rows=[]
    for d in signal_dates:
        for i,r in enumerate(top_by_date[d],1): top_rows.append([d,i,r['market'],r['code'],r['factor_score'],r['avg_amount_20']]+[r[f] for f in FACTORS])
    write_csv(out/'all_top20_signals.csv',['signal_date','rank','market','code','factor_score','avg_amount_20']+list(FACTORS),top_rows)
    report.update(status='PASS',start_date=nav_rows[0][0],end_date=nav_rows[-1][0],
                  signal_dates=len(signal_dates),execution_dates=len(exec_dates),
                  final_nav=round(final_nav,2),total_return=round(total_ret,6),
                  max_drawdown=round(max_dd,6),sharpe=round(sharpe,4),
                  rebalance_count=len(rebalance_rows),buy_trades=total_buy,sell_trades=total_sell,
                  skipped_buys=skipped_buys,skipped_sells=skipped_sells,pending=pending,
                  elapsed_sec=round(time.time()-t0,3),notes=['仅模拟，不连接券商','初始资金10万元','MaxCorr关闭','历史ST不补造','RAW TDX未复权价格用于执行与净值'])
    (out/'run_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'run_report.txt').write_text('\n'.join([f"status={report['status']}",f"initial_cash={INITIAL_CASH:.2f}",f"start_date={report['start_date']}",f"end_date={report['end_date']}",f"final_nav={final_nav:.2f}",f"total_return={total_ret:.2%}",f"max_drawdown={max_dd:.2%}",f"sharpe={sharpe:.4f}",f"rebalance_count={len(rebalance_rows)}",f"buy_trades={total_buy}",f"sell_trades={total_sell}","data=RAW TDX .day; simulation only"]))
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--tdx-path',default=None); ap.add_argument('--output',default='output'); args=ap.parse_args()
    root=Path(args.tdx_path or os.environ.get('TDX_PATH','D:/new_tdx/vipdoc')).expanduser(); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    r=simulate(root,out); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(0 if r.get('status')=='PASS' else 2)
