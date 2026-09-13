import unittest
from tushare.tushare_ashare_events import TuShareEventProvider

class FakeClient:
    def moneyflow(self, **kwargs): return [{'ts_code':kwargs['ts_code'],'net_mf_amount':10}]
    def top_list(self, **kwargs): return [{'ts_code':kwargs['ts_code'],'net_amount':5}]
    def top_inst(self, **kwargs): return []
    def forecast(self, **kwargs): return [{'ts_code':kwargs['ts_code'],'ann_date':'20260901'}]
    def express(self, **kwargs): return []
    def share_float(self, **kwargs): return []
    def stk_holdertrade(self, **kwargs): return []
    def repurchase(self, **kwargs): return []

class TestTuShareEvents(unittest.TestCase):
    def test_bundle(self):
        p=TuShareEventProvider(client=FakeClient())
        b=p.fetch_bundle('600519.SH','20260901','20260906')
        self.assertEqual(b['provider'],'tushare')
        self.assertEqual(b['moneyflow'][0]['net_mf_amount'],10)
        self.assertEqual(b['forecast'][0]['ann_date'],'20260901')
        self.assertEqual(b['errors'],{})

    def test_partial_failure(self):
        class Bad(FakeClient):
            def repurchase(self, **kwargs): raise RuntimeError('quota')
        b=TuShareEventProvider(client=Bad()).fetch_bundle('600519.SH')
        self.assertEqual(b['repurchase'],[])
        self.assertIn('repurchase',b['errors'])

if __name__=='__main__': unittest.main()
