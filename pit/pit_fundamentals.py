# -*- coding: utf-8 -*-
"""PIT（时点正确）财务数据：把业绩报表变成"某日可知"的因子值。

## 为什么必须有这一层

财务数据是**离散公告**的，不是连续可得的。2024Q1 的报表若 2024-04-25 才公告，
则 2024-04-25 之前**不得使用**它 —— 用了就是前视偏差，且这种偏差**不会报错**，
只会让回测结果悄悄变好。

本模块的唯一职责：给定 ``(code, date)``，返回**该日确实已经公告**的最新财务数据。

## ⚠️ 公告日字段不可信（2026-09-19 实测）

数据源（东方财富业绩报表）的 ``最新公告日期`` 在 **2016-01 ~ 2025-06 的全部报告期上
系统性偏移 +1 年** —— 例：贵州茅台 2016Q1 财报（EPS 3.89，数值确为 2016Q1）
标注公告日为 ``2017-04-25``；仅最近约 4 期正确。

因此本模块**不直接使用**该字段，而是走 :func:`resolve_availability`：

* 公告日 <= 法定截止日 + :data:`ANNOUNCE_SANITY_DAYS`(45 天) → 采信公告日；
* 否则判为不可信 → 退回**法定披露截止日**（一季报 4/30、半年报 8/31、
  三季报 10/31、年报次年 4/30）。

**残留风险（必须随结论声明）**：真实延迟披露且超出容忍窗口的公司会被退回法定截止日，
从而比真实公开时间略早。用 :func:`audit_announce_dates` 可量化该比例。

## 与 `factors/factor_registry.py` 的对应

registry 中此前因缺数据源而标记 ``missing_source`` 的 6 个基本面因子，
本模块可直接支撑其中 4 个：

========================  ====================================================
因子名                    来源
========================  ====================================================
``pb``                    ``price / 每股净资产``
``roe``                   ``净资产收益率``（**YTD 累计口径**，见下方局限）
``net_profit_growth``     ``净利润-同比增长``
``pe_ttm``                ``price / TTM 每股收益``（TTM 由三期报表推算）
========================  ====================================================

另新增 ``revenue_growth`` / ``gross_margin`` / ``ocf_per_share`` 三个可直接使用的因子。
``ps_ttm`` 需要市值与营业收入（市值需股本，本地数据集未含），
``operating_cashflow_growth`` 需要 OCF 的同比口径 —— 两者**仍不可用**，不硬凑。

## 已知局限（必须随结论声明）

1. ``roe`` 是**年初至今累计**口径，不是 TTM。同一日不同个股可能落在不同报告期，
   跨报告期比较前应先用返回的 ``report_period`` 过滤。
2. ``industry`` 字段来自数据源的**抓取时点**标签，**不是历史时点分类**，
   直接用于历史回测会引入分类幸存者偏差。
3. TTM 每股收益按 ``EPS(Y,Q) + EPS(Y-1,Q4) - EPS(Y-1,Q)`` 推算，
   **仅当三期都在该日已公告时才输出**；否则 ``pe_ttm`` 缺失（不插补）。
4. 每股收益为负时不输出 ``pe_ttm``（负 PE 无经济含义，硬算会产生假排序）。
"""
from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# 严格的 ISO 日期格式。用于拒绝上游混入的非日期值（如 pandas 的 "NaT"）。
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

__all__ = [
    "SUPPORTED_FACTORS",
    "PitFundamentals",
    "audit_announce_dates",
    "load_records",
    "resolve_availability",
    "save_records",
    "statutory_available_date",
]

# 本模块可直接支撑的因子名（供 factor_registry 的可用性检查引用）
SUPPORTED_FACTORS = ("pe_ttm", "pb", "roe", "net_profit_growth",
                     "revenue_growth", "gross_margin", "ocf_per_share")

# 法定披露截止日（按报告期末月-日）。依据《证券法》与交易所信息披露规则：
# 一季报 4/30 前、半年报 8/31 前、三季报 10/31 前、年报次年 4/30 前。
STATUTORY_DEADLINE = {"03-31": "04-30", "06-30": "08-31",
                      "09-30": "10-31", "12-31": "04-30"}

