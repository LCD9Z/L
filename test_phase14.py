import unittest
from data_quality import validate_bars
from research_integrity import build_manifest, assert_manifest_match
from validation_suite import validate_strategy

class TestPhase14(unittest.TestCase):
    def test_invalid_date_rejected(self):
        r=validate_bars([{'date':'not-a-date','open':1,'high':1,'low':1,'close':1}])
        self.assertFalse(r['ok'])
        self.assertEqual(r['errors'][0]['type'],'invalid_date')
    def test_manifest_deterministic(self):
        a=build_manifest(strategy_config={'b':2,'a':1}, universe=['A'], bars=[{'x':1}])
        b=build_manifest(strategy_config={'a':1,'b':2}, universe=['A'], bars=[{'x':1}])
        self.assertTrue(assert_manifest_match(a,b)['ok'])
    def test_no_trades_is_fail(self):
        r=validate_strategy({'trades':0,'equity_curve':[],'trade_log':[]})
        self.assertEqual(r['verdict'],'FAIL')

if __name__=='__main__': unittest.main()
