# -*- coding: utf-8 -*-
"""V3 unified data contracts for the A-share research pipeline.

The contract deliberately separates source data from normalized research data.
Every record keeps source/provider and timestamps so downstream agents can audit
where a fact came from and whether it was available as-of a historical cutoff.

A6（EVIDENCE_CHAIN_PREREG 组件 A6）：`DataProvenance` 增三个 PIT 契约字段
（`availability_lag` / `null_policy` / `source_version`），并提供
`register_source` 注册器 —— 新增数据源缺任一字段即 `IncompleteContractError`。
只注册**有代码依据**的源；无证据的动态爬取源入 `LEGACY_SOURCES` 显式遗产集，
不伪造口径。
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
    # A6 三字段（EVIDENCE_CHAIN_PREREG）：默认 None 不破坏既有构造点；
    # 「新增数据源必须填」由 register_source 强制，不靠构造点自觉。
    availability_lag: Optional[str] = None
    null_policy: Optional[str] = None
    source_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


# --------------------------------------------------------------------------
# A6：数据源契约注册器（EVIDENCE_CHAIN_PREREG 组件 A6）
#
# 背景：survey §8.4-A6 —— `data_contracts.py` 手写 dataclass 缺三个字段，
# 「数据什么时候可用、缺失时怎么办、是哪一个版本」没有强制声明位。
# 验收原话：「新增数据源必须填；缺字段时校验失败」。
# --------------------------------------------------------------------------

class ContractError(ValueError):
    """数据源契约相关错误的基类。"""


class IncompleteContractError(ContractError):
    """注册数据源时 availability_lag / null_policy / source_version 有缺失。"""


class UnknownSourceError(ContractError):
    """查询未注册的数据源契约。"""


@dataclass(frozen=True)
class DataSourceContract:
    """一个数据源的 PIT 契约。四要素缺一不可（注册时强制）。"""
    name: str
    availability_lag: str
    null_policy: str
    source_version: str
    note: str = ""


#: 模块级注册表（单一事实来源）。
SOURCE_REGISTRY: Dict[str, DataSourceContract] = {}

#: 显式遗产集：source 名在运行时才可知（来自数据行）、且无滞后口径证据的
#: 既有构造点。入集即「不注册、不伪造、但点名」——`validate_all_sources`
#: 会对它们出具遗产报告而不是静默通过。
LEGACY_SOURCES = frozenset({"v3_data_bus 动态爬取源（source 名来自数据行）"})


def _require_text(value: Optional[str], field_name: str, name: str) -> str:
    """契约字段的非空校验：None 与空串/纯空格一律视为缺失。"""
    if value is None or not str(value).strip():
        raise IncompleteContractError(
            f"数据源 {name!r} 缺少契约字段 {field_name!r}"
            "（availability_lag / null_policy / source_version 缺一不可）"
        )
    return str(value)


def register_source(
    name: str,
    *,
    availability_lag: Optional[str],
    null_policy: Optional[str],
    source_version: Optional[str],
    note: str = "",
) -> DataSourceContract:
    """注册一个数据源；三字段任一缺失即抛 `IncompleteContractError`。

    重复注册同名源同样抛错（契约是单一事实来源，不允许静默覆盖）。
    """
    if name in SOURCE_REGISTRY:
        raise ContractError(f"数据源 {name!r} 已注册，不允许静默覆盖")
    contract = DataSourceContract(
        name=name,
        availability_lag=_require_text(availability_lag, "availability_lag", name),
        null_policy=_require_text(null_policy, "null_policy", name),
        source_version=_require_text(source_version, "source_version", name),
        note=note,
    )
    SOURCE_REGISTRY[name] = contract
    return contract


def contract_for(name: str) -> DataSourceContract:
    """取契约；未注册抛 `UnknownSourceError`（不返回 None 让调用方猜）。"""
    try:
        return SOURCE_REGISTRY[name]
    except KeyError:
        raise UnknownSourceError(
            f"数据源 {name!r} 未注册；新数据源必须 register_source"
            "（availability_lag / null_policy / source_version 缺一不可）"
        ) from None


def validate_source_registered(name: str) -> DataSourceContract:
    """校验用入口：等价于 contract_for，语义上供 pipeline 启动时调用。"""
    return contract_for(name)


def validate_all_sources() -> Dict[str, Any]:
    """汇总注册表状态：已注册源逐字段非空自检 + 遗产集点名。

    不抛错（合法性在 register_source 时已强制）；返回值供启动日志与测试。
    """
    incomplete = [
        c.name for c in SOURCE_REGISTRY.values()
        if not (c.availability_lag.strip() and c.null_policy.strip()
                and c.source_version.strip())
    ]
    return {
        "registered": sorted(SOURCE_REGISTRY),
        "n_registered": len(SOURCE_REGISTRY),
        "incomplete": incomplete,
        "legacy_sources": sorted(LEGACY_SOURCES),
        "n_legacy": len(LEGACY_SOURCES),
    }


# 本轮注册的三个源（EVIDENCE_CHAIN_PREREG §四.1）——每个字段都有代码依据，
# 依据写进 note，复核者可按图索骥。
register_source(
    "cninfo_disclosure",
    availability_lag="公告日当日可用（PIT 主口径以真实公告日为准）",
    null_policy="公告日未知 ⇒ 法定截止日兜底（pit_fundamentals.resolve_availability）",
    source_version="disclosure_dates.jsonl 的 meta fetched_at（抓取时刻即版本）",
    note="巨潮 stock_report_disclosure；兜底行为见 pit/pit_fundamentals.py",
)
register_source(
    "eastmoney_appointment",
    availability_lag="预约日 / 实际公告日当日可用",
    null_policy="ACTUAL_PUBLISH_DATE 为空即缺失，不补造（fetch/disclosure_eastmoney.py）",
    source_version="disclosure_eastmoney.jsonl 的 meta fetched_at + 端点 RPT_PUBLIC_BS_APPOIN",
    note="东财预约披露第二源；预约日 ≠ 实际披露日，缺失即缺失",
)
register_source(
    "fundamentals_yjbb",
    availability_lag="报告期 → 公告日由披露日表决定（resolve_availability）",
    null_policy="公告日未知 ⇒ 法定截止日兜底（pit_fundamentals.resolve_availability）",
    source_version="fundamentals.jsonl 的 meta fetched_at（抓取时刻即版本）",
    note="东财业绩报表（yjbb）；PIT 可用性不在本表内，在披露日表",
)


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
