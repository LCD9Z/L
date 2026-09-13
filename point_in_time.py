# -*- coding: utf-8 -*-
"""Point-in-Time股票池接口。缺少历史快照时明确拒绝“伪历史”回测。"""
import json, os

def load_universe(snapshot_dir, date, strict=True):
    files=[]
    if os.path.isdir(snapshot_dir):
        files=sorted(f for f in os.listdir(snapshot_dir) if f.endswith('.json') and f[:-5] <= str(date))
    if not files:
        if strict: raise ValueError('缺少不晚于回测日期的历史股票池快照，禁止使用当前股票池替代历史股票池')
        return []
    with open(os.path.join(snapshot_dir,files[-1]),encoding='utf-8') as f: obj=json.load(f)
    return obj.get('codes',obj if isinstance(obj,list) else [])
