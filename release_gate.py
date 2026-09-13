# -*- coding: utf-8 -*-
"""Conservative release gates; no profitability claim is inferred."""
from __future__ import annotations

from survivorship_guard import SurvivorshipAudit, guard_alpha_claim


def evaluate_release(test_passed, secret_scan_ok, pit_ok, min_tests=25):
    reasons=[]
    if test_passed<min_tests: reasons.append('insufficient_test_coverage')
    if not secret_scan_ok: reasons.append('secret_scan_failed')
    if not pit_ok: reasons.append('point_in_time_validation_failed')
    return {'approved':not reasons,'reasons':reasons,'test_passed':test_passed}


def evaluate_alpha_release(test_passed, secret_scan_ok, pit_ok, survivorship_audit: SurvivorshipAudit, min_tests=25):
    """Gate an Alpha claim; incomplete survivorship evidence is inconclusive, not a failure."""
    base = evaluate_release(test_passed, secret_scan_ok, pit_ok, min_tests)
    decision = guard_alpha_claim(survivorship_audit)
    reasons = list(base['reasons'])
    if not decision['allowed']:
        reasons.append('SURVIVORSHIP DATA INCOMPLETE')
    return {
        **base,
        'approved': not reasons,
        'reasons': reasons,
        'alpha_status': 'ALPHA_EVIDENCE_ELIGIBLE' if not reasons else 'INCONCLUSIVE',
        'survivorship_audit': survivorship_audit.to_dict(),
    }
