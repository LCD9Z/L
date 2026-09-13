from factors.factor_registry import availability, select_available
from factors.factor_gate import gate_factors


def test_registry_does_not_fabricate_missing_sources():
    rows = [{"momentum_5d": 0.1}, {"momentum_5d": 0.2}, {}]
    info = availability(rows)
    assert info["momentum_5d"]["status"] == "available"
    assert info["roe"]["status"] == "missing_source"
    assert "momentum_5d" in select_available(rows)
    assert "roe" not in select_available(rows)


def test_factor_gate_prunes_redundant_factor():
    rows = [{"a": i, "b": i, "c": (i % 3) - 1} for i in range(30)]
    def report(name):
        return {"horizons": {"5": {"rank_ic_mean": 0.08 if name != "c" else 0.04,
                                      "rank_icir": 1.0, "rank_ic_positive_ratio": 0.7,
                                      "top_bottom_spread_mean": 0.02}}}
    result = gate_factors({"a": report("a"), "b": report("b"), "c": report("c")}, rows=rows, horizon=5)
    assert result["selected"] == ["a", "c"]
    assert result["pruned_redundant"] == ["b"]
    assert "c" in result["selected"] or "c" in [x["factor"] for x in result["all"]]
