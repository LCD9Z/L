from pathlib import Path
from typing import Any, Dict, List

from ashare.ashare_cross_section import rank_candidates
from screen_pipeline import ScreenConfig, run_screen
from streaming_topk import TopK


def test_topk_bounded():
    t = TopK(3, key=lambda x: x)
    t.extend(range(10))
    assert t.items() == [9, 8, 7]


def test_cross_section():
    rows = [
        {"code": "A", "factors": {"momentum_5d": 1, "momentum_20d": 1}},
        {"code": "B", "factors": {"momentum_5d": 2, "momentum_20d": 2}},
        {"code": "C", "factors": {"momentum_5d": 0, "momentum_20d": 0}},
    ]
    out = rank_candidates(rows)
    assert out[0]["code"] == "B"
    assert out[-1]["code"] == "C"


def test_pipeline_and_resume(tmp_path: Path):
    rows: List[Dict[str, Any]] = []
    for i in range(100):
        rows.append({"code": f"600{i:03d}", "quote": {"price": 10+i/100, "amount": 1e8,
                     "turnover": 2.0}, "factors": {"momentum_5d": i/100,
                     "momentum_20d": i/200, "realized_vol_20d": 0.2,
                     "drawdown_20d": -i/1000, "volume_ratio_5d": 1+i/100,
                     "amount_ratio_5d": 1+i/100}})
    rows[5]["quote"]["is_suspended"] = True
    out = run_screen(rows, str(tmp_path), ScreenConfig(stage1_keep=30, stage2_keep=10, ai_keep=5, checkpoint_every=20))
    assert out["counts"]["seen"] == 100
    assert out["counts"]["eligible"] == 99
    assert len(out["stage1"]) == 30
    assert len(out["stage2"]) == 10
    assert len(out["ai_candidates"]) == 5
    assert (tmp_path / "screen_snapshot.json").exists()
    resumed = run_screen(rows, str(tmp_path), ScreenConfig(stage1_keep=30, stage2_keep=10, ai_keep=5, checkpoint_every=20), resume=True)
    assert resumed["counts"]["seen"] == 100
