# -*- coding: utf-8 -*-
"""证券代码映射表（DATA_CHANNEL_PREREG 组件 B，② 借 `QuantConnect/Lean` MapFile）。

## 解决什么问题

A 股的 6 位代码**不是全局唯一的命名空间**：`000905` 既是深交所股票
（厦门港务），又是上交所指数（中证500）；`000001` 既是平安银行（SZ），
又是上证指数（SH）。Lean 的 MapFile 因此以 `(market, symbol)` 为键，
并显式记录 listed/delisted/successor。

本项目此前的对应物是 `fetch/common.py::normalize_code` —— 它对裸码
**静默取一个**：`000905` → `0.000905`（SZ），未知前缀 → 默认沪。
本模块提供**严格层**：歧义必报错，调用方必须显式给市场。

## 命名空间规则（2026-10-18 扫全库实证，非拍脑袋）

扫 `D:/tdx_dataset_v3/stocks/` 全部 5,667 个 metadata 后，实际出现的
代码段只有：SZ `000/001/002/003/300/301/302`、SH `600/601/603/605/688/689`、
BJ `920`。其中两段是**单票段**，规则若只写「常识段」会把它们判成未知：

* `302132` 中航成飞（SZ 主板，2024 年换代码段后上市）；
* `689009` 九号公司（SH 科创板 CDR）。

⇒ 规则按实证写全，未知代码段抛 :class:`UnknownMarketError`，**不猜**。

## successor 为什么留空

数据集里**没有** successor 的可靠来源：`corporate_actions.csv` 只有复权
因子，不含换股/吸收合并。实测两个易误判的实例：`002190` 成飞集成与
`302132` 中航成飞**是两家不同公司**（虽同属成飞集团系），行情区间重叠
**不构成** successor 证据；`300114` 中航电测（→ 中航成飞换码）**不在
本数据集内**，无从观测。⇒ successor 一律空串，表级统计
`successor_known_count`（预期 0）。**不硬凑** —— 猜错一条映射比没有映射
更危险：它会静默改变复权与生存偏差的处理对象。

## secid 格式

东财 `1.600000` / `0.000001` / `0.<bj>`（BJ 段前缀沿用
`fetch.common.normalize_code` 的既有口径，不在此重新推导）；
baostock `sh.600000` / `sz.000001` / `bj.430047`。**两库格式不同，
不得互抄**（项目记忆既有判据）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = [
    "AMBIGUOUS_BARE_RANGE",
    "MARKET_PREFIXES",
    "AmbiguousCodeError",
    "MarketMismatchError",
    "SecurityEntry",
    "SecurityMap",
    "SecurityMapError",
    "UnknownCodeError",
    "UnknownMarketError",
    "is_ambiguous_bare",
    "market_of_code",
    "secid_baostock",
    "secid_eastmoney",
]

#: 裸码歧义区：SH 指数命名空间（000001 上证指数 …）与 SZ 股票命名空间
#: （000001 平安银行 …）在 000000–000999 上重叠。该区间内 `resolve(code)`
#: **必须抛** AmbiguousCodeError —— 两个命名空间都有意义，静默取一个即错。
AMBIGUOUS_BARE_RANGE: Tuple[str, str] = ("000000", "000999")

#: 市场 → 代码段前缀（3 位）。按 2026-10-18 全库扫描实证写全。
MARKET_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "sh": ("600", "601", "603", "605", "688", "689", "900"),
    "sz": ("000", "001", "002", "003", "200", "300", "301", "302"),
    "bj": ("430", "830", "870", "920"),
}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SecurityMapError(ValueError):
    """映射层错误的公共基类。"""


class AmbiguousCodeError(SecurityMapError):
    """裸码落在歧义区（000000–000999），不得静默取一个市场。"""


class UnknownCodeError(SecurityMapError):
    """给定市场下没有该代码的条目。"""


class MarketMismatchError(SecurityMapError):
    """代码段不属于调用方指定的市场（典型的「市场传错」）。"""


class UnknownMarketError(SecurityMapError):
    """代码段不在任何已知市场的命名空间内 —— 不猜。"""


@dataclass(frozen=True)
class SecurityEntry:
    """一条证券映射。``delisted``/``successor`` 为空串表示「未知」而非「没有」。"""

    code: str
    market: str
    listed: str = ""
    delisted: str = ""
    successor: str = ""
    name: str = ""


def _norm_code(code: Any) -> str:
    s = str(code or "").strip()
    if not s:
        raise UnknownCodeError("空代码")
    return s.zfill(6)


def market_of_code(code: Any) -> str:
    """按代码段推断市场；未知段抛 :class:`UnknownMarketError`（不猜）。"""
    c = _norm_code(code)
    for market, prefixes in MARKET_PREFIXES.items():
        if c[:3] in prefixes:
            return market
    raise UnknownMarketError(
        f"代码 {c} 的前三位 {c[:3]} 不在任何已知市场命名空间"
        f"（{ {m: list(p) for m, p in MARKET_PREFIXES.items()} }）")


def is_ambiguous_bare(code: Any) -> bool:
    """裸码是否落在 000000–000999 歧义区（SH 指数 ∩ SZ 股票）。"""
    c = _norm_code(code)
    return AMBIGUOUS_BARE_RANGE[0] <= c <= AMBIGUOUS_BARE_RANGE[1]


def secid_eastmoney(code: Any, market: str) -> str:
    """东财 secid（``1.600000`` / ``0.000001`` / BJ 段 ``0.<code>``）。

    先做命名空间校验（防止把 SZ 代码传成 sh），格式串委托
    `fetch.common.normalize_code` —— 既有权威，不在此重新推导。
    """
    c = _norm_code(code)
    m = str(market or "").lower()
    if m not in MARKET_PREFIXES:
        raise UnknownMarketError(f"未知市场：{market!r}")
    if c[:3] not in MARKET_PREFIXES[m]:
        raise MarketMismatchError(f"代码 {c} 不属于 {m} 命名空间")
    from fetch.common import normalize_code  # 延迟导入：保持 pit 包不依赖 fetch
    _, secid, _ = normalize_code(f"{m}{c}")
    return secid


def secid_baostock(code: Any, market: str) -> str:
    """baostock secid（``sh.600000`` / ``sz.000001`` / ``bj.430047``）。"""
    c = _norm_code(code)
    m = str(market or "").lower()
    if m not in MARKET_PREFIXES:
        raise UnknownMarketError(f"未知市场：{market!r}")
    if c[:3] not in MARKET_PREFIXES[m]:
        raise MarketMismatchError(f"代码 {c} 不属于 {m} 命名空间")
    return f"{m}.{c}"


class SecurityMap:
    """``(market, code) → SecurityEntry`` 的映射表。

    构建自 `stocks/*.metadata.json`（字段 ``code``/``name``/
    ``list_date``/``delist_date``/``is_delisted``）。构建期的异常
    （未知代码段、缺日期、delisted 与 delist_date 矛盾）**不静默丢弃**，
    进 ``anomalies`` 并在落盘 meta 中计数。
    """

    SCHEMA = "security_map/v1"

    def __init__(self, entries: Iterable[SecurityEntry],
                 built_from: str = "", anomalies: Optional[Dict[str, Any]] = None):
        self._by_key: Dict[Tuple[str, str], SecurityEntry] = {}
        for e in entries:
            self._by_key[(e.market, e.code)] = e
        self._built_from = built_from
        self.anomalies: Dict[str, Any] = anomalies or {}

    # -- 构建 -------------------------------------------------------------

    @classmethod
    def build_from_metadata(cls, stocks_dir: str | Path) -> SecurityMap:
        """读 `*.metadata.json` 建表。异常代码段记 ``market=None`` 并计数。"""
        d = Path(stocks_dir)
        entries: List[SecurityEntry] = []
        anomalies: Dict[str, Any] = {"unknown_market": [], "missing_list_date": [],
                                     "delisted_without_date": [], "undated": 0}
        for p in sorted(d.glob("*.metadata.json")):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                anomalies["undated"] += 1
                continue
            code = _norm_code(m.get("code"))
            name = str(m.get("name") or "")
            listed = str(m.get("list_date") or "")
            delisted = str(m.get("delist_date") or "")
            is_delisted = bool(m.get("is_delisted"))
            try:
                market = market_of_code(code)
            except UnknownMarketError:
                anomalies["unknown_market"].append(code)
                market = ""
            if not _ISO_DATE.match(listed):
                anomalies["missing_list_date"].append(code)
                listed = ""
            if is_delisted and not _ISO_DATE.match(delisted):
                anomalies["delisted_without_date"].append(code)
            entries.append(SecurityEntry(code=code, market=market, listed=listed,
                                         delisted=delisted if _ISO_DATE.match(delisted) else "",
                                         successor="", name=name))
        for k in ("unknown_market", "missing_list_date", "delisted_without_date"):
            anomalies[k] = sorted(anomalies[k])
        return cls(entries, built_from=str(d), anomalies=anomalies)

    # -- 查询 -------------------------------------------------------------

    def resolve(self, code: Any, market: Optional[str] = None) -> SecurityEntry:
        """解析代码 → 条目。

        * 不给 ``market``：歧义区（000000–000999）抛 :class:`AmbiguousCodeError`
          （错误信息列出两个候选命名空间）；其余按代码段推断市场。
        * 给 ``market``：三重校验（市场已知 / 代码段属于该市场 / 条目存在）。
        """
        c = _norm_code(code)
        if market is None:
            if is_ambiguous_bare(c):
                raise AmbiguousCodeError(
                    f"裸码 {c} 落在歧义区 {AMBIGUOUS_BARE_RANGE[0]}–"
                    f"{AMBIGUOUS_BARE_RANGE[1]}：它同时属于 sh 指数命名空间"
                    f"（如 000905.SH = 中证500）与 sz 股票命名空间"
                    f"（000905.SZ = 厦门港务）。请显式传 market=…，"
                    f"本映射不静默取一个。")
            market = market_of_code(c)
        m = str(market).lower()
        if m not in MARKET_PREFIXES:
            raise UnknownMarketError(f"未知市场：{market!r}")
        if c[:3] not in MARKET_PREFIXES[m]:
            raise MarketMismatchError(
                f"代码 {c} 不属于 {m} 命名空间（{m} 段为 "
                f"{'/'.join(MARKET_PREFIXES[m])}）")
        entry = self._by_key.get((m, c))
        if entry is None:
            raise UnknownCodeError(f"{m} 市场没有代码 {c} 的条目")
        return entry

    def get(self, code: Any, market: Optional[str] = None) -> Optional[SecurityEntry]:
        """不抛异常的查询；歧义/未知一律返回 ``None``（不静默取一个）。"""
        try:
            return self.resolve(code, market)
        except SecurityMapError:
            return None

    def entries(self) -> List[SecurityEntry]:
        return [self._by_key[k] for k in sorted(self._by_key)]

    def market_counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self._by_key.values():
            out[e.market or "unknown"] = out.get(e.market or "unknown", 0) + 1
        return dict(sorted(out.items()))

    @property
    def successor_known_count(self) -> int:
        return sum(1 for e in self._by_key.values() if e.successor)

    def __len__(self) -> int:
        return len(self._by_key)

    # -- 落盘 -------------------------------------------------------------

    def to_dict(self, built_at: str = "") -> Dict[str, Any]:
        return {
            "schema": self.SCHEMA,
            "built_from": self._built_from,
            "built_at": built_at,
            "count": len(self._by_key),
            "ambiguous_bare_range": list(AMBIGUOUS_BARE_RANGE),
            "market_counts": self.market_counts(),
            "successor_known_count": self.successor_known_count,
            "anomaly_counts": {k: (len(v) if isinstance(v, list) else v)
                               for k, v in self.anomalies.items()},
            "entries": [asdict(e) for e in self.entries()],
        }

    # -- 自检 -------------------------------------------------------------

    def audit_delist_consistency(self, stocks_dir: str | Path, *,
                                 sample: Optional[int] = None) -> Dict[str, Any]:
        """对账 metadata 的 ``delist_date``/``is_delisted`` 与 CSV 末条日期。

        逐条判定：

        * ``match`` —— 已退市且末条 ≤ delist_date；
        * ``active_ok`` —— 未退市且末条 = 全库最后交易日；
        * ``stale_but_active`` —— 未退市但末条早于全库最后交易日
          （数据缺口或**未申报的退市**，必须计数）；
        * ``mismatch`` —— 已退市但末条晚于 delist_date。

        ``sample`` 给定时只查前 N 条（测试用）；全量查时 ``dataset_end``
        取全库末条最大值。**矛盾只登记，不静默改 metadata。**
        """
        d = Path(stocks_dir)
        keys = sorted(self._by_key)
        if sample is not None:
            keys = keys[:sample]
        last_bars: Dict[Tuple[str, str], str] = {}
        for market, code in keys:
            csv_path = d / f"{code}.csv"
            if not csv_path.is_file():
                continue
            last_bars[(market, code)] = _last_bar_date(csv_path)
        dataset_end = max(last_bars.values()) if last_bars else ""
        out: Dict[str, Any] = {"dataset_end": dataset_end, "checked": len(last_bars),
                               "verdicts": {}, "counts": {}}
        for key, last in last_bars.items():
            e = self._by_key[key]
            if e.delisted:
                verdict = "match" if last <= e.delisted else "mismatch"
            else:
                verdict = "active_ok" if last == dataset_end else "stale_but_active"
            out["verdicts"][f"{e.market}:{e.code}"] = {"verdict": verdict,
                                                       "last_bar": last,
                                                       "meta_delisted": e.delisted}
        for v in out["verdicts"].values():
            out["counts"][v["verdict"]] = out["counts"].get(v["verdict"], 0) + 1
        return out


def _last_bar_date(csv_path: Path) -> str:
    """取 CSV 最后一行的日期（首列），不读整个文件。"""
    size = csv_path.stat().st_size
    with csv_path.open("rb") as fh:
        fh.seek(max(0, size - 8192))
        tail = fh.read()
    for line in reversed(tail.split(b"\n")):
        line = line.strip(b"\r")
        if not line:
            continue
        head = line.split(b",", 1)[0].decode("ascii", errors="ignore").strip()
        if _ISO_DATE.match(head):
            return head
    return ""
