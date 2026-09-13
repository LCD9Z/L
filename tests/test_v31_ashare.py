import unittest
from ashare.ashare_market import board_of, default_limit_ratio, event_flags
from candidate_prefilter import prefilter_fact_sheet
from exchange_rules import limit_prices

class TestV31Ashare(unittest.TestCase):
    def test_board_and_default_limits(self):
        self.assertEqual(board_of('600519'), '沪主板')
        self.assertEqual(board_of('300750'), '创业板')
        self.assertEqual(board_of('688981'), '科创板')
        self.assertEqual(board_of('430047'), '北交所')
        self.assertEqual(default_limit_ratio('300750'), 0.20)
        self.assertEqual(default_limit_ratio('688981'), 0.20)
        self.assertEqual(default_limit_ratio('430047'), 0.30)
        self.assertEqual(default_limit_ratio('600519'), 0.10)

    def test_daily_limit_metadata_has_priority(self):
        self.assertEqual(limit_prices(10, '600519', {'limit_ratio': 0.20}), (12.0, 8.0))

    def test_event_flags(self):
        bars=[]
        closes=[10,11,11,9.9,10.89]
        for i,c in enumerate(closes):
            prev=closes[i-1] if i else None
            bars.append({'date':f'2026-01-0{i+1}','open':prev or c,'high':c,'low':c,'close':c,'volume':1,'amount':1})
        e=event_flags('600519', bars)
        self.assertGreaterEqual(e['limit_up_days'], 1)

    def test_prefilter_veto_suspension(self):
        fact={'meta':{'code':'600519'},'quote':{'price':10,'is_suspended':True},'kline':[],'quant_factors':{},'quant_score':{}}
        r=prefilter_fact_sheet(fact)
        self.assertFalse(r['eligible_for_llm'])
        self.assertIn('当前停牌', r['veto'])

if __name__=='__main__':
    unittest.main()
