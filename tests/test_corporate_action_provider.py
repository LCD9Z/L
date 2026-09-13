from corporate.corporate_action_provider import normalize_tushare_dividend, audit_action_coverage


def test_normalize_tushare_cash_bonus():
    a = normalize_tushare_dividend({
        "ts_code": "600000.SH", "ex_date": "20260601",
        "stk_bo_rate": 2.0, "stk_co_rate": 3.0, "cash_div": 0.5,
    })
    assert a is not None
    assert a.normalized_code() == "600000"
    assert a.event_type == "cash_bonus"
    assert abs(a.bonus_ratio - 0.5) < 1e-9
    assert abs(a.cash_dividend - 0.5) < 1e-9


def test_missing_ex_date_is_not_invented():
    assert normalize_tushare_dividend({"ts_code": "600000.SH", "cash_div": 1.0}) is None


def test_coverage_detects_missing_codes():
    a = normalize_tushare_dividend({"ts_code": "600000.SH", "ex_date": "20260601", "cash_div": 1.0})
    assert a is not None
    audit = audit_action_coverage(["600000", "000001"], [a])
    assert audit.requested_codes == 2
    assert audit.returned_codes == 1
    assert audit.event_rows == 1
    assert audit.has_complete_coverage is False
    assert audit.missing_codes == ("000001",)
