# -*- coding: utf-8 -*-
"""Simple strategy health checks for live paper-trading records."""
def evaluate_health(curve, trades, max_drawdown_alert=20.0, consecutive_loss_alert=5):
    equity=[float(x['equity']) for x in curve if x.get('equity') is not None]
    peak=0.0; mdd=0.0
    for x in equity:
        peak=max(peak,x)
        if peak: mdd=max(mdd,(peak-x)/peak*100)
    closed=[x for x in trades if x.get('status','closed')=='closed' and x.get('return_pct') is not None]
    streak=0; worst=0
    for x in closed:
        if float(x['return_pct'])<0: streak+=1; worst=max(worst,streak)
        else: streak=0
    alerts=[]
    if mdd>=max_drawdown_alert: alerts.append('drawdown_alert')
    if worst>=consecutive_loss_alert: alerts.append('consecutive_loss_alert')
    return {'healthy':not alerts,'alerts':alerts,'max_drawdown_pct':round(mdd,3),'max_consecutive_losses':worst,'closed_trades':len(closed)}
