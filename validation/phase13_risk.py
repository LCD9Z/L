# -*- coding: utf-8 -*-
"""Phase 13: independent red-team risk and execution checks."""
from collections import Counter

def audit_trades(trades, max_single_loss_pct=12.0):
    closed=[t for t in trades if t.get('status')=='closed']
    issues=[]
    if any(t.get('entry_date') and t.get('signal_date') and str(t['entry_date'])<=str(t['signal_date']) for t in closed):
        issues.append('possible_lookahead_or_same_day_execution')
    if any(float(t.get('return_pct',0)) < -abs(max_single_loss_pct) for t in closed):
        issues.append('large_single_trade_loss')
    dates=[t.get('entry_date') for t in closed if t.get('entry_date')]
    concentration=max(Counter(dates).values()) if dates else 0
    return {'ok':not issues,'issues':issues,'closed_trades':len(closed),'max_same_day_entries':concentration}
