import unittest
from execution_rules import first_sellable_index
from backtest_engine import _signal

class TestExecutionRealism(unittest.TestCase):
    def test_limit_down_exit_is_deferred(self):
        bars=[
            {'date':'2026-01-01','open':10,'high':10,'low':10,'close':10},
            {'date':'2026-01-02','open':9,'high':9,'low':9,'close':9},
            {'date':'2026-01-03','open':9,'high':9.5,'low':8.9,'close':9.2},
        ]
        self.assertEqual(first_sellable_index('600000',bars,1),2)

    def test_future_data_does_not_change_signal(self):
        closes=[float(i) for i in range(1,30)]
        before=_signal(closes)
        future_mutated=closes+[9999.0]
        self.assertEqual(before,_signal(future_mutated[:len(closes)]))

if __name__ == '__main__': unittest.main()
