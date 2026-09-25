# -*- coding: utf-8 -*-
"""认证数据集增量更新的守卫。

核心断言是**前复权序列不能被盲目追加**：新快照若已重新锚定，
必须整体替换该股序列，否则会得到一条跨接处带假跳空的混合序列
（不报错、只静默污染趋势类信号）。
"""
import csv
import json
import sys

import pytest

import update_certified_dataset as upd

SRC_HEADER = ["date", "code", "name", "board", "status", "open", "high", "low",
              "close", "volume", "amount", "outstanding_share", "turnover",
              "is_st", "st_basis", "source"]
POOL_HEADER = ["code", "name", "board", "status", "list_date", "delist_date",
               "rows", "first_date", "last_date", "is_delisted", "sources"]


def src_row(date, code, close, turnover="0.02", is_st="0", name="测试"):
    return {"date": date, "code": code, "name": name, "board": "沪主板",
            "status": "上市", "open": close, "high": close, "low": close,
            "close": close, "volume": 1000.0, "amount": 100000.0,
            "outstanding_share": 1e8, "turnover": turnover, "is_st": is_st,
            "st_basis": "", "source": "sina"}


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def make_dataset(root, stocks, pool=None, benchmark_days=("2024-01-02",)):
    """stocks: {code: [(date, close), ...]}；pool: {code: {list_date, delist_date}}"""
    for code, bars in stocks.items():
        rows = [{"date": d, "open": c, "high": c, "low": c, "close": c,
                 "volume": 1000.0, "amount": 1e5, "turnover": 2.0, "is_st": "0",
                 "st_basis": "", "source": "sina", "name": "测试",
                 "limit_ratio": 0.1, "limit_basis": "board"} for d, c in bars]
        write_csv(root / "stocks" / f"{code}.csv", upd.OUT_COLUMNS, rows)
        (root / "stocks" / f"{code}.metadata.json").write_text(json.dumps({
            "strict": True, "sha256": "x", "rows": len(rows), "code": code,
        }, ensure_ascii=False), encoding="utf-8")
    pool = pool or {c: {"list_date": "1990-01-01", "delist_date": ""} for c in stocks}
    write_csv(root / "pool_v2.csv", POOL_HEADER,
              [{"code": c, "name": "测试", "board": "沪主板", "status": "上市",
                "list_date": v.get("list_date", ""), "delist_date": v.get("delist_date", ""),
                "rows": len(stocks.get(c, [])), "first_date": "1990-01-01",
                "last_date": stocks.get(c, [("", "")])[-1][0], "is_delisted": "False",
                "sources": "['sina']"} for c, v in pool.items()])
    (root / "pit_universe.json").write_text(json.dumps({
        "snapshots": {"2024-01-02": sorted(stocks)},
        "note": "test", "as_of": "2024-01-02", "calendar_source": "benchmark",
    }, ensure_ascii=False), encoding="utf-8")
    write_csv(root / "benchmark.csv", ["date", "open", "close", "high", "low", "volume", "amount"],
              [{"date": d, "open": 1, "close": 1, "high": 1, "low": 1,
                "volume": 1, "amount": 1} for d in benchmark_days])


def tail(path):
    """取尾部状态；不存在则用例失败（避免每处写 Optional 断言）。"""
    out = upd.tail_of_csv(path)
    assert out is not None, f"{path} 应有内容"
    return out


def run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["update_certified_dataset.py", *argv])
    return upd.main()


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------

def test_tail_of_csv_returns_last_row_and_count(tmp_path):
    p = tmp_path / "x.csv"
    write_csv(p, ["date", "close"], [{"date": "2024-01-02", "close": 10.0},
                                     {"date": "2024-01-03", "close": 11.0}])
    assert upd.tail_of_csv(p) == ("2024-01-03", 11.0, 2)


def test_tail_of_csv_missing_file(tmp_path):
    assert upd.tail_of_csv(tmp_path / "nope.csv") is None


def test_to_out_row_maps_columns_and_derives_limit_ratio():
    row = src_row("2026-08-03", "600000", 10.0, turnover="0.02", is_st="1")
    out = upd.to_out_row(row, "600000")
    got = dict(zip(upd.OUT_COLUMNS, out, strict=True))
    assert got["turnover"] == pytest.approx(2.0)      # 小数 → 百分比
    assert got["limit_ratio"] == pytest.approx(0.10)  # 主板 ST：2026-07-06 起为 10%
    assert got["limit_basis"] == "board_st"


