# -*- coding: utf-8 -*-

# 脚本位于 scripts/ 下，需把项目根目录加入导入路径
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, json
from data_fetcher import fetch_kline
from walk_forward import compare
p=argparse.ArgumentParser(); p.add_argument('code'); p.add_argument('--limit',type=int,default=500); p.add_argument('--threshold',type=float,default=70); p.add_argument('--horizon',type=int,default=5); p.add_argument('--out')
a=p.parse_args(); bars=fetch_kline(a.code,limit=a.limit,min_quality='medium')
if not bars: raise SystemExit('无法获取足够的高质量历史数据')
r=compare(a.code,bars,threshold=a.threshold,horizon=a.horizon)
print(json.dumps(r,ensure_ascii=False,indent=2,default=str))
if a.out:
    with open(a.out,'w',encoding='utf-8') as f:
        f.write(json.dumps(r,ensure_ascii=False,indent=2,default=str))
