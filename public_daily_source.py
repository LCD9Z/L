# -*- coding: utf-8 -*-
"""Public day-file downloader for real A-share research data.

Designed for 8GB PCs: one trading-day file at a time, atomic writes, SHA-256
manifest, and no silent synthetic fallback.
"""
from __future__ import annotations
import argparse, hashlib, json, os, tempfile
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

DEFAULT_URL = "https://raw.githubusercontent.com/guidebee/china-stock-data/main/data/price/{yyyy}/{mm}/stock_price_{yyyy}_{mm}_{dd}.csv"
UA = "AI-Stock-God/4.5 (+research-data-ingestor)"


def iter_dates(start: str, end: str):
    s = date.fromisoformat(start); e = date.fromisoformat(end)
    if e < s: raise ValueError("end_before_start")
    d = s
    while d <= e:
        yield d
        d += timedelta(days=1)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def fetch_one(d: date, out_root: str | Path, url_template: str = DEFAULT_URL, *, timeout=20, overwrite=False):
    rel = Path(str(d.year)) / f"{d.month:02d}" / f"stock_price_{d.year}_{d.month:02d}_{d.day:02d}.csv"
    out = Path(out_root) / rel
    if out.exists() and not overwrite:
        data = out.read_bytes()
        return {"date": d.isoformat(), "status": "existing", "path": str(out), "bytes": len(data), "sha256": sha256_bytes(data), "url": url_template.format(yyyy=d.year, mm=f"{d.month:02d}", dd=f"{d.day:02d}")}
    url = url_template.format(yyyy=d.year, mm=f"{d.month:02d}", dd=f"{d.day:02d}")
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except Exception as exc:
        return {"date": d.isoformat(), "status": "download_error", "url": url, "error": f"{type(exc).__name__}:{str(exc)[:200]}"}
    if not data.strip():
        return {"date": d.isoformat(), "status": "empty_response", "url": url}
    _atomic_write(out, data)
    lines = sum(1 for ln in data.splitlines() if ln.strip())
    return {"date": d.isoformat(), "status": "downloaded", "path": str(out), "bytes": len(data), "nonempty_lines": lines, "sha256": sha256_bytes(data), "url": url}


def pull_range(start: str, end: str, out_root: str | Path, url_template: str = DEFAULT_URL, *, timeout=20, overwrite=False, stop_on_error=False):
    results=[]
    for d in iter_dates(start,end):
        r=fetch_one(d,out_root,url_template,timeout=timeout,overwrite=overwrite); results.append(r)
        if stop_on_error and r["status"] in {"download_error","empty_response"}: break
    root=Path(out_root); root.mkdir(parents=True,exist_ok=True)
    manifest={"schema_version":"phase44","source_template":url_template,"start":start,"end":end,"results":results}
    (root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    ok=sum(1 for r in results if r["status"] in {"downloaded","existing"})
    return {"status":"ok" if ok==len(results) and results else "partial","requested_days":len(results),"ok_days":ok,"manifest":str(root/"manifest.json"),"results":results}


def main():
    ap=argparse.ArgumentParser(description="Download public daily A-share day files")
    ap.add_argument("--start",required=True); ap.add_argument("--end",required=True)
    ap.add_argument("--out",default="real_market/dayfiles")
    ap.add_argument("--url-template",default=DEFAULT_URL)
    ap.add_argument("--timeout",type=int,default=20); ap.add_argument("--overwrite",action="store_true")
    ap.add_argument("--stop-on-error",action="store_true")
    args=ap.parse_args()
    print(json.dumps(pull_range(args.start,args.end,args.out,args.url_template,timeout=args.timeout,overwrite=args.overwrite,stop_on_error=args.stop_on_error),ensure_ascii=False))

if __name__=="__main__": main()
