# -*- coding: utf-8 -*-
"""Phase 8: A-share industry relative-strength model.
Uses only data available up to the evaluation date. Input is a mapping of
stock code -> bars; industry_map maps stock code -> industry name.
"""
from collections import defaultdict


def _ret(closes, n):
    if len(closes) <= n or not closes[-n-1]:
        return None
    return closes[-1] / closes[-n-1] - 1


def rank_industries(data, industry_map, as_of=None, windows=(5,20,60), min_members=2):
    groups=defaultdict(list)
    for code,bars in data.items():
        hist=[b for b in bars if as_of is None or str(b.get('date'))<=str(as_of)]
        closes=[float(b['close']) for b in hist if b.get('close') not in (None,0)]
        if len(closes)<max(windows)+1: continue
        industry=industry_map.get(code,'未知行业')
        groups[industry].append((_ret(closes,5),_ret(closes,20),_ret(closes,60)))
    rows=[]
    for industry, vals in groups.items():
        if len(vals)<min_members: continue
        avgs=[sum(v[i] for v in vals)/len(vals) for i in range(3)]
        # 60% medium trend, 30% short momentum, 10% long confirmation
        strength=avgs[0]*30+avgs[1]*60+avgs[2]*10
        rows.append({'industry':industry,'members':len(vals),'ret_5d_pct':round(avgs[0]*100,3),
                     'ret_20d_pct':round(avgs[1]*100,3),'ret_60d_pct':round(avgs[2]*100,3),
                     'strength_score_raw':round(strength*100,3)})
    rows.sort(key=lambda x:x['strength_score_raw'],reverse=True)
    for i,r in enumerate(rows,1):
        r['rank']=i
        r['percentile']=round((len(rows)-i+1)/len(rows)*100,1) if rows else 0
    return rows


def stock_industry_bonus(code, rankings, industry_map):
    industry=industry_map.get(code,'未知行业')
    row=next((x for x in rankings if x['industry']==industry),None)
    if not row: return 0.0
    p=row['percentile']
    return 8.0 if p>=80 else 4.0 if p>=60 else (-4.0 if p<=20 else 0.0)
