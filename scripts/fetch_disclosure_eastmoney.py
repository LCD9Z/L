# -*- coding: utf-8 -*-
"""抓取东财预约披露时间表（DATA_CHANNEL_PREREG 组件 C，A8 数据通道）。

数据源：东方财富数据中心 ``RPT_PUBLIC_BS_APPOIN``（**直连 HTTP**，
akshare 未装故不引入依赖；akshare 侧对应函数为 ``stock_yysj_em``）。
产物：``disclosure_eastmoney.jsonl`` + ``.meta.json``（真实出处 + 指纹）。

用法::

    python scripts/fetch_disclosure_eastmoney.py                     # 2016Q1~2026Q3
    python scripts/fetch_disclosure_eastmoney.py --start 20240331 --end 20241231
    python scripts/fetch_disclosure_eastmoney.py --no-resume         # 从头重写

**按期追加落盘**：每期一批请求写完即 flush；中断后 ``--resume``
跳过已抓期。失败的期记入 meta 的 ``failed``，不静默跳过。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch.disclosure_eastmoney import (  # noqa: E402
    AKSHARE_REFERENCE,
    APPOINTMENT_ENDPOINT,
    fetch_all_appointments,
)
from fetch.fingerprint import fingerprint_file  # noqa: E402
from fetch.fundamentals_source import report_periods  # noqa: E402


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取东财预约披露时间表（A8 第二源）")
    ap.add_argument("--start", default="20160331", help="起始报告期 YYYYMMDD")
    ap.add_argument("--end", default="20260930", help="结束报告期 YYYYMMDD")
    ap.add_argument("--out", default="D:/tdx_dataset_v3/disclosure_eastmoney.jsonl")
    ap.add_argument("--delay", type=float, default=0.2, help="每期间隔秒数")
    ap.add_argument("--no-resume", action="store_true", help="忽略已有文件，从头重写")
    args = ap.parse_args()

    start_y, end_y = int(args.start[:4]), int(args.end[:4])
    periods = [p for p in report_periods(start_y, end_y)
               if args.start <= p <= args.end]
    if not periods:
        print(f"报告期范围为空：{args.start} ~ {args.end}", flush=True)
        return 2
    print(f"待抓 {len(periods)} 期（{periods[0]} ~ {periods[-1]}）", flush=True)

    out = Path(args.out)
    if args.no_resume and out.exists():
        out.unlink()

    def _progress(i: int, n: int, period: str, rows: int, err: str) -> None:
        tag = f"  [{i}/{n}] {period}"
        if err and err != "resume":
            print(f"{tag} 失败：{err[:80]}", flush=True)
        elif err == "resume":
            print(f"{tag} 已抓过（{rows:,} 行），跳过", flush=True)
        else:
            print(f"{tag} 写入 {rows:,} 行", flush=True)

    result = fetch_all_appointments(periods, out_path=str(out), delay=args.delay,
                                    resume=not args.no_resume, on_progress=_progress)
    total = sum(result["rows_by_period"].values())
    fp = fingerprint_file(out) if out.is_file() else None
    meta: Dict[str, Any] = {
        "source": (f"东方财富数据中心直连 {APPOINTMENT_ENDPOINT}"
                   f"（akshare 对应函数：{AKSHARE_REFERENCE}；akshare 未安装，"
                   f"故直连，不引入依赖）"),
        "fetched_at": _now(),
        "periods_total": len(periods),
        "rows_by_period": result["rows_by_period"],
        "rows_total": total,
        "failed": result["failed"],
        "fingerprint": fp,
        "caveats": [
            "actual_publish 为空 = 尚未披露（不产出日期，只带预约日）",
            "market/secucode 取自 API 的 SECUCODE 字段，供交叉校验",
            "与巨潮表（disclosure_dates.jsonl）语义同构："
            "first_appoint↔first_scheduled、actual_publish↔actual_disclose",
            "本表只作第二源证据，不改 pit.pit_fundamentals 的 PIT 主口径",
        ],
    }
    out.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"\n完成：成功 {len(result['ok_periods'])} 期 / 共 {len(periods)} 期，"
          f"累计 {total:,} 行 → {out}", flush=True)
    if result["failed"]:
        print(f"失败 {len(result['failed'])} 期：{sorted(result['failed'])}", flush=True)
        print("  （失败期必须随结论声明，不得按「无数据」处理）", flush=True)
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
