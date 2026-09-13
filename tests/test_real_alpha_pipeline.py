# -*- coding: utf-8 -*-
import csv,json,hashlib
from pathlib import Path
from real_alpha_pipeline import load_certified_csv, run_real_alpha_pipeline

def _make(path, code, n=300, base=10):
    rows=[]
    for i in range(n):
        # ISO-like monotonic synthetic dates; sufficient for loader test only.
        d=f"2024-{(i//28)+1:02d}-{(i%28)+1:02d}" if i<336 else f"2025-01-{(i-336)%28+1:02d}"
        px=base+i*0.01
        rows.append({"date":d,"open":px,"close":px*1.001,"high":px*1.01,"low":px*.99,"volume":2e8,"amount":2e9})
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    h=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    meta={"strict":True,"sha256":h,"rows":len(rows)}
    Path(path).with_suffix(".metadata.json").write_text(json.dumps(meta),encoding="utf-8")

def test_certified_loader_rejects_tamper(tmp_path):
    p=tmp_path/"x.csv";_make(p,"x",20)
    assert len(load_certified_csv(p))==20
    with open(p,"a",encoding="utf-8") as f:f.write("\\n")
    try: load_certified_csv(p)
    except ValueError as e: assert "sha256" in str(e)
    else: assert False

def test_pipeline_requires_enough_oos(tmp_path):
    s=tmp_path/"s.csv";b=tmp_path/"b.csv";_make(s,"s",100);_make(b,"b",100,3000)
    r=run_real_alpha_pipeline({"600000":str(s)},str(b),"2024-02-01",min_periods=252)
    assert r["verdict"]=="INCONCLUSIVE"
