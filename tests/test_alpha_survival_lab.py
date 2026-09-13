import unittest
from alpha.alpha_survival_lab import analyse_alpha, alpha_survival_gate, block_bootstrap_mean_ci

class TestAlphaSurvivalLab(unittest.TestCase):
    def test_insufficient_data_is_inconclusive(self):
        r=analyse_alpha([.01]*10,[0]*10,min_periods=20,bootstrap_reps=20,permutation_reps=20)
        self.assertEqual(r['verdict'],'INCONCLUSIVE')
    def test_bootstrap_reproducible(self):
        a=block_bootstrap_mean_ci([.01,-.02,.03,.01],reps=100,seed=7)
        b=block_bootstrap_mean_ci([.01,-.02,.03,.01],reps=100,seed=7)
        self.assertEqual(a,b)
    def test_gate_rejects_inconclusive(self):
        g=alpha_survival_gate([{'name':'x','strategy_returns':[.01]*10,'benchmark_returns':[0]*10,'min_periods':20,'bootstrap_reps':20,'permutation_reps':20}],required_benchmarks=['CSI300'])
        self.assertEqual(g['verdict'],'INCONCLUSIVE')
    def test_gate_requires_all_experiments(self):
        g=alpha_survival_gate([
          {'name':'a','strategy_returns':[.01]*10,'benchmark_returns':[0]*10,'min_periods':20,'bootstrap_reps':20,'permutation_reps':20},
          {'name':'b','strategy_returns':[.01]*30,'benchmark_returns':[0]*30,'min_periods':20,'bootstrap_reps':20,'permutation_reps':20}
        ])
        self.assertEqual(g['verdict'],'NOT_ESTABLISHED')

if __name__=='__main__': unittest.main()
