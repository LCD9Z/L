import unittest
from ashare_event_engine import normalize_events, build_event_risk_pack, normalize_forecast, normalize_float_event
from ashare_flow_engine import moneyflow_features, top_list_features
from ashare_universe import screen_row, rank_candidates

class TestV32Ashare(unittest.TestCase):
    def test_pit_event_filter(self):
        rows=[
            {'ts_code':'600000.SH','ann_date':'2026-09-01','title':'公告','source':'x'},
            {'ts_code':'600000.SH','ann_date':'2026-09-07','title':'未来公告','source':'x'},
            {'ts_code':'600000.SH','title':'无日期','source':'x'},
        ]
        out=normalize_events(rows,'forecast',cutoff='2026-09-06T12:00:00')
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['published_at'],'2026-09-01')

    def test_event_risk_labels(self):
        pack=build_event_risk_pack([
            {'event_type':'share_float','published_at':'2026-09-01'},
            {'event_type':'repurchase','published_at':'2026-09-02'},
            {'event_type':'top_list','published_at':'2026-09-03'},
        ], cutoff='2026-09-06')
        self.assertEqual(pack['event_count'],3)
        self.assertTrue(pack['high_risk_flags'])
        self.assertTrue(pack['warnings'])

    def test_moneyflow(self):
        f=moneyflow_features([{'net_mf_amount':10,'amount':100},{'net_mf_amount':-5,'amount':120}])
        self.assertAlmostEqual(f['net_flow_latest'],-5)
        self.assertAlmostEqual(f['net_flow_positive_ratio'],0.5)

    def test_top_list(self):
        f=top_list_features([{'reason':'连续三个交易日内涨幅偏离值累计20%','net_amount':10},{'reason':'日涨幅偏离','net_amount':-2}])
        self.assertEqual(f['rows'],2)
        self.assertAlmostEqual(f['net_buy_total'],8)

    def test_universe_veto(self):
        r=screen_row({'code':'600519','price':100,'is_suspended':True})
        self.assertFalse(r['eligible'])
        self.assertIn('停牌',r['veto'])

    def test_rank(self):
        rows=[{'code':'600001','price':10,'score':70},{'code':'600002','price':10,'score':50}]
        r=rank_candidates(rows, min_score=55)
        self.assertEqual([x['code'] for x in r],['600001'])

    def test_normalizers(self):
        self.assertEqual(normalize_forecast({'ts_code':'600000.SH','ann_date':'2026-09-01','p_change_min':10})['change_min_pct'],10)
        self.assertEqual(normalize_float_event({'ts_code':'600000.SH','float_date':'20260910','float_share':100})['event_date'],'2026-09-10')

if __name__=='__main__': unittest.main()
