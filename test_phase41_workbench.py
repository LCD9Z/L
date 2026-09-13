from typing import Any, Dict, List

from pit_universe_builder import build_snapshot_map, validate_snapshot_coverage
from phase41_data_workbench import build_factor_rows_for_stock


def test_pit_builder_uses_listing_and_delisting_boundaries():
    master = [
        {"code": "000001", "list_date": "2020-01-01"},
        {"code": "600000", "list_date": "2020-01-01", "delist_date": "2020-01-03"},
        {"code": "200001", "list_date": "2020-01-01"},  # B-share excluded
    ]
    snap = build_snapshot_map(master, ["2020-01-02", "2020-01-03", "2020-01-04"])
    assert snap["2020-01-02"] == ["000001", "600000"]
    assert snap["2020-01-03"] == ["000001"]
    assert snap["2020-01-04"] == ["000001"]


def test_pit_coverage_flags_missing_dates():
    r = validate_snapshot_coverage({"2020-01-02": ["000001"]}, ["2020-01-02", "2020-01-03"])
    assert not r["ok"]
    assert "2020-01-03" in r["missing_dates"]


def test_factor_rows_respect_pit_membership():
    bars: List[Dict[str, Any]] = []
    for i in range(70):
        d = f"2020-03-{i+1:02d}" if i < 30 else f"2020-04-{i-29:02d}"
        p = 10 + i * 0.1
        bars.append({"date": d, "open": p, "close": p, "high": p, "low": p, "volume": 1000, "amount": 100000})
    pit = {b["date"]: (["000001"] if idx < 65 else []) for idx, b in enumerate(bars)}
    rows = build_factor_rows_for_stock("000001", bars, pit, min_history=61)
    assert rows
    assert all(r["code"] == "000001" for r in rows)
    assert all(r["date"] in pit and "000001" in pit[r["date"]] for r in rows)
