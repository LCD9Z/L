# -*- coding: utf-8 -*-
"""从东方财富抓取 A 股分红送股数据，输出为项目公司行动层可消费的 CSV。

## 数据源

东方财富数据中心 `RPT_SHAREBONUS_DET`（分红送股详情），公开接口，无需凭据。

## 字段与单位（**已实测核对**）

源字段 → 输出字段的映射遵循 `corporate_action_provider.normalize_tushare_dividend`
的单位约定（该约定由 `test_corporate_action_provider.py` 明确）：

| 输出字段 | 来源 | 单位 |
|---------|------|------|
| `stk_bo_rate` | `BONUS_RATIO` | **每 10 股**送股数（原样，归一化时除以 10） |
| `stk_co_rate` | `IT_RATIO` | **每 10 股**转增数（原样） |
| `cash_div` | `PRETAX_BONUS_RMB` / 10 | **每股**税前派息 |

实测核对：`10转4.50股派0.69元` → 派=0.69 转=4.5 → 输出 `stk_co_rate=4.5`, `cash_div=0.069`
→ 归一化后 `bonus_ratio=0.45`, `cash_dividend=0.069` ✓

## PIT 提醒（重要）

接口会返回**尚未实施的分红预案**（如除权日在未来的记录）。本脚本**原样保留**
并附带 `assign_progress` / `notice_date` / `publish_date` 字段，
**由下游按研究需要过滤**。做历史复权时应只用除权日已过的记录。

用法::

    python fetch_corporate_actions.py --start 2021-08-01 --end 2026-09-10 \
        --out D:/tdx_dataset/corporate_actions.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import socket
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, List

API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORT = "RPT_SHAREBONUS_DET"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://data.eastmoney.com/",
}

# 输出列（前 7 列与 corporate_action_ingest.read_tushare_csv 兼容）
OUT_COLUMNS = [
    "ts_code", "ex_date", "stk_bo_rate", "stk_co_rate", "cash_div",
    "rights_ratio", "issue_price",
    # 附加元数据（供 PIT 过滤与审计）
    "security_code", "security_name", "plan_profile", "assign_progress",
    "notice_date", "publish_date", "report_date",
]


def _to_float(v: Any) -> float:
    if v in (None, "", "None", "nan"):
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _date8(v: Any) -> str:
    """``2026-06-26 00:00:00`` → ``20260626``；无效则返回空串。"""
    s = str(v or "").strip()
    if len(s) < 10 or s.startswith("None"):
        return ""
    return s[:10].replace("-", "")


def _to_ts_code(code: str, market_flag: Any) -> str:
    """``601688`` + 市场标识 → ``601688.SH``。

    东方财富的 `SECUCODE` 已带后缀，优先使用；否则按代码段推断。
    """
    c = str(code).zfill(6)
    if c.startswith(("600", "601", "603", "605", "688", "689")):
        return f"{c}.SH"
    if c.startswith(("000", "001", "002", "003", "300", "301", "302")):
        return f"{c}.SZ"
    if c.startswith(("43", "83", "87", "88", "92")):
        return f"{c}.BJ"
    return f"{c}.SH"


def fetch_page(page: int, page_size: int, start: str, end: str,
               retries: int = 3) -> Dict[str, Any]:
    """抓取一页。返回 API 的 ``result`` 字典（可能为空）。"""
    params = {
        "reportName": REPORT,
        "columns": "ALL",
        "pageSize": page_size,
        "pageNumber": page,
        "filter": f"(EX_DIVIDEND_DATE>='{start}')(EX_DIVIDEND_DATE<='{end}')",
        "sortColumns": "EX_DIVIDEND_DATE",
        "sortTypes": "1",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            return data.get("result") or {}
        except Exception as exc:  # 网络抖动重试
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"抓取第 {page} 页失败: {last}")


def iter_actions(start: str, end: str, page_size: int = 500,
                 rate: float = 2.0) -> Iterator[Dict[str, Any]]:
    """按页产出规范化后的公司行动记录（**原样保留未实施预案**）。"""
    interval = 1.0 / rate if rate > 0 else 0.0
    page = 1
    total_pages = None
    fetched = 0
    while True:
        res = fetch_page(page, page_size, start, end)
        rows: List[Dict[str, Any]] = res.get("data") or []
        if total_pages is None:
            total_pages = int(res.get("pages") or 0)
            print(f"  共 {res.get('count')} 条记录 / {total_pages} 页", flush=True)
        if not rows:
            break
        for row in rows:
            ex = _date8(row.get("EX_DIVIDEND_DATE"))
            code = str(row.get("SECURITY_CODE") or "").zfill(6)
            if not ex or not code.isdigit():
                continue
            secucode = str(row.get("SECUCODE") or "")
            ts_code = secucode if "." in secucode else _to_ts_code(code, None)
            yield {
                "ts_code": ts_code,
                # 送股/转增保持「每 10 股」原样，与归一化层的 /10 约定配套
                "stk_bo_rate": _to_float(row.get("BONUS_RATIO")),
                "stk_co_rate": _to_float(row.get("IT_RATIO")),
                # 派息换算为「每股」
                "cash_div": round(_to_float(row.get("PRETAX_BONUS_RMB")) / 10.0, 8),
                "rights_ratio": 0.0,      # 配股在另一报表，本接口不含
                "issue_price": 0.0,
                "ex_date": ex,
                "security_code": code,
                "security_name": str(row.get("SECURITY_NAME_ABBR") or ""),
                "plan_profile": str(row.get("IMPL_PLAN_PROFILE") or ""),
                "assign_progress": str(row.get("ASSIGN_PROGRESS") or ""),
                "notice_date": _date8(row.get("NOTICE_DATE")),
                "publish_date": _date8(row.get("PUBLISH_DATE")),
                "report_date": _date8(row.get("REPORT_DATE")),
            }
        fetched += len(rows)
        if total_pages and page >= total_pages:
            break
        page += 1
        if interval:
            time.sleep(interval)
    print(f"  已抓取 {fetched} 行", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取东方财富分红送股数据")
    ap.add_argument("--start", default="2021-08-01", help="除权日起始 YYYY-MM-DD")
    ap.add_argument("--end", default="2026-09-10", help="除权日截止 YYYY-MM-DD")
    ap.add_argument("--out", required=True, help="输出 CSV 路径")
    ap.add_argument("--page-size", type=int, default=500)
    ap.add_argument("--rate", type=float, default=2.0, help="请求速率（次/秒）")
    args = ap.parse_args()

    socket.setdefaulttimeout(25)
    print("=" * 80)
    print(f"抓取分红送股数据  除权日 {args.start} ~ {args.end}")
    print("=" * 80)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    n = 0
    codes: set = set()
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLUMNS)
        w.writeheader()
        for rec in iter_actions(args.start, args.end, args.page_size, args.rate):
            w.writerow(rec)
            n += 1
            codes.add(rec["security_code"])

    print(f"\n完成：{n:,} 行，覆盖 {len(codes):,} 只股票")
    print(f"输出：{args.out}")
    print("\n提醒：CSV 含**未实施的分红预案**（除权日在未来）。")
    print("      做历史复权时请按 ex_date 与研究区间过滤。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
