import unittest
from pit_integrity import audit_pit_rows
from real_alpha_pipeline import run_real_alpha_pipeline
from portfolio_backtest import portfolio_backtest

class TestPhase40PIT(unittest.TestCase):
    def test_future_availability_rejected(self):
        rows=[{"code":"000001","trade_date":"2026-01-05","close":10,"available_at":"2026-01-06"}]
        r=audit_pit_rows(rows, cutoff="2026-01-05")
        self.assertFalse(r["ok"])
        self.assertIn("future_available_data", r["issue_types"])

    def test_duplicate_rejected(self):
        rows=[
            {"code":"000001","trade_date":"2026-01-05","available_at":"2026-01-05"},
            {"code":"000001","trade_date":"2026-01-05","available_at":"2026-01-05"},
        ]
        r=audit_pit_rows(rows, cutoff="2026-01-05")
        self.assertFalse(r["ok"])
        self.assertIn("duplicate_code_trade_date", r["issue_types"])

    def test_market_bars_need_not_have_event_timestamp(self):
        rows=[{"code":"000001","trade_date":"2026-01-05","close":10}]
        r=audit_pit_rows(rows, cutoff="2026-01-05", require_timestamp=False)
        self.assertTrue(r["ok"])

    def test_portfolio_backtest_supports_oos_warmup(self):
        bars=[]
        for i in range(35):
            d=f"2026-01-{i+1:02d}"
            p=10+i*0.1
            bars.append({"date":d,"open":p,"close":p,"high":p,"low":p,"volume":2_000_000,"amount":200_000_000})
        data={"000001":bars}
        r=portfolio_backtest(data, threshold=0, top_n=1, horizon=1, min_avg_amount=0, start_signal_date="2026-01-31")
        self.assertIsInstance(r, dict)

    def test_real_alpha_requires_pit_universe(self):
        r=run_real_alpha_pipeline({}, "missing.csv", "2026-01-01")
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertEqual(r["reason"], "professional_evidence_gate_failed")

if __name__ == '__main__':
    unittest.main()
