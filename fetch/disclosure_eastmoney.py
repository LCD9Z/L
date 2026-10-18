# -*- coding: utf-8 -*-
"""东财预约披露时间表 —— 公告日第二数据源（DATA_CHANNEL_PREREG 组件 C，A8）。

## 为什么要有第二源

PIT 的首选依据此前只有巨潮一张表（`fetch/fundamentals_source.py` 的
`fetch_disclosure_period`）。单一来源意味着：

* 覆盖率缺口无从交叉验证（实测池内 12.8% 记录退法定截止日兜底）；
* 表本身出问题（如 2026-09 实测的 176,841 → 176,830 静默漂移）
  时**没有第二个声音**。

本模块提供**独立第二源**：东方财富数据中心预约披露时间表。

## 端点（真实出处，写进 meta）

``https://datacenter-web.eastmoney.com/api/data/v1/get``
``?reportName=RPT_PUBLIC_BS_APPOIN&columns=ALL&pageSize=5000``
``&pageNumber=N&filter=(REPORT_DATE='YYYY-MM-DD')``

即 akshare ``stock_yysj_em``（预约披露时间）的底层数据源。
本环境 **akshare 未安装**，故直连 HTTP（经 `fetch/transport.py` 的
限流 + 重试），不引入依赖；「akshare 函数名 ↔ 端点」对照记录在此。

## 字段与巨潮表的同构性（交叉校验的前提）

===================================  ==============================
本模块（东财）                       巨潮表（`load_disclosures`）
===================================  ==============================
``first_appoint``  FIRST_APPOINT_DATE  ``first_scheduled``（首次预约）
``actual_publish`` ACTUAL_PUBLISH_DATE  ``actual_disclose``（实际披露）
``revisions``      三个 CHANGE_DATE     ``revisions``（变更次数）
===================================  ==============================

两表语义对齐 ⇒ `scripts/crosscheck_disclosure_sources.py` 做逐
``(code, report_period)`` 比对。**冲突不静默覆盖**：本表只作证据，
PIT 主口径（`pit.pit_fundamentals.resolve_availability`）本轮不动。

## 缺失即缺失

``ACTUAL_PUBLISH_DATE`` 为 null（尚未披露）的行**仍产出**（带
``first_appoint``），但 ``actual_publish`` 记空串 —— 预约日不是
实际披露日，不许混为一谈。
"""
from __future__ import annotations

import json
import urllib.parse
from typing import Any, Dict, List

from .transport import _http_get

__all__ = [
    "AKSHARE_REFERENCE",
    "APPOINTMENT_ENDPOINT",
    "fetch_all_appointments",
    "fetch_appointment_period",
    "parse_appointment_rows",
    "report_period_to_iso",
]

#: 端点与 akshare 对照（真实出处）
APPOINTMENT_ENDPOINT = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?reportName=RPT_PUBLIC_BS_APPOIN&columns=ALL")
AKSHARE_REFERENCE = "akshare stock_yysj_em（东方财富-数据中心-预约披露时间）"

_ISO_DATE_LEN = 10


def report_period_to_iso(period: str) -> str:
    """``"20240331"`` → ``"2024-03-31"``。"""
    if len(period) != 8 or not period.isdigit():
        raise ValueError(f"非法报告期：{period!r}（应为 YYYYMMDD）")
    return f"{period[:4]}-{period[4:6]}-{period[6:8]}"


def _date_only(value: Any) -> str:
    """``"2024-04-20 00:00:00"`` → ``"2024-04-20"``；缺失/``null`` → 空串。"""
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() in ("nat", "nan", "none", "null"):
        return ""
    return s[:_ISO_DATE_LEN]


