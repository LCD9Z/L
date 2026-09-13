import unittest
from industry_strength import rank_industries, stock_industry_bonus
class T(unittest.TestCase):
 def test_rank(self):
  dates=[f'2026-01-{i:02d}' for i in range(1,62)]
  def bars(a): return [{'date':d,'close':100+a*i} for i,d in enumerate(dates)]
  data={'A':bars(1),'B':bars(1.1),'C':bars(.1),'D':bars(.2)}; m={'A':'强行业','B':'强行业','C':'弱行业','D':'弱行业'}
  r=rank_industries(data,m,min_members=2); self.assertEqual(r[0]['industry'],'强行业'); self.assertGreater(stock_industry_bonus('A',r,m),0)
if __name__=='__main__': unittest.main()
