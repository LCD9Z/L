from factor_validation import build_forward_returns, validate_factor


def _fixture():
    rows = []
    # Four stocks, monotonic factor/return relation. Five dates gives enough
    # 1d observations; 20d is intentionally unavailable and must stay None.
    for d in range(1, 7):
        for i, code in enumerate(("A", "B", "C", "D"), 1):
            close = 100 + d * (i * 2)
            rows.append({"code": code, "trade_date": f"2026-09-{d:02d}", "close": close, "factor": i})
    return rows


def test_forward_returns_use_only_later_closes():
    out = build_forward_returns(_fixture(), horizons=(1, 3))
    first = next(r for r in out if r["code"] == "A" and r["trade_date"] == "2026-09-01")
    assert first["forward_return_1d"] > 0
    assert first["forward_return_3d"] > 0
    last = next(r for r in out if r["code"] == "A" and r["trade_date"] == "2026-09-06")
    assert last["forward_return_1d"] is None


def test_factor_validation_reports_cross_sectional_metrics():
    out = validate_factor(_fixture(), "factor", horizons=(1,), min_assets=4)
    m = out["horizons"]["1"]
    assert m["valid_dates"] == 5
    assert m["rank_ic_mean"] > 0.99
    assert m["rank_icir"] is None  # constant IC => undefined stability ratio
    assert m["top_bottom_win_rate"] == 1.0
