import unittest
from ashare.ashare_factor_engine import compute_factors, score_candidate
from data_contracts import DataProvenance, NewsItem
from provider_router import Provider, ProviderRouter
from quant_skill_router import route


class TestV3Architecture(unittest.TestCase):
    def test_factor_layer_is_deterministic(self):
        bars = [
            {"trade_date": f"2026-01-{i:02d}", "close": 100+i, "volume": 1000+i*10, "amount": 100000+i*1000}
            for i in range(1, 25)
        ]
        a = compute_factors(bars)
        b = compute_factors(bars)
        self.assertEqual(a, b)
        self.assertGreater(score_candidate(a)["score"], 50)

    def test_provider_router_fallback(self):
        r = ProviderRouter()
        r.register(Provider("bad", 1, lambda: True, lambda **_: None))
        r.register(Provider("good", 2, lambda: True, lambda **_: {"ok": True}))
        result, name, errors = r.fetch_first()
        self.assertEqual(name, "good")
        self.assertEqual(result, {"ok": True})
        # "bad" 是以「返回 None」而非抛异常的方式失败，故不记入 errors
        self.assertEqual(errors, [])

    def test_skill_router(self):
        x = route("回测")
        self.assertTrue(x["ok"])
        self.assertEqual(x["skill"], "backtest")

    def test_news_provenance(self):
        n = NewsItem("600519", "x", "2026-01-01T09:00:00", "test", provenance=DataProvenance("test", "test"))
        self.assertEqual(n.to_dict()["provenance"]["source"], "test")


if __name__ == "__main__":
    unittest.main()
