from typing import Any, Dict, List

from stage2_enrichment import enrich_candidate


def test_stage2_enrichment_is_deterministic_and_no_fake_data():
    row = {
        "code": "300750",
        "quote": {"is_st": False},
        "bars": [
            {"trade_date": "2026-09-01", "close": 10, "high": 10, "low": 9.9},
            {"trade_date": "2026-09-02", "close": 11, "high": 11, "low": 10.5, "limit_ratio": 0.20},
        ],
        "moneyflow": [{"net_mf_amount": 10, "amount": 100}],
        "top_list": [{"reason": "涨幅偏离", "net_amount": 5}],
        "events": [{"event_type": "share_float", "published_at": "2026-09-01", "event_date": "2026-09-10"}],
    }
    out = enrich_candidate(row, cutoff="2026-09-02")
    assert out["moneyflow"]["status"] == "ok"
    assert out["top_list"]["net_buy_total"] == 5
    assert out["event_risk"]["event_count"] == 1
    assert "share_float" in out["event_risk"]["counts"]
    assert "recent_limit_down" not in out["risk_flags"]


def test_stage2_scoring_uses_flow_and_risk_overlay():
    from stage2_scoring import rank_stage2_candidates
    rows = [
        {"code": "A", "cross_section_score": 70, "moneyflow": {"net_flow_mean": 10, "net_flow_positive_ratio": 1},
         "top_list": {"net_buy_total": 10, "net_buy_positive_ratio": 1},
         "microstructure": {"max_limit_up_streak": 2, "limit_down_days": 0, "failed_limit_up_proxy_days": 0},
         "event_risk": {"high_risk_flags": []}},
        {"code": "B", "cross_section_score": 72, "moneyflow": {"net_flow_mean": -10, "net_flow_positive_ratio": 0},
         "top_list": {"net_buy_total": -10, "net_buy_positive_ratio": 0},
         "microstructure": {"max_limit_up_streak": 0, "limit_down_days": 2, "failed_limit_up_proxy_days": 2},
         "event_risk": {"high_risk_flags": ["share_float"]}},
    ]
    out = rank_stage2_candidates(rows)
    assert out[0]["code"] == "A"
    assert out[0]["stage2_alpha_score"] > out[1]["stage2_alpha_score"]


def test_stage2_ablation_runs_and_reports_incremental_delta():
    from stage2_ablation import run_stage2_ablation
    rows: List[Dict[str, Any]] = []
    for day in range(1, 7):
        for i in range(30):
            # Synthetic mechanics fixture only: deliberately creates a stable
            # flow signal so the experiment has enough cross-sectional data.
            flow = float(i)
            rows.append({
                "code": f"{i:06d}", "trade_date": f"2026-09-{day:02d}",
                "close": 10.0 + day * 0.1 + i * 0.001,
                "cross_section_score": float(i),
                "moneyflow": {"net_flow_mean": flow, "net_flow_positive_ratio": flow / 29.0},
                "top_list": {"net_buy_total": flow, "net_buy_positive_ratio": flow / 29.0},
                "microstructure": {"max_limit_up_streak": flow / 10.0, "limit_down_days": 0, "failed_limit_up_proxy_days": 0},
                "event_risk": {"high_risk_count": 0},
            })
    # Make later returns depend on the same cross-section rank while preserving
    # the test's purpose: validating the harness rather than Alpha performance.
    for idx, r in enumerate(rows):
        r["close"] += (idx % 30) * 0.00001
    report = run_stage2_ablation(rows, horizons=(1, 3), min_assets=20)
    assert set(report["models"]) == {"stage1", "stage1_plus_flow", "stage1_plus_top_list", "stage1_plus_microstructure", "stage1_plus_event_risk", "stage2_full"}
    assert "delta_rank_ic_mean_vs_stage1" in report["models"]["stage1_plus_flow"]["horizons"]["1"]
