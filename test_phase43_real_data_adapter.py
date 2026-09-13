# -*- coding: utf-8 -*-
import json
from pathlib import Path

from daily_csv_adapter import is_ashare_code, normalize_code, parse_row
from recon_price_factor_lab import build_recon_rows


def test_normalize_and_b_share_filter():
    assert normalize_code("sh600519") == "600519"
    assert normalize_code("bj920000") == "920000"
    assert not is_ashare_code("900001")
    assert is_ashare_code("920000")
    assert not is_ashare_code("200001")
    assert is_ashare_code("688001")


def test_parse_real_source_shape():
    row = parse_row(["sh600519", "2026-06-01", "100", "101", "102", "99", "123", "12345"])
    assert row["code"] == "600519"
    assert row["close"] == 101.0
    assert row["amount"] == 12345.0


def test_recon_uses_real_daily_schema_and_excludes_b(tmp_path: Path):
    root = tmp_path / "price" / "2026" / "06"
    root.mkdir(parents=True)
    # 62 observations for one A-share and one B-share row per day.
    for i in range(62):
        d = f"2026-01-{i+1:02d}" if i < 31 else f"2026-02-{i-30:02d}"
        p = root / f"stock_price_2026_{'06'}_{i+1:02d}.csv"
        # filenames are only discovery fixtures; the row date is what is parsed.
        p.write_text(
            f"sh600519,{d},100,101,102,99,1000,100000\n"
            f"sh900001,{d},10,10,10,10,100,1000\n",
            encoding="utf-8",
        )
    out = tmp_path / "rows.jsonl"
    rep = build_recon_rows(root, out, min_history=61)
    assert rep["status"] == "ok"
    assert rep["factor_rows"] == 1
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["code"] == "600519"
