from corporate_action_ingest import read_codes_from_tdx, read_tushare_csv, audit


def test_ingest_and_audit(tmp_path):
    tdx = tmp_path / "tdx.csv"
    tdx.write_text("date,code,market,close\n2026-01-01,000001,sz,10\n2026-01-01,600000,sh,10\n2026-01-01,399001,sz,10\n", encoding="utf-8")
    actions = tmp_path / "actions.csv"
    actions.write_text("ts_code,ex_date,stk_bo_rate,stk_co_rate,cash_div\n000001.SZ,20260110,0,0,1\n", encoding="utf-8")
    assert read_codes_from_tdx(tdx) == {"000001", "600000"}
    got, rejected = read_tushare_csv(actions)
    assert len(got) == 1 and rejected == 0
    out = tmp_path / "report.json"
    r = audit(tdx, actions, out)
    assert r["requested_stock_codes"] == 2
    assert r["returned_action_codes"] == 1
    assert r["coverage_ratio"] == 0.5
    assert r["alpha_claim_eligible"] is False
    assert out.exists()
