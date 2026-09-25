# -*- coding: utf-8 -*-
"""业绩报表数据源适配（AkShare / 东方财富）。

## 设计约束

核心数据管道保持**零第三方依赖**：``akshare`` / ``pandas`` 一律**惰性导入**，
未安装或接口不可用时抛 :class:`AkshareUnavailable` —— **诚实失败**，
绝不返回空表冒充"该期无数据"（那会把"数据源挂了"误读成"公司没业绩"）。

## 数据内容

``ak.stock_yjbb_em(date=报告期)`` 单次返回该报告期**全部 A 股**的业绩报表：

    每股收益 / 营业总收入(+同比) / 净利润(+同比) / 每股净资产 /
    净资产收益率 / 每股经营现金流量 / 销售毛利率 / 所处行业 / 最新公告日期

## 时点正确性（PIT）

关键字段是 ``最新公告日期`` —— 它是**时点正确性的唯一依据**。
2024Q1 的报表若 2024-04-25 才公告，则 2024-04-25 之前**不得使用**它。
本模块只负责如实抓取并保留该字段；PIT 语义由 :mod:`pit.pit_fundamentals` 实现。

## 已知局限（必须随结论声明）

* ``所处行业`` 是**抓取时点**的行业标签，**不是历史时点分类** ——
  用它回填历史会引入分类幸存者偏差。做行业中性化前必须另行获取
  行业变更历史，或明确声明该局限。
* 东财业绩报表的 ``最新公告日期`` 是**该报告期最后一份公告的日期**；
  同一报告期多次更正公告时，以最后一份为准（更保守，不会提前使用）。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

__all__ = [
    "DISCLOSURE_PERIOD_SUFFIX",
    "REPORT_PERIODS_QUARTER_ENDS",
    "AkshareUnavailable",
    "disclosure_period_label",
    "fetch_all_disclosures",
    "fetch_all_periods",
    "fetch_disclosure_period",
    "fetch_period",
    "normalize_row",
    "report_periods",
]


class AkshareUnavailable(RuntimeError):
    """akshare（或其依赖 pandas）不可用。

    调用方应把它当作**阻断**处理，而不是当作"没有数据"。
    """


def _ak():
    """惰性导入 akshare；不可用时诚实失败。"""
    try:
        import akshare  # noqa: PLC0415 —— 刻意惰性导入，保持核心零依赖
    except ImportError as exc:  # pragma: no cover - 取决于运行环境
        raise AkshareUnavailable(
            "akshare 未安装：pip install akshare（核心数据管道不依赖它，"
            "但财务数据接入需要）"
        ) from exc
    return akshare


# 报告期季度末（月-日）
REPORT_PERIODS_QUARTER_ENDS = {"Q1": "0331", "Q2": "0630", "Q3": "0930", "Q4": "1231"}

# 注：法定披露截止日与"公告日是否可信"的判定属 **PIT 语义**，
# 定义在 `pit/pit_fundamentals.py`（该包要求自包含）。本模块只负责如实抓取。


def report_periods(start_year: int, end_year: int) -> List[str]:
    """生成报告期列表 ``["20160331", ...]``（升序）。"""
    out: List[str] = []
    for year in range(start_year, end_year + 1):
        for suffix in ("0331", "0630", "0930", "1231"):
            out.append(f"{year}{suffix}")
    return out


def _num(value: Any) -> Optional[float]:
    """把东财的数值列解析为 float；``-`` / 空 / 非数值一律返回 None（不补造）。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if f == f else None
    s = str(value).strip().replace(",", "")
    if s in ("", "-", "--", "None", "nan", "NaN"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f == f else None


def _text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() in ("nan", "none") else s


def _norm_date(value: Any) -> str:
    """把 ``2024-04-25`` / ``20240425`` / Timestamp 统一成 ``YYYY-MM-DD``。

    ⚠️ pandas 的缺失值是 ``NaT`` / ``NaN``，``str()`` 之后**不是空串** ——
    若只判 ``None``，``"NaT"`` 会作为"合法日期"流进下游。
    2026-09-25 实测：巨潮披露日 176,841 条中有 **11 条** ``actual_disclose="NaT"``，
    下游 ``if not actual`` 抓不住，直接污染了「披露时点偏离」的分布计算。
    **缺失即缺失** —— 这里统一归成空串，由调用方决定如何处置。
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in ("nat", "nan", "none", ""):
        return ""
    s = s.replace("/", "-")
    if len(s) >= 10:
        return s[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def normalize_row(row: Dict[str, Any], period: str) -> Optional[Dict[str, Any]]:
    """把东财原始行归一化为本项目记录；缺关键字段返回 ``None``。

    注意：股票代码必须**先判空再补零** —— ``"".zfill(6)`` 会得到 ``"000000"``
    这个看似合法的值，把"该行无代码"静默变成一个假股票。
    """
    raw_code = _text(row.get("股票代码"))
    announce = _norm_date(row.get("最新公告日期"))
    if not raw_code or not announce:
        return None
    code = raw_code.zfill(6)
    period_iso = f"{period[:4]}-{period[4:6]}-{period[6:8]}"
    return {
        "code": code,
        "report_period": period_iso,
        "announce_date": announce,
        "name": _text(row.get("股票简称")),
        "industry": _text(row.get("所处行业")),
        "eps": _num(row.get("每股收益")),
        "revenue": _num(row.get("营业总收入-营业总收入")),
        "revenue_yoy_pct": _num(row.get("营业总收入-同比增长")),
        "net_profit": _num(row.get("净利润-净利润")),
        "net_profit_yoy_pct": _num(row.get("净利润-同比增长")),
        "bps": _num(row.get("每股净资产")),
        "roe_pct": _num(row.get("净资产收益率")),
        "ocf_per_share": _num(row.get("每股经营现金流量")),
        "gross_margin_pct": _num(row.get("销售毛利率")),
    }


def fetch_period(period: str) -> List[Dict[str, Any]]:
    """抓取单个报告期的全部 A 股业绩报表。

    ``period`` 形如 ``"20240331"``。同一 ``code`` 出现多行时**保留公告日期最晚的
    一行**（更保守：不会提前使用更正前的旧数）。
    """
    ak = _ak()
    try:
        frame = ak.stock_yjbb_em(date=period)
    except Exception as exc:  # pragma: no cover - 取决于网络与上游
        raise AkshareUnavailable(f"stock_yjbb_em({period}) 失败：{exc!r}") from exc
    if frame is None:
        raise AkshareUnavailable(f"stock_yjbb_em({period}) 返回 None")

    best: Dict[str, Dict[str, Any]] = {}
    for raw in frame.to_dict("records"):
        rec = normalize_row(raw, period)
        if rec is None:
            continue
        prev = best.get(rec["code"])
        if prev is None or rec["announce_date"] >= prev["announce_date"]:
            best[rec["code"]] = rec
    return [best[c] for c in sorted(best)]


def fetch_all_periods(periods: List[str], *, delay: float = 0.4,
                      on_progress=None) -> Dict[str, Any]:
    """逐期抓取。**失败的期不静默跳过** —— 记入 ``failed`` 并如实返回。

    **空结果也算失败**：上游对某期返回 0 行，意味着该期不可信
    （接口异常或该期数据缺失），不能当作"成功但没有数据"，
    否则覆盖率会被高估。

    返回 ``{"records": [...], "ok_periods": [...], "failed": {period: reason}}``。
    """
    records: List[Dict[str, Any]] = []
    ok: List[str] = []
    failed: Dict[str, str] = {}
    for i, period in enumerate(periods):
        try:
            got = fetch_period(period)
        except AkshareUnavailable as exc:
            failed[period] = str(exc)
            if on_progress:
                on_progress(i + 1, len(periods), period, 0, str(exc))
            continue
        if not got:
            failed[period] = "empty_records"
            if on_progress:
                on_progress(i + 1, len(periods), period, 0, "empty_records")
            continue
        records.extend(got)
        ok.append(period)
        if on_progress:
            on_progress(i + 1, len(periods), period, len(got), "")
        if delay:
            time.sleep(delay)
    return {"records": records, "ok_periods": ok, "failed": failed}


# ---------------------------------------------------------------------------
# 真实披露日（巨潮资讯）—— 取代"法定截止日兜底"
#
# 动机：东财业绩报表的 `最新公告日期` 在 2016-01 ~ 2025-06 的**全部**报告期上
# 系统性偏移 +1 年（实测 88.4% 的记录不可信），此前只能用**法定披露截止日**兜底。
# 兜底虽保守（不会前视），但会把数据可用时间整体推迟数周至数月。
#
# 巨潮资讯 `stock_report_disclosure` 按**报告期**返回全市场披露时间表，含
#   `首次预约` / `初次变更` / `二次变更` / `三次变更` / **`实际披露`**
# —— 最后一项即**真实披露日**，且是**批量**接口（每期 2,000~5,500 只）。
# 覆盖范围实测 2010 年报 ~ 2025 年报（2026 年报尚未到披露期）。
# ---------------------------------------------------------------------------

# 报告期 → 巨潮的期数标签后缀
DISCLOSURE_PERIOD_SUFFIX = {"Q1": "一季", "Q2": "半年报", "Q3": "三季", "Q4": "年报"}
_QUARTER_OF_MONTH_DAY = {"03-31": "Q1", "06-30": "Q2", "09-30": "Q3", "12-31": "Q4"}


def disclosure_period_label(report_period: str) -> str:
    """``"2024-03-31"`` → ``"2024一季"``（巨潮 `period` 参数格式）。"""
    year, month_day = report_period[:4], report_period[5:10]
    q = _QUARTER_OF_MONTH_DAY.get(month_day)
    if q is None:
        raise ValueError(f"非法报告期: {report_period}")
    return f"{year}{DISCLOSURE_PERIOD_SUFFIX[q]}"


def fetch_disclosure_period(report_period: str) -> List[Dict[str, Any]]:
    """抓取某报告期**全市场**的真实披露日。

    ``report_period`` 形如 ``"2024-03-31"``。返回
    ``[{code, report_period, actual_disclose, first_scheduled, revisions}]``；
    ``实际披露`` 为空（尚未披露）的记录**不产出** —— 缺失即缺失，不补造。
    """
    ak = _ak()
    label = disclosure_period_label(report_period)
    try:
        frame = ak.stock_report_disclosure(market="沪深京", period=label)
    except Exception as exc:  # pragma: no cover - 取决于网络与上游
        raise AkshareUnavailable(f"stock_report_disclosure({label}) 失败：{exc!r}") from exc
    if frame is None:
        raise AkshareUnavailable(f"stock_report_disclosure({label}) 返回 None")

    out: List[Dict[str, Any]] = []
    for raw in frame.to_dict("records"):
        code = _text(raw.get("股票代码"))
        actual = _norm_date(raw.get("实际披露"))
        if not code or not actual:
            continue
        revisions = sum(1 for k in ("初次变更", "二次变更", "三次变更")
                        if _norm_date(raw.get(k)))
        out.append({
            "code": code.zfill(6),
            "report_period": report_period,
            "actual_disclose": actual,
            "first_scheduled": _norm_date(raw.get("首次预约")),
            "revisions": revisions,
        })
    return out


def fetch_all_disclosures(report_period_list: List[str], *, delay: float = 0.4,
                          on_progress=None) -> Dict[str, Any]:
    """逐期抓取真实披露日。失败/空结果**如实记入 failed**，不静默跳过。"""
    records: List[Dict[str, Any]] = []
    ok: List[str] = []
    failed: Dict[str, str] = {}
    for i, rp in enumerate(report_period_list):
        try:
            got = fetch_disclosure_period(rp)
        except AkshareUnavailable as exc:
            failed[rp] = str(exc)
            if on_progress:
                on_progress(i + 1, len(report_period_list), rp, 0, str(exc))
            continue
        if not got:
            failed[rp] = "empty_records"
            if on_progress:
                on_progress(i + 1, len(report_period_list), rp, 0, "empty_records")
            continue
        records.extend(got)
        ok.append(rp)
        if on_progress:
            on_progress(i + 1, len(report_period_list), rp, len(got), "")
        if delay:
            time.sleep(delay)
    return {"records": records, "ok_periods": ok, "failed": failed}
