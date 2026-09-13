import json
from pathlib import Path
from factors.factor_blind_test import run_blind_test


def _write_day(root, day, rows):
    p = Path(root) / day[:4] / day[5:7]
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"stock_price_{day.replace('-', '_')}.csv"
    f.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_blind_forward_returns_are_asof_and_b_excluded(tmp_path):
    days = [f"2026-01-{i:02d}" for i in range(1, 25)]
    for i, d in enumerate(days):
        _write_day(tmp_path, d, [
            f"sh600000,{d},{10+i/10},{10+i/10},{10+i/10},{10+i/10},1000,10000",
            f"sz000001,{d},{20+i/20},{20+i/20},{20+i/20},{20+i/20},2000,20000",
            f"sh600000,{d},{10+i/10},{10+i/10},{10+i/10},{10+i/10},1000,10000",
        ])
    # inject a B-share row into the last file; adapter must skip it
    last = next((Path(tmp_path) / "2026" / "01").glob("stock_price_2026_01_24.csv"))
    last.write_text(last.read_text() + "sh900901,2026-01-24,1,1,1,1,100,100\n", encoding="utf-8")
    out = tmp_path / "blind.jsonl"
    report = run_blind_test(tmp_path, out, min_history=5, horizons=(1,3,5))
    assert report["status"] == "ok"
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert rows
    assert all(r["code"] == "600000" or r["code"] == "000001" for r in rows)
    assert rows[0]["date"] < rows[-1]["date"]
    assert set(rows[0]["forward_returns"]).issubset({"1","3","5"})


def test_no_future_bar_used_in_factor_observation(tmp_path):
    days = [f"2026-02-{i:02d}" for i in range(1, 15)]
    for i, d in enumerate(days):
        _write_day(tmp_path, d, [f"sh600001,{d},{10+i},{10+i},{10+i},{10+i},1000,10000"])
    out = tmp_path / "blind.jsonl"
    report = run_blind_test(tmp_path, out, min_history=5, horizons=(1,))
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert report["status"] == "ok"
    first = rows[0]
    assert first["close"] == 15.0
    assert abs(first["forward_returns"]["1"] - (1.0 / 15.0)) < 1e-12
