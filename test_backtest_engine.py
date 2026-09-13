from backtest_engine import backtest
# 单调上升数据；突破信号只能在T日产生，入场必须从T+1开盘开始
bars=[]
for i in range(50):
 c=10+i*0.1
 bars.append({'date':f'2026-01-{i+1:02d}' if i<31 else f'2026-02-{i-30:02d}','open':c-0.03,'high':c+0.08,'low':c-0.08,'close':c})
r=backtest('600000',bars,horizon=5,initial_capital=100000)
assert r['trades']>0, r
for t in r['trade_log']:
 if t.get('status')=='closed':
  assert t['entry_date'] > t['signal_date'], t
print('PASS',r['trades'],r['win_rate_pct'],r['max_drawdown_pct'])
