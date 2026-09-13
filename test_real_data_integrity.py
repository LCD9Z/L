import real_data_integrity as i

def test_integrity_detects_tampering(tmp_path):
    p=tmp_path/'x.csv'; p.write_text('date,open,close,high,low,volume,amount\n2024-01-02,1,1,1,1,,\n',encoding='utf-8')
    r={'symbol':'x','verified':True,'path':str(p),'sha256':i.sha256(p),'rows':1}
    assert i.verify_report(r)['passed']
    p.write_text(p.read_text(encoding='utf-8')+'2024-01-03,1,1,1,1,,\n',encoding='utf-8')
    assert not i.verify_report(r)['passed']