def parse_appointment_rows(payload: Any, report_period: str) -> List[Dict[str, Any]]:
    """把 API 响应解析成本项目行格式。

    ``report_period`` 为 ISO 形式（``"2024-03-31"``）。schema 不符
    （缺 ``result``/``data``）抛 :class:`ValueError` —— **不把
    「接口挂了」当成「该期无数据」**。
    """
    if not isinstance(payload, dict):
        raise ValueError(f"响应不是 JSON object：{type(payload).__name__}")
    result = payload.get("result")
    if not isinstance(result, dict) or "data" not in result:
        raise ValueError("响应缺少 result.data（接口 schema 变更或异常）")
    rows_in = result.get("data") or []
    if not isinstance(rows_in, list):
        raise ValueError("result.data 不是列表")
    out: List[Dict[str, Any]] = []
    for raw in rows_in:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("SECURITY_CODE") or "").strip()
        if not code:
            continue  # 无代码的行无法定位到证券，跳过并计数（见调用方）
        secucode = str(raw.get("SECUCODE") or "")
        market = secucode.rsplit(".", 1)[-1].lower() if "." in secucode else ""
        changes = [_date_only(raw.get(k)) for k in
                   ("FIRST_CHANGE_DATE", "SECOND_CHANGE_DATE", "THIRD_CHANGE_DATE")]
        out.append({
            "code": code.zfill(6),
            "report_period": report_period,
            "secucode": secucode,
            "market": market,
            "name": str(raw.get("SECURITY_NAME_ABBR") or ""),
            "first_appoint": _date_only(raw.get("FIRST_APPOINT_DATE")),
            "first_change": changes[0],
            "second_change": changes[1],
            "third_change": changes[2],
            "revisions": sum(1 for c in changes if c),
            "appoint_publish": _date_only(raw.get("APPOINT_PUBLISH_DATE")),
            "actual_publish": _date_only(raw.get("ACTUAL_PUBLISH_DATE")),
            "is_publish": str(raw.get("IS_PUBLISH") or ""),
            "report_type_name": str(raw.get("REPORT_TYPE_NAME") or ""),
        })
    return out


def fetch_appointment_period(period: str, *, page_size: int = 5000,
                             max_pages: int = 20) -> Dict[str, Any]:
    """抓取单个报告期的全市场预约披露表。

    ``period`` 形如 ``"20240331"``。返回
    ``{"records": [...], "pages": n, "rows": n}``。
    网络失败 / schema 异常抛 :class:`RuntimeError`（诚实失败，
    不返回空表冒充「该期无数据」）。
    """
    iso = report_period_to_iso(period)
    filt = urllib.parse.quote(f"(REPORT_DATE='{iso}')", safe="()'=")
    records: List[Dict[str, Any]] = []
    pages = 0
    for page in range(1, max_pages + 1):
        url = f"{APPOINTMENT_ENDPOINT}&pageSize={page_size}&pageNumber={page}&filter={filt}"
        text = _http_get(url)
        if text is None:
            raise RuntimeError(f"东财预约披露接口无响应（{period} 第 {page} 页）")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"东财预约披露接口返回非 JSON（{period} 第 {page} 页）") from exc
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or "data" not in result:
            raise RuntimeError(f"东财预约披露接口 schema 异常（{period} 第 {page} 页）")
        pages += 1
        data = result.get("data") or []
        if data:
            records.extend(parse_appointment_rows(payload, iso))
        total_pages = int(result.get("pages") or 1)
        if page >= total_pages:
            break
    return {"records": records, "pages": pages, "rows": len(records)}


def fetch_all_appointments(periods: List[str], *, out_path: str,
                           delay: float = 0.2, resume: bool = True,
                           on_progress=None) -> Dict[str, Any]:
    """逐期抓取并**按期追加**落盘（本机 5 分钟前台上限的教训）。

    ``resume=True`` 时跳过输出文件中已有记录的期。失败的期记入
    ``failed`` 并**如实返回**，不静默跳过。
    """
    from pathlib import Path
    p = Path(out_path)
    done: Dict[str, int] = {}
    if resume and p.is_file():
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rp = str(r.get("report_period") or "")
                if rp:
                    done[rp] = done.get(rp, 0) + 1
    ok: List[str] = []
    failed: Dict[str, str] = {}
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        for i, period in enumerate(periods, 1):
            iso = report_period_to_iso(period)
            if done.get(iso):
                ok.append(period)
                if on_progress:
                    on_progress(i, len(periods), period, done[iso], "resume")
                continue
            try:
                got = fetch_appointment_period(period)
            except (RuntimeError, ValueError) as exc:
                failed[period] = str(exc)
                if on_progress:
                    on_progress(i, len(periods), period, 0, str(exc))
                continue
            if not got["records"]:
                failed[period] = "empty_records"
                if on_progress:
                    on_progress(i, len(periods), period, 0, "empty_records")
                continue
            for r in got["records"]:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
            done[iso] = got["rows"]
            ok.append(period)
            if on_progress:
                on_progress(i, len(periods), period, got["rows"], "")
            if delay:
                import time
                time.sleep(delay)
    return {"ok_periods": ok, "failed": failed, "rows_by_period": done}