def test_to_out_row_main_board_st_before_rule_change_is_five_percent():
    row = src_row("2026-07-03", "600000", 10.0, is_st="1")
    got = dict(zip(upd.OUT_COLUMNS, upd.to_out_row(row, "600000"), strict=True))
    assert got["limit_ratio"] == pytest.approx(0.05)
    assert got["limit_basis"] == "board_st_legacy"


def test_scan_splits_overlap_and_new_rows(tmp_path):
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [
        src_row("2024-01-02", "600000", 10.0),   # 重叠日
        src_row("2024-01-03", "600000", 10.5),   # 新行
        src_row("2024-01-04", "600000", 11.0),   # 新行
        src_row("2024-01-03", "999999", 1.0),    # 不在数据集内
    ])
    overlap, new_rows = upd.scan_overlap_and_new(
        src, {"600000"}, {"600000": "2024-01-02"})
    assert overlap == {"600000": pytest.approx(10.0)}
    assert [r["date"] for r in new_rows["600000"]] == ["2024-01-03", "2024-01-04"]
    assert "999999" not in new_rows


# ---------------------------------------------------------------------------
# 端到端：三种判定分支
# ---------------------------------------------------------------------------

def test_append_when_anchor_unchanged(tmp_path, monkeypatch):
    root = tmp_path / "ds"
    make_dataset(root, {"600000": [("2024-01-02", 10.0)]},
                 benchmark_days=("2024-01-02", "2024-01-03"))
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [src_row("2024-01-02", "600000", 10.0),
                                src_row("2024-01-03", "600000", 10.5)])
    assert run_main(monkeypatch, ["--dataset", str(root), "--src-qfq", str(src)]) == 0
    with (root / "stocks" / "600000.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["date"] for r in rows] == ["2024-01-02", "2024-01-03"]
    assert tail(root / "stocks" / "600000.csv")[0] == "2024-01-03"
    log = json.loads((root / "update_log.json").read_text(encoding="utf-8"))
    assert log["counts"]["append"] == 1 and log["counts"]["reanchor"] == 0


def test_reanchor_when_overlap_price_differs(tmp_path, monkeypatch):
    """重叠日价格不同 = 新快照已重新锚定 → 必须**整体替换**，不能追加。"""
    root = tmp_path / "ds"
    make_dataset(root, {"600000": [("2024-01-02", 10.0)]},
                 benchmark_days=("2024-01-02", "2024-01-03"))
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [
        src_row("2024-01-02", "600000", 8.0),    # 与旧值 10.0 差 20% > 0.5%
        src_row("2024-01-03", "600000", 8.4),
    ])
    assert run_main(monkeypatch, ["--dataset", str(root), "--src-qfq", str(src)]) == 0
    with (root / "stocks" / "600000.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["close"] for r in rows] == ["8.0", "8.4"]     # 历史段也被替换
    log = json.loads((root / "update_log.json").read_text(encoding="utf-8"))
    assert log["counts"]["reanchor"] == 1
    assert log["changed"][0]["action"] == "reanchor"


def test_undecidable_when_code_absent_from_source(tmp_path, monkeypatch):
    """新快照里没有该股 → **不动**，且必须记入日志（不得当作"无需更新"）。"""
    root = tmp_path / "ds"
    make_dataset(root, {"600000": [("2024-01-02", 10.0)],
                        "000001": [("2024-01-02", 5.0)]})
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [src_row("2024-01-02", "600000", 10.0),
                                src_row("2024-01-03", "600000", 10.5)])
    assert run_main(monkeypatch, ["--dataset", str(root), "--src-qfq", str(src)]) == 0
    log = json.loads((root / "update_log.json").read_text(encoding="utf-8"))
    assert log["undecidable_codes"] == ["000001"]
    assert tail(root / "stocks" / "000001.csv")[0] == "2024-01-02"


