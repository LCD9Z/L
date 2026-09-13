"""Phase 25: strict, provenance-first real market data collector.

Rules:
* Never synthesize prices.
* A source fallback is explicit and recorded.
* Data with structural/audit errors are not silently certified.
* Every certified file has a SHA-256 fingerprint and reproducible metadata.
"""
from __future__ import annotations
import csv, hashlib, json, os
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from data_fetcher import fetch_kline

@dataclass
class AcquisitionReport:
    symbol: str
    source: str | None
    rows: int
    path: str | None
    sha256: str | None
    verified: bool
    errors: list[str]
    adjustment: str | None = None
    coverage_ratio: float | None = None
    provenance_path: str | None = None


def _norm_date(s: str) -> str:
    s = str(s).replace('-', '')
    if len(s) != 8 or not s.isdigit():
        raise ValueError('date must be YYYYMMDD or YYYY-MM-DD')
    return s


def _audit(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    errors=[]; valid=[]; seen=set(); last=''
    for r in rows:
        d=str(r.get('date','')).replace('-','')
        if len(d)!=8 or not d.isdigit(): errors.append(f'invalid_date:{d}'); continue
        if d in seen: errors.append(f'duplicate_date:{d}'); continue
        seen.add(d)
        try:
            o,c,h,l=(float(r[k]) for k in ('open','close','high','low'))
            volume=None if r.get('volume') in (None,'') else float(r['volume'])
            amount=None if r.get('amount') in (None,'') else float(r['amount'])
        except Exception:
            errors.append(f'invalid_numeric:{d}'); continue
        if min(o,c,h,l)<=0 or h<max(o,c) or l>min(o,c):
            errors.append(f'ohlc_logic:{d}'); continue
        if (volume is not None and volume < 0) or (amount is not None and amount < 0):
            errors.append(f'invalid_volume_amount:{d}'); continue
        if last and d < last: errors.append(f'non_monotonic_date:{d}'); continue
        last=d
        valid.append({'date':f'{d[:4]}-{d[4:6]}-{d[6:8]}','open':o,'close':c,'high':h,'low':l,'volume':volume,'amount':amount})
    return valid, errors


def _tushare_rows(symbol: str, start: str, end: str) -> list[dict[str,Any]]:
    token=os.getenv('TUSHARE_TOKEN','').strip()
    if not token: raise RuntimeError('TUSHARE_TOKEN not configured')
    from tushare_provider import TuShareProvider
    suffix='.SH' if symbol.startswith(('6','9')) else '.SZ'
    df=TuShareProvider(token).daily(symbol+suffix,start,end)
    if df is None or len(df)==0: return []
    return [dict(date=str(x.trade_date),open=x.open,close=x.close,high=x.high,low=x.low,volume=x.vol,amount=x.amount) for x in df.sort_values('trade_date').itertuples()]


def _public_rows(symbol,start,end):
    k=fetch_kline(symbol,beg=start,end=end,min_quality='low',allow_raw=False)
    return list(k),getattr(k,'source',None),getattr(k,'adjust',None)


def acquire_daily(symbol: str, start: str, end: str, out_dir='real_data', prefer_tushare=True,
                  strict=True, min_rows=1) -> AcquisitionReport:
    start,end=_norm_date(start),_norm_date(end)
    errors=[]; rows=[]; source=None; adjustment=None; attempted=[]
    if prefer_tushare:
        attempted.append('tushare_daily_raw')
        try:
            rows=_tushare_rows(symbol,start,end)
            if rows: source='tushare_daily_raw'; adjustment='raw'
            else: errors.append('tushare_returned_no_rows')
        except Exception as e: errors.append('tushare:'+type(e).__name__+':'+str(e)[:200])
    if not rows:
        attempted.append('public_fallback')
        try:
            rows,source,adjustment=_public_rows(symbol,start,end)
            if not rows: errors.append('public_sources_returned_no_rows')
        except Exception as e: errors.append('public:'+type(e).__name__+':'+str(e)[:200])
    valid,audit_errors=_audit(rows); errors.extend(audit_errors)
    if len(valid)<min_rows: errors.append(f'insufficient_rows:{len(valid)}<{min_rows}')
    # Coverage is only a coarse calendar-day diagnostic; it is not a trading-calendar claim.
    coverage_ratio=len(valid)/max(1,((datetime.strptime(end,'%Y%m%d')-datetime.strptime(start,'%Y%m%d')).days+1))
    certified=bool(valid) and len(valid)>=min_rows and (not strict or not audit_errors)
    if not certified:
        return AcquisitionReport(symbol,source,len(valid),None,None,False,errors,adjustment,coverage_ratio,None)
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    stem=f'{symbol}_{start}_{end}_{source or "unknown"}'
    path=out/f'{stem}.csv'
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['date','open','close','high','low','volume','amount']); w.writeheader(); w.writerows(valid)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    meta={'schema_version':'phase25','symbol':symbol,'source':source,'attempted_sources':attempted,'adjustment':adjustment,'start':start,'end':end,'rows':len(valid),'sha256':digest,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'audit_errors':audit_errors,'all_errors':errors,'coverage_ratio_calendar':coverage_ratio,'strict':strict}
    mp=path.with_suffix('.metadata.json'); mp.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    return AcquisitionReport(symbol,source,len(valid),str(path),digest,True,errors,adjustment,coverage_ratio,str(mp))


def acquire_universe(symbols,start,end,out_dir='real_data',**kwargs):
    reports=[acquire_daily(str(s),start,end,out_dir,**kwargs) for s in symbols]
    manifest={'schema_version':'phase25','created_at_utc':datetime.now(timezone.utc).isoformat(),'reports':[asdict(r) for r in reports]}
    p=Path(out_dir)/'manifest.json'; p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest
