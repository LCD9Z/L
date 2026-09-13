# -*- coding: utf-8 -*-
"""TDX 日线适配器测试。

不依赖真实源文件（175MB），全部使用合成夹具，保证 CI 可运行。
"""
import csv
import json
import zipfile

import pytest

from tdx_csv_adapter import (
    PIPELINE_COLUMNS,
    board_of,
    build_pit_universe,
    classify,
    export_stock_csvs,
    is_a_share_stock,
    is_valid_ohlc,
    iter_rows,
    iter_stock_rows,
    scan_inventory,
)

HEADER = "date,code,market,open,high,low,close,volume,amount"


def _row(date, code, market, o=10.0, h=11.0, l=9.0, c=10.5, v=1000, a=1e6):
    return f"{date},{code},{market},{o},{h},{l},{c},{v},{a}"


@pytest.fixture
def sample_zip(tmp_path):
    """构造含股票/ETF/可转债/板块指数/指数的混合源文件。"""
    lines = [HEADER]
    # 真实股票
    for d in range(1, 11):
        lines.append(_row(f"2026-01-{d:02d}", "600519", "sh"))
        lines.append(_row(f"2026-01-{d:02d}", "000001", "sz"))     # 平安银行
        lines.append(_row(f"2026-01-{d:02d}", "300750", "sz"))
    # 上证指数（与平安银行同代码，靠 market 区分）
    for d in range(1, 11):
        lines.append(_row(f"2026-01-{d:02d}", "000001", "sh", o=3000, h=3010, l=2990, c=3005))
    # 通达信板块指数 / ETF / 可转债（均应被排除）
    for d in range(1, 11):
        lines.append(_row(f"2026-01-{d:02d}", "880301", "sh"))
        lines.append(_row(f"2026-01-{d:02d}", "159915", "sz"))
        lines.append(_row(f"2026-01-{d:02d}", "113050", "sh"))

    p = tmp_path / "sample.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("tdx_daily_all.csv", "\n".join(lines) + "\n")
    return str(p)


# ---------------------------------------------------------------------------
# 品种判定
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code,market,expect", [
    ("600519", "sh", "stock"),
    ("601398", "sh", "stock"),
    ("603259", "sh", "stock"),
    ("688981", "sh", "stock"),
    ("000001", "sz", "stock"),        # 平安银行
    ("002415", "sz", "stock"),
    ("300750", "sz", "stock"),
    ("301029", "sz", "stock"),
    ("920819", "bj", "stock"),
    ("830799", "bj", "stock"),        # 北交所旧码段
    ("873169", "bj", "stock"),
    ("000001", "sh", "broad_index"),  # 上证指数 —— 关键消歧
    ("399001", "sz", "broad_index"),
    ("880301", "sh", "tdx_index"),
    ("881155", "sz", "tdx_index"),
    ("899050", "bj", "tdx_index"),
    ("159915", "sz", "fund"),
    ("510300", "sh", "fund"),
    ("161725", "sz", "fund"),
    ("113050", "sh", "convertible_bond"),
    ("128035", "sz", "convertible_bond"),
])
def test_classify(code, market, expect):
    assert classify(code, market) == expect


def test_same_code_different_market_is_disambiguated():
    """000001 在 sh 是指数、在 sz 是股票 —— 必须靠 market 区分，不能只看代码。"""
    assert classify("000001", "sh") != classify("000001", "sz")
    assert is_a_share_stock("000001", "sz") is True
    assert is_a_share_stock("000001", "sh") is False


@pytest.mark.parametrize("code,board", [
    ("600519", "sh_main"), ("688981", "star"), ("000001", "sz_main"),
    ("300750", "chinext"), ("920819", "bse"),
])
def test_board_of(code, board):
    assert board_of(code) == board


# ---------------------------------------------------------------------------
# 流式读取与过滤
# ---------------------------------------------------------------------------

