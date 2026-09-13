# -*- coding: utf-8 -*-
import argparse,json
from data_fetcher import fetch_kline
from historical_universe import load_codes
from portfolio_backtest import portfolio_backtest
from regime_backtest_report import evaluate_backtest
p=argparse.ArgumentParser(); p.add_argument('universe_json'); p.add_argument('--limit',type=int,default=500); p.add_argument('--top-n',type=int,default=5); p.add_argument('--threshold',type=float,default=70); p.add_argument('--horizon',type=int,default=5); p.add_argument('--out'); a=p.parse_args()
data={}
for c in load_codes(a.universe_json):
    bars=fetch_kline(c,limit=a.limit,min_quality='medium')
    if bars: data[c]=bars
r=portfolio_backtest(data,threshold=a.threshold,top_n=a.top_n,horizon=a.horizon)
r['phase9_diagnostics']=evaluate_backtest(r)
print(json.dumps({k:v for k,v in r.items() if k not in ('trade_log','equity_curve')},ensure_ascii=False,indent=2))
if a.out:
    with open(a.out,'w',encoding='utf-8') as f:
        f.write(json.dumps(r,ensure_ascii=False,indent=2,default=str))
