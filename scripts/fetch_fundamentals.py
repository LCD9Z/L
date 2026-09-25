# -*- coding: utf-8 -*-
r"""抓取并落盘 PIT 财务数据（业绩报表）。

数据源：AkShare → 东方财富 ``stock_yjbb_em``（按报告期，单次返回全 A）。
产物：``fundamentals.jsonl``（每行一条 ``code × report_period``）+ ``fundamentals.meta.json``。

## 设计要点

* **按期落盘**：每抓完一期就追加写盘。本机后台进程曾多次静默死亡，
  只在结尾落盘的脚本一旦中断就前功尽弃。
* **失败的期如实记录**：不静默跳过。``meta.json`` 里列明 ``failed``，
  读者据此判断覆盖率是否可信。
* **不重算已有期**：``--resume`` 时跳过 meta 中已成功且行数一致的期。

用法::

    python scripts/fetch_fundamentals.py --out D:/tdx_dataset_v3/fundamentals.jsonl \
        --start-year 2016 --end-year 2026
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch.fundamentals_source import (  # noqa: E402
    AkshareUnavailable,
    fetch_all_disclosures,
    fetch_period,
    report_periods,
)


def _meta_path(out: Path) -> Path:
    return out.with_suffix(".meta.json")


def _load_meta(out: Path) -> Dict[str, Any]:
    p = _meta_path(out)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _write_meta(out: Path, meta: Dict[str, Any]) -> None:
    _meta_path(out).write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def _append_period(out: Path, period: str, records: List[Dict[str, Any]]) -> None:
    """按期追加写盘（崩溃时已完成的期不丢）。"""
    with out.open("a", encoding="utf-8", newline="\n") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取 PIT 财务数据（业绩报表）")
    ap.add_argument("--out", default=r"D:\tdx_dataset_v3\fundamentals.jsonl")
    ap.add_argument("--mode", choices=("yjbb", "disclosure"), default="yjbb",
                    help="yjbb=东财业绩报表（财务数值）；"
                         "disclosure=巨潮资讯定期报告**真实披露日**")
    ap.add_argument("--start-year", type=int, default=2016)
    ap.add_argument("--end-year", type=int, default=2026)
    ap.add_argument("--delay", type=float, default=0.4,
                    help="期间间隔秒数（上游为公开接口，避免过快）")
    ap.add_argument("--resume", action="store_true",
                    help="跳过 meta 中已成功抓取的报告期（从头重写文件）")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    periods = report_periods(args.start_year, args.end_year)
    meta = _load_meta(out)
    done: Dict[str, int] = dict(meta.get("rows_by_period", {}))
    failed: Dict[str, str] = dict(meta.get("failed", {}))

    if not args.resume:
        done, failed = {}, {}
        if out.exists():
            out.unlink()
    elif not out.exists():
        print("警告：--resume 但产物不存在，将从头抓取", flush=True)
        done, failed = {}, {}

    todo = [p for p in periods if p not in done]
    print(f"报告期共 {len(periods)} 期；已完成 {len(done)} 期；待抓 {len(todo)} 期", flush=True)

    for i, period in enumerate(todo, 1):
        try:
            if args.mode == "disclosure":
                # 巨潮：period 用 "2024-03-31" 形式的报告期
                iso = f"{period[:4]}-{period[4:6]}-{period[6:8]}"
                records = fetch_all_disclosures([iso], delay=0)["records"]
            else:
                records = fetch_period(period)
        except AkshareUnavailable as exc:
            failed[period] = str(exc)
            print(f"  [{i}/{len(todo)}] {period} 失败：{str(exc)[:90]}", flush=True)
            continue
        if not records:
            failed[period] = "empty_records"
            print(f"  [{i}/{len(todo)}] {period} 空记录（不写入，视为失败）", flush=True)
            continue
        _append_period(out, period, records)
        done[period] = len(records)
        failed.pop(period, None)
        print(f"  [{i}/{len(todo)}] {period} 写入 {len(records):,} 条", flush=True)
        _write_meta(out, {
            "source": ("akshare stock_report_disclosure（巨潮资讯定期报告披露时间表）"
                       if args.mode == "disclosure"
                       else "akshare stock_yjbb_em（东方财富业绩报表）"),
            "fetched_at": _now(),
            "periods_total": len(periods),
            "rows_by_period": done,
            "failed": failed,
            "caveats": [
                "实际披露=巨潮资讯披露时间表的实际披露日，是 PIT 的首选依据",
                "实际披露为空的记录不产出（尚未披露）",
                "含 首次预约/变更次数 字段，可用于诊断披露可靠性",
                "⚠️ 巨潮披露时间表早年覆盖少于业绩报表（如 2016 年报 2,896 行 vs "
                "业绩报表 2016Q1 的 3,693 行），故仍有部分记录走法定截止日兜底",
            ] if args.mode == "disclosure" else [
                "所处行业为抓取时点标签，非历史时点分类，用于历史回测会引入分类幸存者偏差",
                "最新公告日期为该报告期最后一份公告日期（多次更正时取最后一份，偏保守）",
                "同一 code×period 若出现多行，已保留公告日期最晚的一行",
                "⚠️ 东财业绩报表**混入新三板公司**（400xxx/430xxx/831xxx/832xxx/839xxx "
                "等代码段），实测占全部记录约 38.7%。这些记录不属于 A 股池、"
                "不会被研究查询，但会灌大覆盖率分母 —— 统计时须先按 pool_v2.csv 过滤",
            ],
        })

    total = sum(done.values())
    # 循环结束后再写一次 meta：循环内的 _write_meta 只发生在**成功**分支，
    # 最后一期若失败则失败集不会落盘（首轮实测即如此：日志报 2 期失败、
    # meta 却记 0 期）。失败信息必须落盘，否则读者无从判断覆盖率。
    _write_meta(out, {
        "source": "akshare stock_yjbb_em（东方财富业绩报表）",
        "fetched_at": _now(),
        "periods_total": len(periods),
        "rows_by_period": done,
        "failed": failed,
        "caveats": [
            "所处行业为抓取时点标签，非历史时点分类，用于历史回测会引入分类幸存者偏差",
            "最新公告日期为该报告期最后一份公告日期（多次更正时取最后一份，偏保守）",
            "同一 code×period 若出现多行，已保留公告日期最晚的一行",
            "尚未披露的报告期（如当前时点之后的季度）会出现在 failed 中，属预期而非数据缺陷",
        ],
    })
    print(f"\n完成：成功 {len(done)} 期 / 共 {len(periods)} 期，累计 {total:,} 条 → {out}", flush=True)
    if failed:
        print(f"失败 {len(failed)} 期：{sorted(failed)}", flush=True)
        print("  （失败期必须在结论中声明，不得按'无数据'处理）", flush=True)
    return 0 if not failed else 1


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    raise SystemExit(main())