def test_iter_rows_parses_all_types(sample_zip):
    rows = list(iter_rows(sample_zip))
    assert len(rows) == 70                     # 7 个代码 × 10 天
    assert all(set(r) >= {"date", "code", "market", "open", "close", "amount"} for r in rows)


def test_iter_stock_rows_excludes_non_stocks(sample_zip):
    """ETF / 可转债 / 板块指数 / 宽基指数必须被排除。"""
    codes = {r["code"] for r in iter_stock_rows(sample_zip)}
    assert codes == {"600519", "000001", "300750"}
    # 上证指数(000001,sh) 虽与股票同代码，但市场不同，不应被误当作股票重复计入
    markets = {(r["code"], r["market"]) for r in iter_stock_rows(sample_zip)}
    assert ("000001", "sh") not in markets
    assert ("000001", "sz") in markets


def test_scan_inventory_reports_types_and_ranges(sample_zip):
    inv = scan_inventory(sample_zip)
    assert set(inv["by_type"]) >= {"stock", "fund", "tdx_index", "convertible_bond"}
    assert inv["by_type"]["stock"][1] == 3      # 3 只股票
    s = inv["stocks"]["600519"]
    assert s["rows"] == 10 and s["first"] == "2026-01-01" and s["last"] == "2026-01-10"


# ---------------------------------------------------------------------------
# 导出契约（必须能被 real_alpha_pipeline.load_certified_csv 读取）
# ---------------------------------------------------------------------------

def test_export_produces_pipeline_contract(sample_zip, tmp_path):
    out = tmp_path / "stocks"
    res = export_stock_csvs(sample_zip, str(out), min_rows=5)
    assert res["written"] == 3

    path = out / "600519.csv"
    assert path.exists()
    with path.open(encoding="utf-8") as f:
        rd = csv.DictReader(f)
        assert rd.fieldnames is not None
        assert tuple(rd.fieldnames) == PIPELINE_COLUMNS   # 列名与顺序须匹配管线
        rows = list(rd)
    assert len(rows) == 10
    # 必须按日期升序（load_certified_csv 会校验）
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)

    meta = json.loads((out / "600519.metadata.json").read_text(encoding="utf-8"))
    assert meta["strict"] is True
    assert meta["rows"] == 10
    assert len(meta["sha256"]) == 64
    assert meta["adjusted"] is False      # 显式标注不复权


def test_export_metadata_hash_matches_file(sample_zip, tmp_path):
    """sha256 必须与实际文件内容一致，否则管线的完整性校验会失败。"""
    import hashlib
    out = tmp_path / "stocks"
    export_stock_csvs(sample_zip, str(out), min_rows=5)
    for code in ("600519", "000001", "300750"):
        p = out / f"{code}.csv"
        meta = json.loads((out / f"{code}.metadata.json").read_text(encoding="utf-8"))
        assert hashlib.sha256(p.read_bytes()).hexdigest() == meta["sha256"]


def test_export_respects_min_rows(sample_zip, tmp_path):
    """行数不足的股票应被跳过，不得写出空/短文件。"""
    out = tmp_path / "stocks"
    res = export_stock_csvs(sample_zip, str(out), min_rows=50)
    assert res["written"] == 0
    assert not list(out.glob("*.csv"))


def test_export_respects_code_subset(sample_zip, tmp_path):
    out = tmp_path / "stocks"
    res = export_stock_csvs(sample_zip, str(out), codes={"600519"}, min_rows=5)
    assert res["written"] == 1
    assert (out / "600519.csv").exists()
    assert not (out / "300750.csv").exists()


