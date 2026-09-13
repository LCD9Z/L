from release_gate import evaluate_alpha_release
from survivorship_guard import audit_survivorship


def test_alpha_release_is_inconclusive_without_delisted_history():
    audit = audit_survivorship(
        pit_universe=True, lifecycle=True, delisted_history=False,
        st_history=True, suspension_history=True, corporate_actions=True,
    )
    result = evaluate_alpha_release(100, True, True, audit)
    assert result['approved'] is False
    assert result['alpha_status'] == 'INCONCLUSIVE'
    assert 'SURVIVORSHIP DATA INCOMPLETE' in result['reasons']


def test_alpha_release_can_pass_when_survivorship_evidence_is_complete():
    audit = audit_survivorship(
        pit_universe=True, lifecycle=True, delisted_history=True,
        st_history=True, suspension_history=True, corporate_actions=True,
    )
    result = evaluate_alpha_release(100, True, True, audit)
    assert result['approved'] is True
    assert result['alpha_status'] == 'ALPHA_EVIDENCE_ELIGIBLE'
