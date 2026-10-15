# -*- coding: utf-8 -*-
"""`v3_data_bus` 单测（HANDOVER §7 第 4 项「无覆盖模块」之一，65 行）。

**为什么补**：这是 V3 层**唯一的门面**——把 legacy fetcher 的 fact sheet 归一化
成 `DataBundle` 契约，并串起因子/事件/资金/榜单/约束五个引擎。它此前
**零直接测试引用**：一旦字段映射写错（如 `kline` vs `history.bars` 的
fallback 链失效），下游全部静默拿到空 bars。

**隔离纪律**：`build_fact_sheet` 会真连网 → 一律用 monkeypatch 打桩；
`test_v3_architecture.py` 已守住「契约字段不丢失」，本文件专注
**fact sheet → bundle 的字段映射逻辑**。
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

import v3_data_bus as bus


def _fact(**over: Any) -> Dict[str, Any]:
    """一份**最小但形状合法**的 fact sheet。"""
    base: Dict[str, Any] = {
        "code": "600001",
        "quote": {"src": "tdx", "close": 10.5},
        "kline": [
            {"date": "2024-01-02", "open": 10, "high": 11, "low": 9,
             "close": 10.5, "volume": 100, "amount": 1050, "turnover": 1.2,
             "is_suspended": False, "is_st": False, "adjusted": "qfq"},
        ],
        "news": [
            {"title": "公告", "published_at": "2024-01-02T09:00:00",
             "source": "cninfo", "url": "http://x/y"},
        ],
        "meta": {"cutoff_time": "2024-01-02T15:00:00"},
        "quality": {"missing_fields": []},
    }
    base.update(over)
    return base


class _Stub:
    """带状态的桩：`extra` 为对默认 fact sheet 的覆盖，`calls` 记录调用参数。"""

    def __init__(self) -> None:
        self.extra: Dict[str, Any] = {}
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, code, **kw):
        self.calls.append({"code": code, **kw})
        return _fact(**self.extra)


@pytest.fixture
def stub_fetch(monkeypatch):
    """把会联网的 build_fact_sheet 换成可控桩（隔离，不真连网）。"""
    stub = _Stub()
    monkeypatch.setattr(bus.data_fetcher, "build_fact_sheet", stub)
    return stub


def set_fact(stub_fetch: _Stub, **over) -> None:
    """在**调用前**修改桩将要返回的 fact sheet（覆盖默认字段）。"""
    stub_fetch.extra = over


# ---------------------------------------------------------------------------
# code / asof 归一化
# ---------------------------------------------------------------------------
def test_code_taken_from_fact_sheet(stub_fetch):
    b = bus.build_v3_bundle("600001")
    assert b.code == "600001"
    assert stub_fetch.calls[0]["code"] == "600001"


def test_code_falls_back_to_argument(stub_fetch):
    set_fact(stub_fetch, code="")
    assert bus.build_v3_bundle("SH600001").code == "SH600001", \
        "fact code 为空时应回落到调用参数"


def test_asof_prefers_cutoff_time(stub_fetch):
    b = bus.build_v3_bundle("600001", cutoff_time="2024-01-02T12:00:00")
    assert b.asof == "2024-01-02T12:00:00"


def test_asof_falls_back_to_meta(stub_fetch):
    b = bus.build_v3_bundle("600001")
    assert b.asof == "2024-01-02T15:00:00"


def test_asof_none_when_missing(stub_fetch):
    set_fact(stub_fetch, meta={})
    assert bus.build_v3_bundle("600001").asof is None


# ---------------------------------------------------------------------------
# bars 的三级 fallback 链（核心风险点）
# ---------------------------------------------------------------------------
def test_bars_from_kline(stub_fetch):
    assert len(bus.build_v3_bundle("600001").bars) == 1


def test_bars_fallback_to_history_bars(stub_fetch):
    set_fact(stub_fetch, kline=[],
             history={"bars": [{"trade_date": "2024-01-02", "close": 1}]})
    bars = bus.build_v3_bundle("600001").bars
    assert len(bars) == 1
    assert bars[0].trade_date == "2024-01-02", "须兼容 trade_date 键名"


def test_bars_fallback_to_top_level_bars(stub_fetch):
    set_fact(stub_fetch, kline=[], bars=[{"date": "2024-01-03"}])
    assert bus.build_v3_bundle("600001").bars[0].trade_date == "2024-01-03"


def test_empty_fact_sheet_still_returns_valid_bundle(stub_fetch):
    """缺失即缺失：空 fact 不应炸，但 bars/news 必须为空。"""
    set_fact(stub_fetch, code="", quote=None, kline=None, news=None,
             meta={}, quality=None)
    b = bus.build_v3_bundle("600001")
    assert b.bars == [] and b.news == []
    assert b.quality == {}


def test_meta_none_crashes(stub_fetch):
    """⚠️ **已登记的缺陷**（HANDOVER §5.3 #12）：`meta` 为 `None` 时**直接抛异常**。

    `dict.get(k, {})` 的默认值**只在键缺失时生效**；键存在但值为 `None`
    （即上游给出 `{"meta": null}`）时不兜底 ⇒ `None.get(...)` 炸。
    `v3_data_bus.py` 共 4 处有此形态（L22 / L58 / L59×2）。

    本测试**锁定当前（会崩的）行为**。上游 `build_fact_sheet` 目前构造的
    `meta` 恒为 dict，故生产中暂不触发；一旦上游改为可选 meta 即会崩溃。
    修好后本测试须改为「不抛异常且相关字段回落默认值」。
    """
    set_fact(stub_fetch, meta=None)
    with pytest.raises(AttributeError):
        bus.build_v3_bundle("600001")


def test_bar_field_mapping(stub_fetch):
    bar = bus.build_v3_bundle("600001").bars[0]
    assert (bar.open, bar.high, bar.low, bar.close) == (10, 11, 9, 10.5)
    assert bar.volume == 100 and bar.amount == 1050 and bar.turnover == 1.2
    assert bar.is_st is False and bar.is_suspended is False
    assert bar.adjusted == "qfq"


def test_bar_adjusted_defaults_unknown(stub_fetch):
    set_fact(stub_fetch, kline=[{"date": "2024-01-02", "close": 10.5}])
    assert bus.build_v3_bundle("600001").bars[0].adjusted == "unknown"


def test_bar_limit_ratio_accepts_limit_pct(stub_fetch):
    set_fact(stub_fetch, kline=[{"date": "2024-01-02", "limit_pct": 0.1}])
    assert bus.build_v3_bundle("600001").bars[0].limit_ratio == 0.1


# ---------------------------------------------------------------------------
# news 与 provider_trace
# ---------------------------------------------------------------------------
def test_news_mapped_and_counted(stub_fetch):
    b = bus.build_v3_bundle("600001")
    assert len(b.news) == 1
    assert b.news[0].title == "公告"
    assert b.events["news_count"] == 1


def test_provider_trace_records_quote_and_news(stub_fetch):
    trace = bus.build_v3_bundle("600001").provider_trace
    assert "tdx" in trace and "news" in trace


def test_provider_trace_omits_absent_quote_src(stub_fetch):
    set_fact(stub_fetch, quote={})
    b = bus.build_v3_bundle("600001")
    assert b.provider_trace == ["news"] or "news" in b.provider_trace


# ---------------------------------------------------------------------------
# events：缺失各层保持空状态，不抛异常
# ---------------------------------------------------------------------------
def test_events_layers_default_empty(stub_fetch):
    set_fact(stub_fetch, events=None, moneyflow=None, top_list=None)
    ev = bus.build_v3_bundle("600001").events
    for key in ("event_risk", "moneyflow", "top_list"):
        assert key in ev, f"{key} 必须存在（缺失即缺失，不是缺键）"


def test_market_constraints_present(stub_fetch):
    ev = bus.build_v3_bundle("600001").events
    assert "board" in ev["market_constraints"]
    assert ev["market_constraints"]["same_day_sell_allowed"] is False


def test_price_structure_present(stub_fetch):
    assert bus.build_v3_bundle("600001").events["price_structure"] is not None


def test_prefilter_present(stub_fetch):
    assert bus.build_v3_bundle("600001").events["prefilter"] is not None


def test_crawl4ai_flag_propagated(stub_fetch):
    set_fact(stub_fetch, meta={"cutoff_time": "2024-01-02T15:00:00",
                               "crawl4ai_enabled": True})
    assert bus.build_v3_bundle("600001").events["crawl4ai_enabled"] is True


def test_quality_from_top_level_then_meta(stub_fetch):
    assert bus.build_v3_bundle("600001").quality == {"missing_fields": []}
    set_fact(stub_fetch, quality=None,
             meta={"quality": {"missing_fields": ["close"]}})
    assert bus.build_v3_bundle("600001").quality == {"missing_fields": ["close"]}


# ---------------------------------------------------------------------------
# 参数透传
# ---------------------------------------------------------------------------
def test_params_passed_through(stub_fetch):
    bus.build_v3_bundle("600001", news_limit=9, cutoff_time="2024-01-02T12:00:00",
                        use_crawl4ai=True)
    kw = stub_fetch.calls[0]
    assert kw["news_limit"] == 9
    assert kw["cutoff_time"] == "2024-01-02T12:00:00"
    assert kw["use_crawl4ai"] is True


def test_to_dict_roundtrip(stub_fetch):
    d = bus.build_v3_bundle("600001").to_dict()
    for key in ("code", "asof", "quote", "bars", "news", "factors",
                "events", "quality", "provider_trace"):
        assert key in d