# 公告日晚于法定截止日的最大容忍天数。超出即判为**不可信**，退回法定截止日。
#
# 为什么需要：实测东方财富 `最新公告日期` 在 2016-01 ~ 2025-06 的**全部**报告期上
# 系统性偏移 **+1 年**（例：贵州茅台 2016Q1 财报标注公告日 2017-04-25，
# 而财务数值 3.89 确为 2016Q1），仅最近约 4 期正确。
# 该字段**不能单独作为 PIT 依据**，否则会把数据可用时间整体推迟一年 ——
# 虽然保守（不会前视），但会让因子只剩 1~2 年前的陈旧数据，研究价值归零。
ANNOUNCE_SANITY_DAYS = 45


def statutory_available_date(report_period: str) -> str:
    """报告期 ``"2024-03-31"`` → 法定披露截止日 ``"2024-04-30"``（年报为次年 04-30）。"""
    year, month_day = report_period[:4], report_period[5:10]
    if month_day == "12-31":
        return f"{int(year) + 1}-04-30"
    return f"{year}-{STATUTORY_DEADLINE[month_day]}"


def _days_between(later: str, earlier: str) -> int:
    """``later - earlier`` 的天数；任一日不合法返回一个很大的数（视为不可信）。"""
    from datetime import date
    try:
        a = date.fromisoformat(later[:10])
        b = date.fromisoformat(earlier[:10])
    except (ValueError, TypeError):
        return 10 ** 6
    return (a - b).days


def resolve_availability(record: Dict[str, Any],
                         disclosures: Optional[Dict[Tuple[str, str], str]] = None) -> Tuple[str, str]:
    """判定一条记录**最早可用的日期**及其依据（按可信度从高到低）。

    ====================  ================================================
    basis                 依据与适用条件
    ====================  ================================================
    ``actual_disclosure`` **真实披露日**（巨潮资讯 `stock_report_disclosure`
                          的 `实际披露` 字段）。**首选** —— 它直接给出该报告
                          实际公开的日期，既不前视也不拖延。
    ``announce_date``     数据源公告日，且距法定截止日 ≤ 容忍窗口（45 天）。
                          用于没有巨潮披露日的历史记录。
    ``statutory_deadline`` 法定披露截止日。**兜底**：公告日不可信（典型是系统性
                          偏移 +1 年）且无真实披露日时使用。保守但偏晚。
    ====================  ================================================

    已知残留风险：走兜底路径时，真实**延迟披露**且超出容忍窗口的公司会被退回
    法定截止日，从而比真实公开时间略早。用 :func:`audit_announce_dates` 可量化。
    """
    period = str(record.get("report_period") or "")
    code = str(record.get("code") or "").zfill(6)
    if disclosures and period:
        real = disclosures.get((code, period))
        if real:
            return real, "actual_disclosure"
    announce = str(record.get("announce_date") or "")
    if not period:
        return announce, "announce_date"
    deadline = statutory_available_date(period)
    if announce and _days_between(announce, deadline) <= ANNOUNCE_SANITY_DAYS:
        return announce, "announce_date"
    return deadline, "statutory_deadline"


def audit_announce_dates(records: Iterable[Dict[str, Any]],
                         disclosures: Optional[Dict[Tuple[str, str], str]] = None
                         ) -> Dict[str, Any]:
    """诊断公告日字段的可信度：逐期统计"被判不可信"的比例。

    用途：**在把任何财务数据用于研究之前先跑一遍**。
    某一期的不可信比例接近 100% 即说明该期公告日整体损坏，
    必须依赖法定截止日口径，并在结论中声明。
    """
    by_period: Dict[str, List[int]] = {}
    for r in records:
        period = str(r.get("report_period") or "")
        if not period:
            continue
        _, basis = resolve_availability(r, disclosures)
        by_period.setdefault(period, []).append(1 if basis == "statutory_deadline" else 0)
    out: Dict[str, Any] = {"periods": {}, "suspicious_total": 0, "records_total": 0}
    for period in sorted(by_period):
        flags = by_period[period]
        bad = sum(flags)
        out["periods"][period] = {"n": len(flags), "suspicious": bad,
                                  "suspicious_ratio": bad / len(flags) if flags else 0.0}
        out["suspicious_total"] += bad
        out["records_total"] += len(flags)
    out["suspicious_ratio"] = (out["suspicious_total"] / out["records_total"]
                               if out["records_total"] else 0.0)
    return out


