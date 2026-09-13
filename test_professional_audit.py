import json, hashlib
from professional_audit import audit_csv, audit_pipeline, ROLES

def _write(tmp_path, rows=60):
    p=tmp_path/'x.csv'
    lines=['date,open,high,low,close,volume']
    for i in range(rows): lines.append(f'2025-01-{i+1:03d},{10+i*.01},{11+i*.01},{9+i*.01},{10.5+i*.01},1000')
    p.write_text('\n'.join(lines),encoding='utf-8')
    m=tmp_path/'x.metadata.json'
    m.write_text(json.dumps({'strict':True,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'rows':rows}),encoding='utf-8')
    return p,m

def test_audit_passes_certified_dataset(tmp_path):
    p,m=_write(tmp_path)
    assert audit_csv(p,m)['pass']

def test_audit_rejects_bad_ohlc(tmp_path):
    p,m=_write(tmp_path)
    p.write_text(p.read_text().replace('10.0,11.0,9.0,10.5','10.0,9.0,11.0,10.5',1))
    assert not audit_csv(p,m)['pass']

def test_pipeline_has_ten_roles(tmp_path):
    p,m=_write(tmp_path)
    r=audit_pipeline({'000001':str(p)},{'000001':str(m)},str(p),str(m))
    assert len(r['roles'])==10 and set(r['roles'])==set(ROLES)
