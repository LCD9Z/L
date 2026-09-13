import unittest
from portfolio_backtest import portfolio_backtest

def bars(start=10,n=80):
    out=[]
    for i in range(n):
        # deterministic, gently rising, valid OHLC
        c=start+i*0.12; out.append({'date':f'2024-{1+i//28:02d}-{1+i%28:02d}','open':c-0.03,'high':c+0.08,'low':c-0.08,'close':c,'turnover':3})
    return out
class T(unittest.TestCase):
 def test_no_same_day_entry(self):
    r=portfolio_backtest({'000001':bars(), '000002':bars(12)},threshold=45,top_n=2,horizon=3)
    for t in r['trade_log']: self.assertGreater(t['entry_date'],t['signal_date'])
 def test_portfolio_metrics(self):
    r=portfolio_backtest({'000001':bars()},threshold=45,top_n=1,horizon=3)
    self.assertIn('max_drawdown_pct',r); self.assertGreaterEqual(r['final_equity'],0)
if __name__=='__main__': unittest.main()