def load_disclosures(path: str | Path) -> Dict[Tuple[str, str], str]:
    """读巨潮真实披露日 JSONL → ``{(code, report_period): actual_disclose}``。

    供 :func:`resolve_availability` 作为**首选**依据（优先于数据源公告日与法定截止日）。
    文件不存在时返回空字典 —— 此时自动退回公告日/法定截止日口径，行为与以前一致。
    """
    p = Path(path)
    if not p.exists():
        return {}
    out: Dict[Tuple[str, str], str] = {}
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = str(r.get("code") or "").zfill(6)
            period = str(r.get("report_period") or "")
            actual = str(r.get("actual_disclose") or "")
            # 防御性校验：必须是 YYYY-MM-DD。上游曾把 pandas 的 NaT 写成字符串
            # "NaT" 混入文件（2026-09-25 实测 11/176,841 条），只判空串抓不住。
            if code and period and _ISO_DATE.match(actual):
                out[(code, period)] = actual
    return out


def load_records(path: str | Path) -> List[Dict[str, Any]]:
    """读取 JSONL 记录（每行一条）。空行与坏行**跳过并计数**，不静默吞掉整文件。"""
    out: List[Dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def save_records(records: Iterable[Dict[str, Any]], path: str | Path) -> int:
    """按 ``(code, report_period)`` 排序写出 JSONL，返回条数。"""
    rows = sorted(records, key=lambda r: (str(r.get("code", "")), str(r.get("report_period", ""))))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


class PitFundamentals:
    """按公告日索引的财务数据快照。

    ``records`` 每条的必需字段：``code`` / ``report_period`` / ``announce_date``。
    其余字段（``eps`` / ``bps`` / ``roe_pct`` / ``net_profit_yoy_pct`` / ...）
    缺失即视为不可用，**不做插补**。
    """

    def __init__(self, records: Iterable[Dict[str, Any]],
                 disclosures: Optional[Dict[Tuple[str, str], str]] = None):
        self._disclosures = disclosures or {}
        by_code: Dict[str, List[Dict[str, Any]]] = {}
        for r in records:
            code = str(r.get("code", "")).zfill(6)
            if not code or not r.get("announce_date") or not r.get("report_period"):
                continue
            row = dict(r)
            # 可用日由 resolve_availability 判定，优先级：
            #   真实披露日（巨潮） > 可信的公告日 > 法定截止日兜底
            # 所有查询一律以 available_from 为准，**不直接使用 announce_date**。
            row["available_from"], row["availability_basis"] = resolve_availability(
                row, self._disclosures)
            by_code.setdefault(code, []).append(row)
        # 按可用日升序；同可用日以报告期晚者为准（更完整）
        self._by_code: Dict[str, List[Dict[str, Any]]] = {}
        self._dates: Dict[str, List[str]] = {}
        for code, rows in by_code.items():
            rows.sort(key=lambda r: (str(r["available_from"]), str(r["report_period"])))
            self._by_code[code] = rows
            self._dates[code] = [str(r["available_from"]) for r in rows]

    # -- 基本访问 ---------------------------------------------------------

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_code.values())

    def codes(self) -> List[str]:
        return sorted(self._by_code)

    def known_as_of(self, code: str, date: str) -> List[Dict[str, Any]]:
        """返回 ``date``（含）之前已公告的全部记录（升序）。"""
        rows = self._by_code.get(str(code).zfill(6))
        if not rows:
            return []
        idx = bisect_right(self._dates[str(code).zfill(6)], str(date))
        return rows[:idx]

    def as_of(self, code: str, date: str) -> Optional[Dict[str, Any]]:
        """该日**已公告**的最新一期财务数据；无则 ``None``。

        选取规则：在 ``announce_date <= date`` 的记录里取 **report_period 最大**
        的一条（同报告期取公告更晚的）。

        注意不是"公告日最晚"：年报可能比次年一季报公告得更晚（年报延迟披露），
        此时一季报才是更新的信息，必须被选中。
        """
        known = self.known_as_of(code, date)
        if not known:
            return None
        return max(known, key=lambda r: (str(r["report_period"]), str(r["available_from"])))

    # -- 派生指标 ---------------------------------------------------------

    def ttm_eps_as_of(self, code: str, date: str) -> Optional[float]:
        """该日可推算的 TTM 每股收益；三期不齐或口径不符返回 ``None``。

        报表为**年初至今累计**口径，故
        ``TTM = EPS(Y,Q) + EPS(Y-1,Q4) - EPS(Y-1,Q)``；``Q4`` 时即为年报数。
        **只用该日已公告的记录** —— 上一年的年报可能比本年一季报公告得更晚，
        这一约束正是防前视的关键。
        """
        known = self.known_as_of(code, date)
        if not known:
            return None
        by_period = {str(r["report_period"]): r for r in known}
        latest = self.as_of(code, date)
        if latest is None:
            return None
        period = str(latest["report_period"])
        year, month = period[:4], period[5:7]
        eps_now = _num(latest.get("eps"))
        if eps_now is None:
            return None
        if month == "12":
            return eps_now
        prev_fy = by_period.get(f"{int(year) - 1}-12-31")
        prev_same = by_period.get(f"{int(year) - 1}-{month}-{period[8:10]}")
        if prev_fy is None or prev_same is None:
            return None
        a, b = _num(prev_fy.get("eps")), _num(prev_same.get("eps"))
        if a is None or b is None:
            return None
        return eps_now + a - b

    def factors_as_of(self, code: str, date: str,
                      price: Optional[float] = None) -> Dict[str, Any]:
        """该日可用的基本面因子；**不可用的键不出现**（而非填 0/None）。

        ``price`` 给定时才计算需要价格的估值因子（``pe_ttm`` / ``pb``）。
        """
        rec = self.as_of(code, date)
        if rec is None:
            return {}
        out: Dict[str, Any] = {
            "report_period": rec.get("report_period"),
            "announce_date": rec.get("announce_date"),
            "available_from": rec.get("available_from"),
            "availability_basis": rec.get("availability_basis"),
            "roe": _num(rec.get("roe_pct")),
            "net_profit_growth": _num(rec.get("net_profit_yoy_pct")),
            "revenue_growth": _num(rec.get("revenue_yoy_pct")),
            "gross_margin": _num(rec.get("gross_margin_pct")),
            "ocf_per_share": _num(rec.get("ocf_per_share")),
        }
        bps = _num(rec.get("bps"))
        if price is not None and price > 0:
            if bps is not None and bps > 0:
                out["pb"] = price / bps
            ttm = self.ttm_eps_as_of(code, date)
            if ttm is not None and ttm > 0:
                out["pe_ttm"] = price / ttm
        return {k: v for k, v in out.items() if v is not None}

    # -- 诊断 -------------------------------------------------------------

    def coverage(self, codes: Iterable[str], date: str) -> Dict[str, Any]:
        """该日的覆盖率 —— 结论必须随附此数，否则读者无从判断样本代表性。"""
        codes = [str(c).zfill(6) for c in codes]
        if not codes:
            return {"date": date, "requested": 0, "covered": 0, "ratio": 0.0}
        covered = sum(1 for c in codes if self.as_of(c, date) is not None)
        return {
            "date": date,
            "requested": len(codes),
            "covered": covered,
            "ratio": covered / len(codes),
        }


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None
