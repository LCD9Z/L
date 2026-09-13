from pit.pit_event_master import verified_events
from pit.pit_trading_filter import annotate_rows, filter_snapshot, trading_eligible


def test_suspension_removes_from_trading_universe():
    events = verified_events()
    assert not trading_eligible("002998", "2026-09-10", events=events)
    assert "002998" not in filter_snapshot(["002998", "000001"], "2026-09-10", events=events)


def test_risk_warning_policy_is_explicit():
    events = verified_events()
    assert trading_eligible("002731", "2026-07-07", events=events)
    assert not trading_eligible("002731", "2026-07-07", events=events, exclude_risk_warning=True)


def test_missing_event_is_not_inferred():
    events = verified_events()
    assert trading_eligible("000001", "2026-09-10", events=events)
    rows = annotate_rows([{"code": "000001", "date": "2026-09-10"}], events=events)
    assert rows[0]["pit_trading_eligible"] is True
