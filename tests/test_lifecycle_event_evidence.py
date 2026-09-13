from lifecycle_event_evidence import apply_verified_delistings, lifecycle_evidence_report


def test_verified_delisting_is_attached_without_overwriting_observed_date():
    rows = [{"code": "605081", "last_observed_date": "2026-07-03"}, {"code": "000004", "last_observed_date": "2026-07-13"}]
    out = apply_verified_delistings(rows)
    assert out[0]["certified_delist_date"] == "2026-07-03"
    assert out[0]["last_observed_date"] == "2026-07-03"
    assert out[1]["certified_delist_date"] == "2026-07-14"
    assert out[1]["last_observed_date"] == "2026-07-13"


def test_unknown_code_remains_observed_only():
    out = apply_verified_delistings([{"code": "600004"}])
    assert out[0]["lifecycle_status"] == "OBSERVED_ONLY"
    assert out[0]["certified_delist_date"] == ""


def test_evidence_report_is_conservative():
    r = lifecycle_evidence_report(["605081", "600004"])
    assert r["matched_observed_codes"] == 1
    assert r["alpha_claim_eligible"] is False
