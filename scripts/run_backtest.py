# -*- coding: utf-8 -*-

# 脚本位于 scripts/ 下，需把项目根目录加入导入路径
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, json
from data_fetcher import fetch_kline
from backtest_engine import backtest

def main():
 p=argparse.ArgumentParser(description='A股无未来函数日线回测')
 p.add_argument('code'); p.add_argument('--beg', required=True); p.add_argument('--end', required=True)
 p.add_argument('--horizon',type=int,default=5); p.add_argument('--capital',type=float,default=100000)
 p.add_argument('--output')
 a=p.parse_args()
 bars=fetch_kline(a.code,beg=a.beg,end=a.end,min_quality='medium')
 if len(bars)<30: raise SystemExit('有效前复权K线不足30根，拒绝回测')
 r=backtest(a.code,bars,horizon=a.horizon,initial_capital=a.capital)
 text=json.dumps(r,ensure_ascii=False,indent=2)
 print(text)
 if a.output:
  with open(a.output,'w',encoding='utf-8') as f:f.write(text)
if __name__=='__main__': main()
