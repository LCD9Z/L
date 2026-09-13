from corporate_actions import CorporateAction, build_back_adjustment_factors, evidence_summary


def test_cash_dividend_factor():
    a = CorporateAction("600000", "2026-06-01", "cash_dividend", cash_dividend=1.0)
    assert abs(a.ex_price(10.0) - 9.0) < 1e-9
    assert abs(a.price_factor(10.0) - 0.9) < 1e-9


def test_bonus_and_rights_formula():
    a = CorporateAction("600000", "2026-06-01", "rights_issue", rights_ratio=0.1, rights_price=8.0)
    assert abs(a.ex_price(10.0) - (10.0 + 0.8) / 1.1) < 1e-9


def test_back_adjustment_is_backward_only():
    bars = [
        {"date": "2026-05-29", "close": 10.0},
        {"date": "2026-06-01", "close": 9.0},
        {"date": "2026-06-02", "close": 9.2},
    ]
    action = CorporateAction("600000", "2026-06-01", "cash_dividend", cash_dividend=1.0)
    out = build_back_adjustment_factors(bars, [action])
    assert abs(out[0]["adjusted_close"] - 9.0) < 1e-9
    assert abs(out[1]["adjusted_close"] - 9.0) < 1e-9
    assert abs(out[2]["adjusted_close"] - 9.2) < 1e-9
    assert out[0]["back_adjustment_factor"] == 0.9
    assert out[2]["back_adjustment_factor"] == 1.0


def test_split_requires_share_counts():
    a = CorporateAction("600000", "2026-06-01", "split")
    try:
        a.ex_price(10.0)
    except ValueError as exc:
        assert str(exc) == "share_counts_required_for_split"
    else:
        raise AssertionError("expected validation error")


def test_evidence_is_not_claimed_complete():
    s = evidence_summary([CorporateAction("600000", "2026-06-01", "cash_dividend", cash_dividend=1.0, confidence="verified_public")])
    assert s["verified_event_count"] == 1
    assert s["complete_historical_corporate_actions"] is False
    assert s["alpha_claim_eligible"] is False
