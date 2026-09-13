from public_daily_source import fetch_one, pull_range


def test_fetch_one_existing_file(tmp_path):
    p = tmp_path / "2026" / "05" / "stock_price_2026_05_06.csv"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"sh600000,2026-05-06,10,10,10,10,100,1000\n")
    r = fetch_one(__import__('datetime').date(2026,5,6), tmp_path)
    assert r["status"] == "existing"
    assert r.get("nonempty_lines", True)
    assert len(r["sha256"]) == 64


def test_pull_range_empty_fake_source_is_partial(tmp_path):
    r = pull_range("2026-05-04", "2026-05-05", tmp_path, "file:///not-real/{yyyy}/{mm}/{dd}.csv")
    assert r["requested_days"] == 2
    assert r["ok_days"] == 0
    assert r["status"] == "partial"
    assert (tmp_path / "manifest.json").exists()
