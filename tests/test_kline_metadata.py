# -*- coding: utf-8 -*-
"""KlineList 元数据传递测试。

`KlineList` 是带来源/质量标注的 K 线列表。原实现只在 `__getitem__` 切片时复制
`source`，`adjust` / `quality_ratio` / `data_quality` 会被静默丢弃 ——
下游用 `getattr(k, "data_quality", "unknown")` 兜底时不会报错，
而是悄悄拿到 "unknown"，属于**静默错误**。

本测试锁定：切片必须保留全部元数据。
"""
from data_fetcher import KlineList


def _make(n=10, **meta):
    rows = [{"date": f"2026-01-{i+1:02d}", "open": 10.0 + i, "close": 10.0 + i,
             "high": 11.0 + i, "low": 9.0 + i} for i in range(n)]
    kl = KlineList(rows)
    kl.source = meta.get("source", "eastmoney_qfq")
    kl.adjust = meta.get("adjust", "qfq")
    kl.quality_ratio = meta.get("quality_ratio", 0.99)
    kl.data_quality = meta.get("data_quality", "high")
    return kl


def test_class_declares_metadata_attributes():
    """元数据字段应为类属性（而非仅运行时动态挂载），便于类型检查与文档化。"""
    for attr in ("source", "adjust", "quality_ratio", "data_quality"):
        assert hasattr(KlineList, attr), f"KlineList 未声明类属性 {attr}"


def test_default_metadata_is_safe():
    """未标注的 KlineList 应给出安全的默认值，而非 AttributeError。"""
    kl = KlineList([{"date": "2026-01-01", "close": 10.0}])
    assert kl.source is None
    assert kl.adjust is None
    assert kl.quality_ratio == 0.0
    assert kl.data_quality == "unknown"


def test_slice_preserves_all_metadata():
    """核心性质：切片必须保留全部元数据（原实现只保留 source）。"""
    kl = _make(30)
    sliced = kl[-12:]

    assert isinstance(sliced, KlineList)
    assert len(sliced) == 12
    assert sliced.source == kl.source, "切片丢失 source"
    assert sliced.adjust == kl.adjust, "切片丢失 adjust"
    assert sliced.quality_ratio == kl.quality_ratio, "切片丢失 quality_ratio"
    assert sliced.data_quality == kl.data_quality, "切片丢失 data_quality"


def test_slice_of_slice_still_preserves_metadata():
    """连续切片不应逐层丢失元数据。"""
    kl = _make(40)
    twice = kl[-30:][-10:]
    assert twice.data_quality == "high"
    assert twice.adjust == "qfq"
    assert twice.quality_ratio == 0.99


def test_index_access_returns_plain_row():
    """单元素索引应返回原始行，而不是被包装。"""
    kl = _make(5)
    row = kl[0]
    assert isinstance(row, dict)
    assert row["date"] == "2026-01-01"


def test_sliced_kline_keeps_raw_data_warning_semantics():
    """业务含义：不复权数据的告警标记不能因切片而消失。

    fetcher 依据 `source == 'tdx_local_raw'` 决定是否提示"跨除权日跳价"。
    若切片丢掉 source，该告警会静默消失 —— 这正是原缺陷的风险点。
    """
    raw = _make(30, source="tdx_local_raw", adjust="raw", data_quality="low")
    assert raw[-12:].source == "tdx_local_raw"
    assert raw[-12:].adjust == "raw"
    assert raw[-12:].data_quality == "low"
