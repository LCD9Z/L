from factor_lab import run_factor_lab
from ashare_factor_engine import compute_factors


def _bars(n=65):
    bars = []
    for i in range(n):
        c = 100.0 + i
        bars.append({
            "trade_date": f"2026-01-{i+1:02d}", "close": c, "open": c-0.5,
            "high": c+1, "low": c-1, "volume": 1000+i*10,
            "amount": 100000+i*1000, "turnover": 1.0 + i/1000,
        })
    return bars


def _panel():
    rows = []
    for d in range(1, 45):
        for i, code in enumerate(("A", "B", "C", "D"), 1):
            close = 100 + d * (i * 2)
            rows.append({"code": code, "trade_date": f"2026-09-{d:02d}", "close": close, "momentum_5d": float(i), "roe": 0.1 * i})
    return rows


def test_bar_factor_engine_adds_phase39_candidates():
    f = compute_factors(_bars())['factors']
    for name in ("momentum_10d", "momentum_20d", "momentum_60d", "momentum_accel_5_20", "breakout_20d", "realized_vol_20d", "realized_vol_60d", "range_pct_20d", "volume_ratio_20d", "turnover_mean_20d"):
        assert name in f


def test_factor_lab_validates_only_available_factors():
    report = run_factor_lab(_panel(), horizons=(1, 5), min_coverage=0.20, min_assets=4)
    assert "momentum_5d" in report["available_factors"]
    assert "roe" in report["available_factors"]
    assert "pe_ttm" not in report["available_factors"]
    assert report["candidate_count"] == 24
    assert report["decision"] in {"PRE_SCREEN_PASS", "INCONCLUSIVE"}


def test_factor_lab_no_rows_is_inconclusive():
    report = run_factor_lab([])
    assert report["decision"] == "INCONCLUSIVE"
    assert report["status"] == "insufficient_data"
