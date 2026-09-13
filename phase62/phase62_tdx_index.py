# -*- coding: utf-8 -*-
"""Phase 62: one-pass low-RAM TDX local index for repeated factor research.

Builds a compact SQLite research store from the raw TDX CSV. Only project-classified
A-share stock rows are retained (code, date, close). The raw source remains untouched.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, sqlite3, time
from pathlib import Path

STOCK_PREFIX = {
    'sh': ('600','601','603','605','688','689'),
    'sz': ('000','001','002','003','300','301','302'),
    'bj': ('43','83','87','88','92'),
}

def is_stock(code, market):
    c=str(code).zfill(6)
    return c.startswith(STOCK_PREFIX.get(str(market), ()))

def sha256_file(path, chunk=1024*1024):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            b=f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def build(src, db_path, batch_size=20000):
    src=Path(src); db_path=Path(db_path); db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists(): db_path.unlink()
    t0=time.time(); db=sqlite3.connect(db_path)
    db.execute('PRAGMA journal_mode=OFF'); db.execute('PRAGMA synchronous=OFF'); db.execute('PRAGMA temp_store=MEMORY'); db.execute('PRAGMA cache_size=-65536')
    db.execute('CREATE TABLE stock (code TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL)')
    ins=db.executemany
    batch=[]; rows=0; bad=0; first=None; last=None; codes=set(); dates=set()
    with src.open('r',encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        for x in r:
            if not is_stock(x.get('code',''), x.get('market','')): continue
            try:
                c=str(x['code']).zfill(6); d=x['date']; p=float(x['close'])
                if not d or p != p: raise ValueError
            except Exception:
                bad += 1; continue
            batch.append((c,d,p)); rows += 1; codes.add(c); dates.add(d)
            first=d if first is None or d<first else first; last=d if last is None or d>last else last
            if len(batch)>=batch_size:
                ins('INSERT INTO stock(code,date,close) VALUES (?,?,?)', batch); db.commit(); batch.clear()
    if batch: ins('INSERT INTO stock(code,date,close) VALUES (?,?,?)', batch); db.commit()
    t1=time.time()
    db.execute('CREATE UNIQUE INDEX idx_stock_code_date ON stock(code,date)'); db.commit()
    t2=time.time()
    db.execute('ANALYZE'); db.commit()
    meta={
        'schema':'phase62_tdx_stock_v1','source':str(src),'source_size_bytes':src.stat().st_size,
        'source_sha256':sha256_file(src),'rows':rows,'unique_codes':len(codes),'unique_dates':len(dates),
        'earliest_date':first,'latest_date':last,'bad_rows':bad,'build_seconds':round(t1-t0,2),
        'index_seconds':round(t2-t1,2),'total_seconds':round(t2-t0,2),'classification':'project A-share stock prefixes only',
        'columns':['code','date','close'],'raw_unadjusted':True,
    }
    db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    for k,v in meta.items(): db.execute('INSERT INTO metadata VALUES (?,?)',(k,json.dumps(v,ensure_ascii=False)))
    db.commit(); db.close()
    return meta

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('source'); ap.add_argument('-o','--db',required=True); ap.add_argument('--batch-size',type=int,default=20000); a=ap.parse_args()
    print(json.dumps(build(a.source,a.db,a.batch_size),ensure_ascii=False,indent=2))
