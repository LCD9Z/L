from pathlib import Path
import real_data_collector as r

def test_audit_rejects_bad_and_duplicates():
    rows=[{'date':'20240102','open':10,'close':11,'high':11,'low':9,'volume':1,'amount':2},
          {'date':'20240102','open':10,'close':11,'high':11,'low':9},
          {'date':'20240103','open':10,'close':11,'high':9,'low':8}]
    valid, errors=r._audit(rows)
    assert len(valid)==1 and any('duplicate_date' in e for e in errors) and any('ohlc_logic' in e for e in errors)

def test_fallback_and_fingerprint(monkeypatch,tmp_path):
    monkeypatch.delenv('TUSHARE_TOKEN',raising=False)
    class K(list): source='eastmoney_qfq'; adjust='qfq'
    k=K([{'date':'2024-01-02','open':10,'close':11,'high':12,'low':9,'volume':100,'amount':1000}])
    monkeypatch.setattr(r,'fetch_kline',lambda *a,**kw:k)
    report=r.acquire_daily('600519','20240101','20240131',tmp_path)
    assert report.verified and report.rows==1 and report.source=='eastmoney_qfq'
    assert report.path is not None and report.sha256 is not None
    assert Path(report.path).exists() and len(report.sha256)==64

def test_tushare_preferred(monkeypatch,tmp_path):
    monkeypatch.setenv('TUSHARE_TOKEN','not-a-real-token')
    monkeypatch.setattr(r,'_tushare_rows',lambda *a,**kw:[{'date':'20240102','open':10,'close':11,'high':12,'low':9,'volume':1,'amount':2}])
    report=r.acquire_daily('600519','20240101','20240131',tmp_path)
    assert report.source=='tushare_daily_raw' and report.adjustment=='raw'

def test_strict_mode_refuses_partially_bad_dataset(monkeypatch,tmp_path):
    class K(list): source='eastmoney_qfq'; adjust='qfq'
    k=K([{'date':'20240102','open':10,'close':11,'high':12,'low':9}, {'date':'20240102','open':10,'close':11,'high':12,'low':9}])
    monkeypatch.delenv('TUSHARE_TOKEN',raising=False)
    monkeypatch.setattr(r,'fetch_kline',lambda *a,**kw:k)
    report=r.acquire_daily('600519','20240101','20240131',tmp_path,strict=True)
    assert not report.verified and report.path is None

def test_non_strict_mode_records_bad_rows(monkeypatch,tmp_path):
    class K(list): source='eastmoney_qfq'; adjust='qfq'
    k=K([{'date':'20240102','open':10,'close':11,'high':12,'low':9}, {'date':'20240102','open':10,'close':11,'high':12,'low':9}])
    monkeypatch.delenv('TUSHARE_TOKEN',raising=False)
    monkeypatch.setattr(r,'fetch_kline',lambda *a,**kw:k)
    report=r.acquire_daily('600519','20240101','20240131',tmp_path,strict=False)
    assert report.verified and any('duplicate_date' in e for e in report.errors)
