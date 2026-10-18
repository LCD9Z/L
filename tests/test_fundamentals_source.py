# -*- coding: utf-8 -*-
"""业绩报表数据源适配的守卫。

重点是**诚实失败**：数据源不可用时必须抛 `AkshareUnavailable`，
不能返回空表 —— 那会让"接口挂了"被下游读成"这家公司没业绩"。
另守卫字段解析与去重口径（同 code 多行取公告最晚者）。
"""
import pytest

from typing import Dict

from fetch.fundamentals_source import (
    AkshareUnavailable,
    fetch_all_periods,
    fetch_period,
    normalize_row,
    report_periods,
)


class FakeFrame:
    """替身 DataFrame：只实现被用到的 ``to_dict``。"""

    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return [dict(r) for r in self._rows]


def raw_row(**kw):
    row = {
        "股票代码": "600519", "股票简称": "贵州茅台",
        "每股收益": 1.0, "营业总收入-营业总收入": 1e9, "营业总收入-同比增长": 10.0,
        "净利润-净利润": 1e8, "净利润-同比增长": 12.0,
        "每股净资产": 10.0, "净资产收益率": 8.0, "每股经营现金流量": 0.5,
        "销售毛利率": 90.0, "所处行业": "白酒", "最新公告日期": "2024-04-25",
    }
    row.update(kw)
    return row


class FakeAk:
    def __init__(self, rows_by_period=None, error=None):
        self.rows_by_period = rows_by_period or {}
        self.error = error
        self.calls = []

    def stock_yjbb_em(self, date):
        self.calls.append(date)
        if self.error:
            raise self.error
        return FakeFrame(self.rows_by_period.get(date, []))


@pytest.fixture
def patch_ak(monkeypatch):
    def _install(fake):
        monkeypatch.setattr("fetch.fundamentals_source._ak", lambda: fake)
        return fake
    return _install


# ---------------------------------------------------------------------------
# 报告期生成
# ---------------------------------------------------------------------------

def test_report_periods_covers_four_quarters_per_year():
    ps = report_periods(2024, 2024)
    assert ps == ["20240331", "20240630", "20240930", "20241231"]


def test_report_periods_is_ascending_across_years():
    ps = report_periods(2016, 2017)
    assert len(ps) == 8
    assert ps == sorted(ps)
    assert ps[0] == "20160331" and ps[-1] == "20171231"


# ---------------------------------------------------------------------------
# 字段归一化
# ---------------------------------------------------------------------------

def test_normalize_row_maps_fields():
    rec = normalize_row(raw_row(), "20240331")
    assert rec is not None
    assert rec["code"] == "600519"
    assert rec["report_period"] == "2024-03-31"
    assert rec["announce_date"] == "2024-04-25"
    assert rec["industry"] == "白酒"
    assert rec["eps"] == pytest.approx(1.0)
    assert rec["roe_pct"] == pytest.approx(8.0)
    assert rec["net_profit_yoy_pct"] == pytest.approx(12.0)


def test_normalize_row_zero_pads_code():
    rec = normalize_row(raw_row(股票代码="1"), "20240331")
    assert rec is not None and rec["code"] == "000001"


@pytest.mark.parametrize("value,expected", [
    ("-", None), ("", None), ("nan", None), ("NaN", None),
    ("1,234.5", 1234.5), ("0.0425", 0.0425), (None, None),
    ("abc", None), (3, 3.0),
])
def test_normalize_row_parses_numeric_columns_leniently(value, expected):
    """东财用 ``-`` 表示缺失 —— 必须解析成 None，不能变成 0。"""
    rec = normalize_row(raw_row(每股收益=value), "20240331")
    assert rec is not None
    assert rec["eps"] == (pytest.approx(expected) if expected is not None else None)


def test_normalize_row_rejects_missing_code_or_announce_date():
    assert normalize_row(raw_row(股票代码=""), "20240331") is None
    assert normalize_row(raw_row(最新公告日期=""), "20240331") is None
    assert normalize_row(raw_row(最新公告日期=None), "20240331") is None


@pytest.mark.parametrize("raw_date,expected", [
    ("2024-04-25", "2024-04-25"),
    ("2024/04/25", "2024-04-25"),
    ("20240425", "2024-04-25"),
    ("2024-04-25 00:00:00", "2024-04-25"),
])
def test_normalize_row_normalizes_date_formats(raw_date, expected):
    rec = normalize_row(raw_row(最新公告日期=raw_date), "20240331")
    assert rec is not None and rec["announce_date"] == expected


# ---------------------------------------------------------------------------
# 单期抓取与去重
# ---------------------------------------------------------------------------

def test_fetch_period_returns_sorted_records(patch_ak):
    patch_ak(FakeAk({"20240331": [raw_row(股票代码="600519"),
                                  raw_row(股票代码="000001")]}))
    got = fetch_period("20240331")
    assert [r["code"] for r in got] == ["000001", "600519"]


def test_fetch_period_keeps_latest_announcement_per_code(patch_ak):
    """同一 code 多行（更正公告）→ 保留公告日最晚的一行，不产生重复。"""
    patch_ak(FakeAk({"20240331": [
        raw_row(每股收益=1.0, 最新公告日期="2024-04-25"),
        raw_row(每股收益=1.2, 最新公告日期="2024-06-01"),
    ]}))
    got = fetch_period("20240331")
    assert len(got) == 1
    assert got[0]["eps"] == pytest.approx(1.2)