def test_tolerance_is_configurable(tmp_path, monkeypatch):
    """偏差 1% 在默认 0.5% 下判为需替换，放宽到 2% 则判为可追加。"""
    def setup():
        root = tmp_path / "ds"
        make_dataset(root, {"600000": [("2024-01-02", 10.0)]})
        src = tmp_path / "src.csv"
        write_csv(src, SRC_HEADER, [src_row("2024-01-02", "600000", 10.1),
                                    src_row("2024-01-03", "600000", 10.6)])
        return root, src

    root, src = setup()
    run_main(monkeypatch, ["--dataset", str(root), "--src-qfq", str(src)])
    assert json.loads((root / "update_log.json").read_text(encoding="utf-8")
                      )["counts"]["reanchor"] == 1

    root2, src2 = setup()
    run_main(monkeypatch, ["--dataset", str(root2), "--src-qfq", str(src2),
                           "--tolerance", "0.02"])
    assert json.loads((root2 / "update_log.json").read_text(encoding="utf-8")
                      )["counts"]["append"] == 1


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    root = tmp_path / "ds"
    make_dataset(root, {"600000": [("2024-01-02", 10.0)]})
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [src_row("2024-01-02", "600000", 10.0),
                                src_row("2024-01-03", "600000", 10.5)])
    before = (root / "stocks" / "600000.csv").read_bytes()
    assert run_main(monkeypatch, ["--dataset", str(root), "--src-qfq", str(src),
                                  "--dry-run"]) == 0
    assert (root / "stocks" / "600000.csv").read_bytes() == before
    assert not (root / "update_log.json").exists()


def test_metadata_sha256_is_refreshed(tmp_path, monkeypatch):
    root = tmp_path / "ds"
    make_dataset(root, {"600000": [("2024-01-02", 10.0)]})
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [src_row("2024-01-02", "600000", 10.0),
                                src_row("2024-01-03", "600000", 10.5)])
    run_main(monkeypatch, ["--dataset", str(root), "--src-qfq", str(src)])
    meta = json.loads((root / "stocks" / "600000.metadata.json").read_text(encoding="utf-8"))
    assert meta["rows"] == 2
    assert meta["last_date"] == "2024-01-03"
    assert meta["sha256"] == upd.sha256_file(root / "stocks" / "600000.csv")
    assert meta["sha256"] != "x"


def test_pit_snapshots_extended_for_new_trading_days(tmp_path, monkeypatch):
    root = tmp_path / "ds"
    make_dataset(root, {"600000": [("2024-01-02", 10.0)]},
                 pool={"600000": {"list_date": "1990-01-01", "delist_date": ""},
                       "000001": {"list_date": "1990-01-01", "delist_date": ""}},
                 benchmark_days=("2024-01-02", "2024-01-03"))
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [src_row("2024-01-02", "600000", 10.0),
                                src_row("2024-01-03", "600000", 10.5)])
    run_main(monkeypatch, ["--dataset", str(root), "--src-qfq", str(src)])
    pit = json.loads((root / "pit_universe.json").read_text(encoding="utf-8"))
    assert "2024-01-03" in pit["snapshots"]
    assert pit["snapshots"]["2024-01-03"] == ["000001", "600000"]
    assert pit["as_of"] == "2024-01-03"


def test_log_declares_what_is_not_updated(tmp_path, monkeypatch):
    """未增量推导的三项必须显式声明，不能让读者以为数据已完全同步。"""
    root = tmp_path / "ds"
    make_dataset(root, {"600000": [("2024-01-02", 10.0)]})
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [src_row("2024-01-02", "600000", 10.0)])
    run_main(monkeypatch, ["--dataset", str(root), "--src-qfq", str(src)])
    log = json.loads((root / "update_log.json").read_text(encoding="utf-8"))
    assert log["not_updated"] == ["不复权源", "复权因子事件", "停牌区间"]
    assert "build_certified_dataset_v2" in log["not_updated_reason"]


def test_missing_dataset_returns_error_code(tmp_path, monkeypatch):
    src = tmp_path / "src.csv"
    write_csv(src, SRC_HEADER, [src_row("2024-01-02", "600000", 10.0)])
    assert run_main(monkeypatch, ["--dataset", str(tmp_path / "nope"),
                                  "--src-qfq", str(src)]) == 2
