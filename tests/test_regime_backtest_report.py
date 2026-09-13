import unittest
from regime.regime_backtest_report import evaluate_backtest
class T(unittest.TestCase):
 def test_metrics(self):
  r={'total_return_pct':10,'equity_curve':[{'date':'1','equity':100},{'date':'2','equity':105},{'date':'3','equity':110}]}
  x=evaluate_backtest(r,[{'close':100},{'close':108}],{'2':'STRONG','3':'WEAK'})
  self.assertIn('cagr_pct',x); self.assertAlmostEqual(x['excess_return_pct'],2)
if __name__=='__main__': unittest.main()
