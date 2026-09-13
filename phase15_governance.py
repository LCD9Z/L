# -*- coding: utf-8 -*-
"""Phase 15: multi-role release governance for A-share research systems.

This module does not claim that a strategy is profitable. It converts evidence from
existing validators into an explicit, conservative release gate reviewed from ten
professional perspectives.
"""

ROLES = (
    'a_share_portfolio_manager',
    'quant_researcher',
    'statistical_researcher',
    'risk_director',
    'data_engineer',
    'trading_rules_specialist',
    'execution_specialist',
    'python_architect',
    'red_team_auditor',
    'research_governance_reviewer',
)

CRITICAL_ISSUES = {
    'data_quality_failed',
    'no_realized_trades',
    'possible_lookahead_or_same_day_execution',
    'future_data_leakage',
    'benchmark_alignment_failed',
}


def _has_issue(validation, name):
    return name in set(validation.get('issues') or [])


def review_release(validation, pit_available=False, benchmark_available=False,
                   stress_available=False, exchange_rules_checked=False,
                   reproducible_manifest=False):
    """Return ten role reviews and a conservative release verdict.

    External evidence is explicit rather than silently assumed. Missing evidence
    produces HOLD/CONDITIONAL instead of PASS.
    """
    issues = list(dict.fromkeys(validation.get('issues') or []))
    dq = validation.get('data_quality') or {}
    perf = validation.get('performance') or {}
    red = validation.get('red_team_audit') or {}
    reviews = {}

    reviews['a_share_portfolio_manager'] = {
        'status': 'PASS' if validation.get('verdict') == 'PASS' and perf.get('max_drawdown_pct', 999) <= 25 else 'HOLD',
        'focus': 'portfolio return versus drawdown and practical deployment risk'}
    reviews['quant_researcher'] = {
        'status': 'PASS' if validation.get('verdict') in ('PASS','CAUTION') and pit_available else 'HOLD',
        'focus': 'out-of-sample evidence, point-in-time universe and sample adequacy'}
    reviews['statistical_researcher'] = {
        'status': 'PASS' if validation.get('verdict') == 'PASS' and not _has_issue(validation, 'insufficient_trade_sample') else 'HOLD',
        'focus': 'sample size and inference reliability'}
    reviews['risk_director'] = {
        'status': 'PASS' if validation.get('verdict') == 'PASS' and not any(i in issues for i in CRITICAL_ISSUES) else 'HOLD',
        'focus': 'drawdown, concentration and hard-stop controls'}
    reviews['data_engineer'] = {
        'status': 'PASS' if dq.get('ok') and reproducible_manifest else 'HOLD',
        'focus': 'input quality and reproducibility'}
    reviews['trading_rules_specialist'] = {
        'status': 'PASS' if exchange_rules_checked else 'HOLD',
        'focus': 'T+1, limit-up/down, suspension and board rules'}
    reviews['execution_specialist'] = {
        'status': 'PASS' if stress_available and not red.get('issues') else 'HOLD',
        'focus': 'slippage, liquidity and execution realism'}
    reviews['python_architect'] = {
        'status': 'PASS' if validation.get('code_tests_passed', False) else 'HOLD',
        'focus': 'tests, determinism and maintainability'}
    reviews['red_team_auditor'] = {
        'status': 'PASS' if red.get('ok') and not any(i in issues for i in CRITICAL_ISSUES) else 'HOLD',
        'focus': 'lookahead, impossible fills and hidden failure modes'}
    reviews['research_governance_reviewer'] = {
        'status': 'PASS' if reproducible_manifest and benchmark_available else 'HOLD',
        'focus': 'benchmarking and experiment traceability'}

    passed = sum(v['status'] == 'PASS' for v in reviews.values())
    critical = sorted(set(issues).intersection(CRITICAL_ISSUES))
    if critical:
        verdict = 'REJECT'
    elif passed >= 9:
        verdict = 'RESEARCH_RELEASE_CANDIDATE'
    elif passed >= 6:
        verdict = 'CONDITIONAL_RESEARCH_ONLY'
    else:
        verdict = 'HOLD_FOR_EVIDENCE'
    return {
        'roles': reviews,
        'role_count': len(ROLES),
        'passed_roles': passed,
        'critical_issues': critical,
        'release_verdict': verdict,
        'not_investment_advice': True,
    }