def test_fetch_period_drops_unparseable_rows(patch_ak):
    patch_ak(FakeAk({"20240331": [raw_row(), raw_row(股票代码="")]}))
    assert len(fetch_period("20240331")) == 1


def test_fetch_period_raises_when_api_fails(patch_ak):
    patch_ak(FakeAk(error=RuntimeError("上游 500")))
    with pytest.raises(AkshareUnavailable, match="stock_yjbb_em"):
        fetch_period("20240331")


def test_fetch_period_raises_when_frame_is_none(patch_ak):
    class NoneAk:
        def stock_yjbb_em(self, date):
            return None
    patch_ak(NoneAk())
    with pytest.raises(AkshareUnavailable):
        fetch_period("20240331")


def test_ak_reports_unavailable_honestly(monkeypatch):
    """akshare 未安装时必须抛 AkshareUnavailable，而不是返回空结果。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "akshare":
            raise ImportError("no akshare")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from fetch import fundamentals_source
    with pytest.raises(AkshareUnavailable, match="akshare 未安装"):
        fundamentals_source._ak()


# ---------------------------------------------------------------------------
# 多期抓取：失败必须留痕
# ---------------------------------------------------------------------------

def test_fetch_all_periods_records_failures(patch_ak):
    """失败的期进入 failed，不得静默跳过 —— 否则覆盖率会被高估。"""
    patch_ak(FakeAk({"20240331": [raw_row()]}, error=RuntimeError("上游 500")))
    seen = []
    out = fetch_all_periods(["20240331", "20240630"], delay=0,
                            on_progress=lambda *a: seen.append((a[2], a[4])))
    assert out["records"] == []
    assert out["ok_periods"] == []
    assert set(out["failed"]) == {"20240331", "20240630"}
    assert len(seen) == 2


def test_fetch_all_periods_mixed_success_and_failure(patch_ak):
    class SelectiveAk(FakeAk):
        def stock_yjbb_em(self, date):
            if date == "20240630":
                raise RuntimeError("上游 500")
            return FakeFrame(self.rows_by_period.get(date, []))

    patch_ak(SelectiveAk({"20240331": [raw_row()]}))
    out = fetch_all_periods(["20240331", "20240630"], delay=0)
    assert out["ok_periods"] == ["20240331"]
    assert list(out["failed"]) == ["20240630"]
    assert len(out["records"]) == 1


def test_fetch_all_periods_treats_empty_period_as_failure(patch_ak):
    """上游返回 0 行 = 该期不可信，不能算"成功但没有数据"。"""
    patch_ak(FakeAk({"20240331": []}))
    out = fetch_all_periods(["20240331"], delay=0)
    assert out["ok_periods"] == []
    assert out["failed"]["20240331"] == "empty_records"


def test_fetch_all_periods_reports_progress_for_every_period(patch_ak):
    patch_ak(FakeAk({"20240331": [raw_row()], "20240630": [raw_row()]}))
    seen = []
    fetch_all_periods(["20240331", "20240630"], delay=0,
                      on_progress=lambda *a: seen.append(a[2]))
    assert seen == ["20240331", "20240630"]


# ---------------------------------------------------------------------------
# 缺陷 #17 守卫：meta 的 source/caveats 必须与 mode 一致
# ---------------------------------------------------------------------------

def _load_fetch_script():
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "_fetch_fundamentals_script", root / "scripts" / "fetch_fundamentals.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_meta_source_is_mode_aware():
    """缺陷 #17：收尾 `_write_meta` 曾硬编码 yjbb 文案，disclosure 模式的
    正确出处（巨潮）被覆盖 —— 磁盘 `disclosure_dates.meta.json` 即为受害者。
    本守卫锁住 `_meta_for_mode`：两个模式的 source 与 caveats 都不许混。"""
    mod = _load_fetch_script()
    done: Dict[str, int] = {"20160331": 10}
    failed: Dict[str, str] = {}
    disc = mod._meta_for_mode("disclosure", done, failed, 1)
    yjbb = mod._meta_for_mode("yjbb", done, failed, 1)
    assert "巨潮" in disc["source"] and "stock_report_disclosure" in disc["source"]
    assert "实际披露" in "".join(disc["caveats"])
    assert "新三板" not in "".join(disc["caveats"])
    assert "yjbb" in yjbb["source"] and "巨潮" not in yjbb["source"]
    assert "新三板" in "".join(yjbb["caveats"])
    assert "实际披露" not in "".join(yjbb["caveats"])


def test_meta_source_modes_are_not_interchangeable():
    """两个模式的 meta 除 source/caveats 外结构一致（可互换比对）。"""
    mod = _load_fetch_script()
    done: Dict[str, int] = {"20160331": 10}
    failed: Dict[str, str] = {"20261231": "empty_records"}
    disc = mod._meta_for_mode("disclosure", done, failed, 2)
    yjbb = mod._meta_for_mode("yjbb", done, failed, 2)
    assert set(disc) == set(yjbb)
    for k in ("periods_total", "rows_by_period", "failed"):
        assert disc[k] == yjbb[k]
    assert disc["source"] != yjbb["source"]