# ---------------------------------------------------------------------------
# OHLC 清洗（管线审计要求"任一行不合规即整体失败"）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("o,h,l,c,ok", [
    (10.0, 11.0, 9.0, 10.5, True),
    (10.0, 10.0, 10.0, 10.0, True),      # 一字板
    (11.0, 10.0, 9.0, 10.5, False),      # open 高于 high
    (10.0, 11.0, 9.0, 12.0, False),      # close 高于 high
    (10.0, 11.0, 9.5, 9.0, False),       # close 低于 low
    (10.0, 8.0, 9.0, 10.0, False),       # high < low
    (0.0, 11.0, 9.0, 10.5, False),       # 零价
    (-1.0, 11.0, 9.0, 10.5, False),      # 负价
])
def test_is_valid_ohlc(o, h, l, c, ok):
    row = {"open": o, "high": h, "low": l, "close": c}
    assert is_valid_ohlc(row) is ok


def test_export_drops_invalid_rows_and_records_count(tmp_path):
    """越界行必须被剔除，且清洗数量要可追溯。"""
    lines = [HEADER]
    for d in range(1, 11):
        lines.append(_row(f"2026-01-{d:02d}", "600519", "sh"))
    lines.append("2026-01-11,600519,sh,10.0,9.0,9.5,10.5,1000,1e6")   # high < low
    lines.append("2026-01-12,600519,sh,10.0,11.0,9.0,12.0,1000,1e6")  # close > high
    p = tmp_path / "bad.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("tdx_daily_all.csv", "\n".join(lines) + "\n")

    out = tmp_path / "stocks"
    res = export_stock_csvs(str(p), str(out), min_rows=5)
    assert res["dropped_invalid_ohlc"] == 2
    with (out / "600519.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10          # 只保留 10 个合法交易日


def test_export_dedupes_same_date(tmp_path):
    """同一 (code, date) 重复必须去重，否则管线会因日期不唯一而失败。"""
    lines = [HEADER]
    for d in range(1, 11):
        lines.append(_row(f"2026-01-{d:02d}", "600519", "sh"))
    lines.append(_row("2026-01-05", "600519", "sh", o=10.1, h=10.9, l=9.9, c=10.6))  # 重复日期（OHLC 合法）
    p = tmp_path / "dup.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("tdx_daily_all.csv", "\n".join(lines) + "\n")

    out = tmp_path / "stocks"
    res = export_stock_csvs(str(p), str(out), min_rows=5)
    assert res["dropped_duplicate_dates"] == 1
    with (out / "600519.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    dates = [r["date"] for r in rows]
    assert len(dates) == len(set(dates)) == 10


def test_exported_data_passes_project_audit(sample_zip, tmp_path):
    """导出结果必须能通过项目自身的 professional_audit 校验（端到端契约）。"""
    from professional_audit import audit_csv

    out = tmp_path / "stocks"
    export_stock_csvs(sample_zip, str(out), min_rows=5)
    for code in ("600519", "000001", "300750"):
        r = audit_csv(str(out / f"{code}.csv"), str(out / f"{code}.metadata.json"),
                      min_rows=5)
        assert r["pass"] is True, f"{code} 未通过项目审计: {r['issues']}"


# ---------------------------------------------------------------------------
# PIT 股票池
# ---------------------------------------------------------------------------

def test_build_pit_universe_respects_listing_date():
    """上市前的日期不得包含该股票；最后交易日之后的日期也不得包含。"""
    stocks = {
        "600519": {"market": "sh", "rows": 5, "first": "2026-01-02", "last": "2026-01-06"},
        "300750": {"market": "sz", "rows": 3, "first": "2026-01-04", "last": "2026-01-06"},
    }
    dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05",
             "2026-01-06", "2026-01-07"]
    snaps = build_pit_universe(stocks, dates)

    assert snaps["2026-01-01"] == []                                   # 均未上市
    assert snaps["2026-01-02"] == ["600519"]
    assert snaps["2026-01-03"] == ["600519"]                           # 300750 未上市
    assert snaps["2026-01-04"] == ["300750", "600519"] or snaps["2026-01-04"] == ["600519", "300750"]
    assert snaps["2026-01-07"] == []                                   # 均已无数据
