import unittest
from data_quality import validate_bars
from risk.risk_engine import evaluate_portfolio
from validation.performance import metrics
from point_in_time import load_universe
import tempfile, json, os
class TestPhase12(unittest.TestCase):
 def test_quality(self):
  x=[{'date':'2024-01-01','open':10,'high':11,'low':9,'close':10.5},{'date':'2024-01-02','open':10.5,'high':12,'low':10,'close':11}]
  self.assertTrue(validate_bars(x)['ok'])
 def test_risk_halt(self): self.assertFalse(evaluate_portfolio(drawdown_pct=20)['allow_new_positions'])
 def test_metrics(self): self.assertEqual(metrics([{'equity':100},{'equity':110}])['observations'],2)
 def test_pit(self):
  with tempfile.TemporaryDirectory() as d:
   with open(os.path.join(d,'2024-01-01.json'),'w') as f: json.dump({'codes':['000001']},f)
   self.assertEqual(load_universe(d,'2024-06-01'),['000001'])
if __name__=='__main__': unittest.main()
