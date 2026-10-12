# -*- coding: utf-8 -*-
"""PIT 快照库：只追加、带采集时刻的每日快照（自建「当日可知」的历史）。

## 为什么需要这一层

抓取型数据源（腾讯/东财/baostock 快照端点）**只给当前值**：今天抓有今天，
**昨天抓不到昨天**。若把「今天抓的值」当「历史值」用，就是前视偏差，
而且这种偏差**不会报错**，只会让回测结果悄悄变好。

唯一不引入前视的办法：**自己每天落盘一次，自建历史**。
本模块提供该过程的**机械**支撑（落盘/校验/查询/断更检测），
**不做任何领域判断** —— 领域语义由各数据集适配器负责。

设计依据：``PIT_SNAPSHOT_DESIGN.md``。

## 双时间轴（本模块的核心纪律）

每条记录同时带三个时间字段：

=================  ==================================================
字段                含义
=================  ==================================================
``effective_date`` 数据在现实世界**生效**的日期（行业调整生效日 / 上市日）
``as_of``          **采集时刻**（何时抓到），含时区
``ingest_run_id``  采集批次 ID（``YYYYMMDD-HHMM``）
=================  ==================================================

查询规则**取决于数据集的 PIT 模式**（见 :data:`DATASET_REGISTRY`）：

* ``revisable``（默认，**未知数据集一律按此处理**）
  → ``as_of <= D AND effective_date <= D``。
  适用于**会被修订**的数据（行业分类、估值快照、财务预告…）——
  只用 ``effective_date`` 会把「当时尚未公布」的修订值放进来。
* ``immutable_fact``
  → 仅 ``effective_date <= D``；``as_of`` 轴**只用于溯源与复现**，不用于筛选。
  **仅限登记表显式声明且给出理由的数据集**（如上市日/退市日这类**历史结局事实**）：
  其保守用法 ``valid_from <= D < valid_to`` **永远不会把尚未发生的事提前纳入**，
  故双轴在此不是安全增益，反而会让整段历史不可查询。

> ⚠️ **默认是 ``revisable``** —— 未登记的数据集走最严格口径，这是 fail-safe 方向。

## 只追加

已落盘的 ``(dataset, ingest_date)`` **不得覆盖**；需显式 ``force=True``，
且强制写一条 ``overwrite`` 留痕日志。
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# 北京时间（采集时刻一律以此记录，避免跨时区歧义）
CST = timezone(timedelta(hours=8))

# --- PIT 模式 ---
MODE_REVISABLE = "revisable"
MODE_IMMUTABLE_FACT = "immutable_fact"

#: 数据集登记表。**新增数据集必须在此登记**，否则 :class:`PitSnapshotStore`
#: 一律拒绝（防「静默使用未登记数据」—— 与本项目反复出现的静默失效同类）。
DATASET_REGISTRY: Dict[str, Dict[str, Any]] = {
    "l1_stock_basic": {
        "pit_mode": MODE_IMMUTABLE_FACT,
        "primary_key": "code",
        "unique_key": ("code",),
        "justification": (
            "上市日/退市日是**历史结局事实**，其保守用法 "
            "(valid_from <= D < valid_to) 永远不会把「尚未发生的事」提前纳入。"
            "as_of 轴在此仅用于溯源与复现，不用于筛选 —— 若强制双轴，"
            "则 2026-10-11 之前的历史将完全不可查询，数据失去意义。"
        ),
    },
    "l2_sw_industry": {
        "pit_mode": MODE_IMMUTABLE_FACT,
        "primary_key": "code",
        "unique_key": ("code", "effective_date"),
        "justification": (
            "行业归属变迁史以「计入日期」为生效日；申万分类体系的历次修订"
            "（2014 / 2021）**本身也有生效日**（体现为同一股票的多行记录），"
            "故「某日该股属哪个行业」是**已发生事实**，不是可随意改写的估计值。"
            "⚠️ 残留风险：若申万**事后回溯修改**历史「计入日期」，我们无法察觉 —— "
            "`as_of` 轴记录采集时刻供溯源，但不用于筛选。"
        ),
    },
    "l3_valuation": {
        # ⚠️ **保守用 `revisable`（双轴）**，理由：
        #   ① **每日追加**时 `as_of ≈ effective_date`，双轴完全可用，无副作用；
        #   ② **历史回填**时 `as_of = 采集日`（如 2026-10-12）≠ `effective_date`（如 2016-01-04）
        #      → 双轴下回填记录**对历史日期不可见**。这正是诚实的语义：
        #      **「这些数据我们在采集日之前并没有」**。
        #   ③ 若要让回填用于历史回测，须**先通过对账**（见 `PIT_SNAPSHOT_P2_REPORT.md`）
        #      并**显式授权**改为 `immutable_fact` —— 不在采集阶段预先声明。
        #      依据：设计文档「不因为「源给了回溯窗口」就默认其 PIT 正确 —— 回溯值同样要对账」。
        "pit_mode": MODE_REVISABLE,
        "primary_key": "code",
        "unique_key": ("code", "effective_date"),
        "note": (
            "日频估值历史（baostock query_history_k_data_plus，adjustflag='3' 不复权）："
            "close / pe_ttm / pb_mrq / ps_ttm / pcf_ncf_ttm / turnover / trade_status / is_st。"
            "回填用于历史回测前必须先做抽样对账并显式授权。"
        ),
    },
}

# 规范化表的**保留列名**。
# ⚠️ `effective_date` 是所有数据集统一的生效日列，不再引入 `effective_field`
# 间接层 —— 首版曾让 `l1_stock_basic` 指到 `ipo_date`，导致同名的 `effective_date`
# 列被静默绕过（测试当场抓到）。**少一层间接 = 少一处静默失效。**
_EFFECTIVE_COL = "effective_date"


class SnapshotError(RuntimeError):
    """快照库的基类异常。"""


class UnknownDatasetError(SnapshotError):
    """数据集未在 :data:`DATASET_REGISTRY` 登记。"""


class OverwriteRefusedError(SnapshotError):
    """目标日期已落盘且未显式 ``force``。"""


def now_cst() -> datetime:
    """当前北京时间。"""
    return datetime.now(CST)


def make_run_id(ts: Optional[datetime] = None) -> str:
    """采集批次 ID，形如 ``20261011-2130``。"""
    return (ts or now_cst()).strftime("%Y%m%d-%H%M")


def sha256_of_file(path: Path) -> str:
    """文件 SHA256（分块读，避免大文件吃内存）。"""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_meta(dataset: str) -> Dict[str, Any]:
    """取数据集登记信息；未登记即抛错（不返回默认值）。"""
    if dataset not in DATASET_REGISTRY:
        raise UnknownDatasetError(
            f"数据集 {dataset!r} 未在 DATASET_REGISTRY 登记。"
            f"已登记: {sorted(DATASET_REGISTRY)}"
        )
    return DATASET_REGISTRY[dataset]


def in_universe(rec: Dict[str, str], date: str) -> bool:
    """L1 语义：``date`` 当日该股**是否在可交易universe内**。

    规则 ``ipo_date <= date < out_date``（``out_date`` 空 = 仍在市）。

    **为何这样用不算前视**：``out_date`` 虽属事后已知，但本规则**只在退市日当天及之后**
    才把该股移出，**从不提前移出** → 在 ``date`` 当日实际可交易性与规则一致，无泄漏。
    这正是 ``l1_stock_basic`` 被登记为 ``immutable_fact`` 的理由。
    """
    ipo = str(rec.get("ipo_date") or "")
    out = str(rec.get("out_date") or "")
    if ipo and ipo > date:
        return False
    # 退市日当天已不可交易（`date >= out_date` 即出局）
    return not (out and date >= out)


class PitSnapshotStore:
    """只追加、双时间轴的快照库。

    :param root: 库根目录（默认 ``D:/pit_snapshots``，由调用方显式传入更佳）。
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.norm_dir = self.root / "normalized"
        self.meta_dir = self.root / "meta"
        self.log_path = self.meta_dir / "ingest_log.jsonl"
        self.gaps_path = self.meta_dir / "gaps.json"

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------
    def raw_path(self, source: str, endpoint: str, ingest_date: str,
                 suffix: str = ".jsonl") -> Path:
        return self.raw_dir / source / endpoint / f"{ingest_date}{suffix}"

    def norm_path(self, dataset: str, ingest_date: str) -> Path:
        return self.norm_dir / dataset / f"{ingest_date}.csv"

    # ------------------------------------------------------------------
    # 写（只追加）
    # ------------------------------------------------------------------
    def append_raw(
        self,
        source: str,
        endpoint: str,
        ingest_date: str,
        records: Sequence[Dict[str, Any]],
        *,
        force: bool = False,
    ) -> Path:
        """写原始层（JSONL，只追加）。已存在且未 ``force`` → 抛 :class:`OverwriteRefusedError`。"""
        path = self.raw_path(source, endpoint, ingest_date)
        if path.exists() and not force:
            raise OverwriteRefusedError(f"原始层已存在（拒绝覆盖）: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return path

    def append_raw_bytes(
        self,
        source: str,
        endpoint: str,
        ingest_date: str,
        data: bytes,
        *,
        suffix: str = ".bin",
        force: bool = False,
    ) -> Path:
        """写**二进制**原始响应（如 xls）。同样只追加。

        二进制源（申万 xls 等）**不能**转成 JSONL —— 那样会丢掉原始字节，
        日后无法用官方文件复核。故原样落盘。
        """
        path = self.raw_path(source, endpoint, ingest_date, suffix)
        if path.exists() and not force:
            raise OverwriteRefusedError(f"原始层已存在（拒绝覆盖）: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_normalized(
        self,
        dataset: str,
        ingest_date: str,
        rows: Sequence[Dict[str, Any]],
        *,
        columns: Optional[Sequence[str]] = None,
        force: bool = False,
    ) -> Path:
        """写规范层（CSV，只追加）。``columns`` 缺省时按首行键序 + 其余键补齐。"""
        dataset_meta(dataset)  # 未登记即抛错
        path = self.norm_path(dataset, ingest_date)
        if path.exists() and not force:
            raise OverwriteRefusedError(f"规范层已存在（拒绝覆盖）: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

        if columns is None:
            cols: List[str] = []
            for r in rows:
                for k in r:
                    if k not in cols:
                        cols.append(k)
        else:
            cols = list(columns)

        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        # 统一 LF（Windows 上 csv 默认 \r\n，与本项目行尾纪律冲突）
        data = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(data)
        return path

    def log_ingest(self, entry: Dict[str, Any]) -> None:
        """追加一条采集日志（``meta/ingest_log.jsonl``）。"""
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------
    def read_normalized(self, dataset: str) -> List[Dict[str, str]]:
        """读全部已落盘的规范层记录（跨所有日期）。"""
        d = self.norm_dir / dataset
        if not d.is_dir():
            return []
        out: List[Dict[str, str]] = []
        for p in sorted(d.glob("*.csv")):
            with p.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    out.append({k: (v if v is not None else "") for k, v in row.items()})
        return out

    def ingest_log(self) -> List[Dict[str, Any]]:
        """读全部采集日志。"""
        if not self.log_path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with self.log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def landed_dates(self, dataset: str) -> List[str]:
        """已落盘的日期序列（升序）。"""
        d = self.norm_dir / dataset
        if not d.is_dir():
            return []
        return sorted(p.stem for p in d.glob("*.csv"))

    # ------------------------------------------------------------------
    # 双时间轴查询
    # ------------------------------------------------------------------
    def records_as_of(self, dataset: str, date: str) -> List[Dict[str, str]]:
        """返回在 ``date`` 当日**可知**的全部记录。

        规则见模块 docstring：``revisable`` 走双轴，``immutable_fact`` 走单轴
        （单轴是**登记表显式授权**的结果，不是默认行为）。
        """
        meta = dataset_meta(dataset)
        strict = meta["pit_mode"] == MODE_REVISABLE
        out: List[Dict[str, str]] = []
        for r in self.read_normalized(dataset):
            ed = str(r.get(_EFFECTIVE_COL) or "")
            if ed and ed > date:
                continue
            if strict and str(r.get("as_of") or "")[:10] > date:
                continue
            out.append(r)
        return out

    def record_as_of(self, dataset: str, key: str, date: str) -> Optional[Dict[str, str]]:
        """返回 ``key``（主键）在 ``date`` 当日可知的**最新一条**记录。

        排序键：``effective_date`` 优先，其次 ``as_of``。取不到返回 ``None``
        （**不猜、不填默认值**）。
        """
        meta = dataset_meta(dataset)
        pk = str(meta["primary_key"])
        cands = [r for r in self.records_as_of(dataset, date) if r.get(pk) == key]
        if not cands:
            return None
        cands.sort(key=lambda r: (str(r.get(_EFFECTIVE_COL) or ""), str(r.get("as_of") or "")))
        return cands[-1]

    # ------------------------------------------------------------------
    # 断更检测
    # ------------------------------------------------------------------
    def detect_gaps(self, dataset: str, expected_days: Sequence[str]) -> List[str]:
        """期望日期 − 已落盘日期 = 缺口清单（升序）。"""
        landed = set(self.landed_dates(dataset))
        return sorted(d for d in expected_days if d not in landed)

    def write_gaps(self, dataset: str, gaps: Sequence[str]) -> Path:
        """把断更清单写入 ``meta/gaps.json``（覆盖式，仅状态文件）。"""
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        existing: Dict[str, Any] = {}
        if self.gaps_path.exists():
            existing = json.loads(self.gaps_path.read_text(encoding="utf-8"))
        existing[dataset] = {
            "checked_at": now_cst().isoformat(),
            "n_gaps": len(gaps),
            "gaps": list(gaps),
        }
        with self.gaps_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(existing, ensure_ascii=False, indent=2))
        return self.gaps_path

    # ------------------------------------------------------------------
    # 自检（阈值由调用方事前固定并传入）
    # ------------------------------------------------------------------
    @staticmethod
    def check_primary_key_unique(rows: Sequence[Dict[str, Any]], key: str) -> List[str]:
        """主键唯一性检查；返回重复键列表（空 = 通过）。"""
        seen: Dict[str, int] = {}
        for r in rows:
            k = str(r.get(key) or "")
            seen[k] = seen.get(k, 0) + 1
        return sorted(k for k, n in seen.items() if n > 1)

    @staticmethod
    def check_unique_key(
        rows: Sequence[Dict[str, Any]], keys: Sequence[str]
    ) -> List[str]:
        """**复合**唯一性检查（如 L2 的 ``(code, effective_date)``）。

        返回重复组合的**可读串**列表（空 = 通过）。
        ⚠️ 不能对 L2 用单列 ``code`` —— 一股多行（历次行业调整）是**正常结构**，
        单列检查会把正确数据判为错误。
        """
        seen: Dict[tuple, int] = {}
        for r in rows:
            k = tuple(str(r.get(c) or "") for c in keys)
            seen[k] = seen.get(k, 0) + 1
        return sorted("|".join(k) for k, n in seen.items() if n > 1)

    @staticmethod
    def check_missing_rate(rows: Sequence[Dict[str, Any]], field: str) -> float:
        """字段缺失率（空串/None 记为缺失）；返回实际比例，由调用方与阈值比较。"""
        if not rows:
            return 0.0
        miss = sum(1 for r in rows if r.get(field) in (None, ""))
        return miss / len(rows)
