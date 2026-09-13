import unittest
from typing import Any, Dict, List

from pit.pit_research_rows import filter_pit_research_rows, attach_research_price

class TestPITResearchRows(unittest.TestCase):
    def test_strict_requires_explicit_true(self):
        rows: List[Dict[str, Any]] = [
            {"code":"000001","pit_trading_eligible":True},
            {"code":"000002","pit_trading_eligible":False},
            {"code":"000003"},
        ]
        self.assertEqual([r["code"] for r in filter_pit_research_rows(rows)], ["000001"])

    def test_research_price_prefers_adjusted(self):
        rows = [{"close":10,"adjusted_close":8}]
        out = attach_research_price(rows)
        self.assertEqual(out[0]["research_price"], 8.0)
        self.assertEqual(out[0]["close"], 10)

    def test_missing_adjusted_keeps_raw(self):
        out = attach_research_price([{"close":"12.5"}])
        self.assertEqual(out[0]["research_price"], 12.5)
        self.assertEqual(out[0]["research_price_source"], "raw_unadjusted")

if __name__ == '__main__': unittest.main()
