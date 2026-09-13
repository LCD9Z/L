import unittest
from walk_forward import walk_forward, compare, score_history

class TestWalkForward(unittest.TestCase):
 def bars(self,n=100):
  out=[]; price=10.0
  for i in range(n):
   price*=1.002 if i%9 else 1.012
   out.append({'date':f'2024-01-{i+1:03d}','open':price*.995,'high':price*1.01,'low':price*.99,'close':price,'turnover':3})
  return out
 def test_no_lookahead(self):
  r=walk_forward('600000',self.bars(),threshold=0,horizon=3)
  for t in r['trade_log']:
   if t.get('status')=='closed': self.assertGreater(t['entry_date'],t['signal_date'])
 def test_compare(self):
  r=compare('600000',self.bars(),threshold=0,horizon=3)
  self.assertIn('legacy',r); self.assertIn('optimized',r)
 def test_score(self): self.assertGreaterEqual(score_history(self.bars())['score'],0)
if __name__=='__main__': unittest.main()
