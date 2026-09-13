# -*- coding: utf-8 -*-
"""V3 unified data contracts for the A-share research pipeline.

The contract deliberately separates source data from normalized research data.
Every record keeps source/provider and timestamps so downstream agents can audit
where a fact came from and whether it was available as-of a historical cutoff.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
