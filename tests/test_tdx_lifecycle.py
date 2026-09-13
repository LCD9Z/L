from tdx_lifecycle import ObservedLifecycle, load_observed_lifecycle, summarize_observed_lifecycle


def test_observed_history_does_not_claim_delisting():
    rows = [
        ObservedLifecycle("600000", "2021-08-02", "2026-09-10", 1200),
        ObservedLifecycle("600001", "2021-08-02", "2026-08-28", 1190),
    ]
    report = summarize_observed_lifecycle(rows, dataset_start="2021-08-02", dataset_end="2026-09-10")
    assert report["certified_listing_delisting"] is False
    assert report["last_observed_before_dataset_end"] == 1
    assert report["possible_lifecycle_gap_codes"] == ["600001"]


def test_boundary_counts():
    rows = [
        ObservedLifecycle("600000", "2021-08-02", "2026-09-10", 1),
        ObservedLifecycle("600001", "2021-08-03", "2026-09-10", 1),
    ]
    report = summarize_observed_lifecycle(rows, dataset_start="2021-08-02", dataset_end="2026-09-10")
    assert report["first_observed_at_dataset_start"] == 1
    assert report["last_observed_at_dataset_end"] == 2


def test_loader_skips_rows_without_observed_rows(tmp_path):
    """行数缺失的记录必须被跳过，不得推断为 0（缺失数据不补造）。"""
    p = tmp_path / "lifecycle.csv"
    p.write_text(
        "code,first_observed_date,last_observed_date,observed_rows\n"
        "600000,2021-08-02,2026-09-10,1200\n"
        "600001,2021-08-02,2026-09-10,\n"
        "600002,2021-08-02,2026-09-10,1190\n",
        encoding="utf-8",
    )
    rows = load_observed_lifecycle(p)
    assert [r.code for r in rows] == ["600000", "600002"]
    assert all(r.observed_rows > 0 for r in rows)
