# -*- coding: utf-8 -*-
"""fetch/akshare_source.py 测试（全部使用测试替身，不联网、不需要 pandas）。"""
import pytest

from fetch import akshare_source
from fetch.akshare_source import (
    AkshareUnavailable,
    fetch_daily_bars,
    make_provider,
    normalize_code,
)


class _FakeDF:
    """模拟 akshare 返回的 pandas DataFrame（只实现 to_dict("records")）。"""

    def __init__(self, records):
        self._records = records

    def to_dict(self, _orient):
        return self._records


_DEFAULT_RECORDS = [
    {"日期": "2024-01-02", "开盘": 10.0, "收盘": 10.5,
     "最高": 10.6, "最低": 9.9, "成交量": 100000, "成交额": 1050000.0,
     "换手率": 1.2},
    {"日期": "2024-01-03", "开盘": 10.5, "收盘": 10.8,
     "最高": 11.0, "最低": 10.4, "成交量": 120000, "成交额": 1290000.0,
     "换手率": 1.4},
]


class _FakeAkshare:
    def __init__(self, records=_DEFAULT_RECORDS, capture=None):
        self._records = records
        self._capture = capture

    def stock_zh_a_hist(self, symbol, period, start_date, end_date, adjust):
        if self._capture is not None:
            self._capture.update(symbol=symbol, period=period,
                                 start_date=start_date, end_date=end_date,
                                 adjust=adjust)
        return _FakeDF(self._records)


# ---------------------------------------------------------------------------
# 代码归一化
# ---------------------------------------------------------------------------

def test_normalize_code_accepts_prefixes():
    assert normalize_code("600519") == "600519"
    assert normalize_code("sh600519") == "600519"
    assert normalize_code("SZ000001") == "000001"
    assert normalize_code("1") == "000001"


def test_normalize_code_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_code("60051A")
    with pytest.raises(ValueError):
        normalize_code("")


# ---------------------------------------------------------------------------
# 抓取与映射
# ---------------------------------------------------------------------------

def test_fetch_maps_columns_and_sorts_by_date():
    capture: dict = {}
    ak = _FakeAkshare(capture=capture)
    bars = fetch_daily_bars("600519", start="2024-01-01", end="2024-01-31",
                            adjust="qfq", akshare_module=ak)
    assert capture["symbol"] == "600519"
    assert capture["start_date"] == "20240101"
    assert capture["adjust"] == "qfq"
    assert [b["date"] for b in bars] == ["2024-01-02", "2024-01-03"]
    first = bars[0]
    assert first["open"] == 10.0 and first["close"] == 10.5
    assert first["adjusted"] == "qfq"
    assert first["source"] == "akshare"
    assert first["provider"] == "stock_zh_a_hist"
    assert first["turnover"] == pytest.approx(1.2)


def test_fetch_raw_adjust_label():
    bars = fetch_daily_bars("000001", adjust="", akshare_module=_FakeAkshare())
    assert bars[0]["adjusted"] == "raw"


def test_fetch_empty_dataframe_returns_empty_list():
    assert fetch_daily_bars("600519", akshare_module=_FakeAkshare(records=[])) == []
    assert fetch_daily_bars("600519", akshare_module=_FakeAkshare(records=None)) == []


def test_fetch_missing_required_column_raises():
    bad = [{"日期": "2024-01-02", "开盘": 10.0, "收盘": 10.5}]  # 缺最高/最低
    with pytest.raises(ValueError, match="缺少必需列"):
        fetch_daily_bars("600519", akshare_module=_FakeAkshare(records=bad))


def test_fetch_invalid_adjust_rejected():
    with pytest.raises(ValueError, match="adjust"):
        fetch_daily_bars("600519", adjust="none", akshare_module=_FakeAkshare())


def test_row_without_date_is_dropped_not_guessed():
    records = [
        {"日期": "", "开盘": 10.0, "收盘": 10.5, "最高": 10.6, "最低": 9.9},
        {"日期": "2024-01-03", "开盘": 10.5, "收盘": 10.8, "最高": 11.0, "最低": 10.4},
    ]
    bars = fetch_daily_bars("600519", akshare_module=_FakeAkshare(records=records))
    assert [b["date"] for b in bars] == ["2024-01-03"]


# ---------------------------------------------------------------------------
# 惰性导入与 Provider 注册
# ---------------------------------------------------------------------------

def test_load_akshare_unavailable_raises_honestly(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "akshare":
            raise ImportError("No module named 'akshare'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(AkshareUnavailable, match="akshare"):
        akshare_source._load_akshare()


def test_make_provider_gate_and_fetch():
    provider = make_provider(priority=70, available_fn=lambda: True)
    assert provider.name == "akshare_daily"
    assert provider.priority == 70
    assert provider.available() is True
    result = provider.fetch("600519", akshare_module=_FakeAkshare())
    assert result and result[0]["close"] == 10.5

    off = make_provider(available_fn=lambda: False)
    assert off.available() is False
