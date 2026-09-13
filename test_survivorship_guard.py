from survivorship_guard import audit_survivorship, guard_alpha_claim


def test_incomplete_delisted_history_blocks_alpha_claim():
    audit = audit_survivorship(
        pit_universe=True,
        lifecycle=True,
        delisted_history=False,
        st_history=True,
        suspension_history=True,
        corporate_actions=True,
        missing_delisted_codes=12,
    )
    decision = guard_alpha_claim(audit)
    assert audit.status == "INCONCLUSIVE"
    assert decision["allowed"] is False
    assert decision["reasons"] == ["SURVIVORSHIP DATA INCOMPLETE"]


def test_complete_lifecycle_evidence_allows_alpha_claim():
    audit = audit_survivorship(
        pit_universe=True,
        lifecycle=True,
        delisted_history=True,
        st_history=True,
        suspension_history=True,
        corporate_actions=True,
    )
    decision = guard_alpha_claim(audit)
    assert audit.ok is True
    assert decision["allowed"] is True
    assert decision["status"] == "ALPHA_EVIDENCE_ELIGIBLE"
