# -*- coding: utf-8 -*-
"""Phase 13 validation suite: quality, sample adequacy, risk and red-team checks."""
from data_quality import validate_bars
from performance import metrics
from phase13_risk import audit_trades

def validate_strategy(result, bars=None, min_trades=30):
    issues=[]
    if bars:
        q=validate_bars(bars)
        if not q['ok']: issues.append('data_quality_failed')
    else:
        q=None
    if result.get('trades',0)<=0: issues.append('no_realized_trades')
    if result.get('trades',0)<min_trades: issues.append('insufficient_trade_sample')
    if result.get('max_drawdown_pct',0)>25: issues.append('drawdown_too_high')
    if result.get('profit_factor') is not None and result['profit_factor']<1: issues.append('profit_factor_below_one')
    p=metrics(result.get('equity_curve',[]))
    audit=audit_trades(result.get('trade_log',[]))
    if not audit['ok']: issues.extend(audit['issues'])
    issues=list(dict.fromkeys(issues))
    critical={'data_quality_failed','no_realized_trades','possible_lookahead_or_same_day_execution'}
    has_critical=bool(critical.intersection(issues))
    verdict='PASS' if not issues else ('FAIL' if has_critical or len(issues)>2 else 'CAUTION')
    return {'verdict':verdict,'issues':issues,'data_quality':q,'performance':p,'red_team_audit':audit,'not_investment_advice':True}
