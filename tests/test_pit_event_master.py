from pit.pit_event_master import active_event_types, attach_pit_events, evidence_summary


def test_risk_warning_and_suspension_are_date_bounded():
    assert "suspension" in active_event_types("002731", "2026-06-10")
    assert "risk_warning" in active_event_types("002731", "2026-07-07")
    assert "suspension" not in active_event_types("002731", "2026-07-07")


def test_open_ended_suspension_is_not_inferred_as_delisting():
    row = attach_pit_events([{"code": "002998", "date": "2026-09-10"}])[0]
    assert row["is_suspended"] is True
    assert "delisted" not in row["pit_event_types"]


def test_evidence_summary_stays_conservative():
    summary = evidence_summary()
    assert summary["complete_historical_st"] is False
    assert summary["complete_historical_suspension"] is False
    assert summary["alpha_claim_eligible"] is False
