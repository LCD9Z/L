import unittest
from portfolio_backtest import portfolio_backtest
from alpha_survival_lab import analyse_alpha

class TestPipelineInvariants(unittest.TestCase):
    def bars(self, n=320, code='300750'):
        out=[]
        p=100.0
        for i in range(n):
            p*=1.001 + ((i%7)-3)*0.0002
            out.append({'date':f'2025-01-{i+1:03d}','open':p,'high':p*1.01,'low':p*.99,'close':p,'volume':100000,'amount':p*100000*100})
        return out
    def test_alpha_requires_full_year_oos(self):
        r=analyse_alpha([0.001]*251,[0.0]*251,min_periods=252,bootstrap_reps=10,permutation_reps=10)
        self.assertEqual(r['verdict'],'INCONCLUSIVE')
    def test_no_silent_zero_liquidity_on_ohlcv(self):
        data={'300750':self.bars()}
        r=portfolio_backtest(data,threshold=0,top_n=1,horizon=5,min_avg_amount=1)
        self.assertIn('equity_curve',r)

if __name__=='__main__': unittest.main()
