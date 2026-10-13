# -*- coding: utf-8 -*-
"""V3 unified data contracts for the A-share research pipeline.

The contract deliberately separates source data from normalized research data.
Every record keeps source/provider and timestamps so downstream agents can audit
where a fact came from and whether it was available as-of a historical cutoff.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def to_float_or_none(v: Any) -> Optional[float]:
    """数值列解析的**唯一标准实现**（CODE_REDUNDANCY_AUDIT P1）。

    语义：``None`` / ``""`` / ``"-"`` / ``"--"`` / 非数值 / **NaN** 一律返回 ``None``
    （缺失即缺失，**绝不补造**）；其余返回 ``float``。字符串先 strip 再去千分位逗号，
    兼容东财/baostock 的 ``"1,234.5"`` 列。

    ⚠️ **NaN 必须过滤**：东财/baostock 数值列几乎不给 NaN（空值给 ``""``），
    NaN 主要来自上游计算（0/0、inf-inf）。本项目此前 5 个模块过滤 NaN、
    5 个模块不过滤 —— 同一条 NaN 在因子引擎当缺失、在估值模块当数值，
    **且不报错**（「静默失效」类别）。2026-10-13 统一为此标准，10 处全部替换。

    ⚠️ ``inf`` **不过滤**（与原各处实现一致）：inf 是显式的计算结果，
    由消费方按需处置；本函数只负责「解析」，不做值域政策。
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f else None
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "--", "None", "nan", "NaN"):
        return None
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


@dataclass
class DataProvenance:
    source: str
    provider: str
    retrieved_at: Optional[str] = None
    published_at: Optional[str] = None
    asof: Optional[str] = None
    source_url: Optional[str] = None
    content_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class MarketBar:
    code: str
    trade_date: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    amount: Optional[float]
    turnover: Optional[float] = None
    limit_ratio: Optional[float] = None
    is_suspended: Optional[bool] = None
    is_st: Optional[bool] = None
    adjusted: str = "unknown"
    provenance: Optional[DataProvenance] = None

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["provenance"] = self.provenance.to_dict() if self.provenance else None
        return d


@dataclass
class NewsItem:
    code: str
    title: str
    published_at: Optional[str]
    source: str
    url: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    crawled_at: Optional[str] = None
    content_hash: Optional[str] = None
    provenance: Optional[DataProvenance] = None

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["provenance"] = self.provenance.to_dict() if self.provenance else None
        return d


@dataclass
class DataBundle:
    code: str
    asof: Optional[str]
    quote: Dict[str, Any] = field(default_factory=dict)
    bars: List[MarketBar] = field(default_factory=list)
    news: List[NewsItem] = field(default_factory=list)
    factors: Dict[str, Any] = field(default_factory=dict)
    events: Dict[str, Any] = field(default_factory=dict)
    quality: Dict[str, Any] = field(default_factory=dict)
    provider_trace: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "asof": self.asof,
            "quote": self.quote,
            "bars": [b.to_dict() for b in self.bars],
            "news": [n.to_dict() for n in self.news],
            "factors": self.factors,
            "events": self.events,
            "quality": self.quality,
            "provider_trace": self.provider_trace,
        }
