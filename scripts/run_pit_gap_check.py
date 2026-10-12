# -*- coding: utf-8 -*-
"""PIT 快照断更检测 + 告警。

对应 ``PIT_SNAPSHOT_DESIGN.md`` §六「断更检测与补数」与 §五 第 6 步「非零退出 + 告警」。

## 为什么必须有这一步

设计文档写明：**本机后台进程会静默死亡**。若没有独立的断更检测，
「快照库」会在某天悄悄停止增长，而**没有任何信号** ——
这与本项目反复出现的「静默失效」是同一类问题，只是发生在**运维层**而非代码层。

## 判定规则（事前固定）

* **期望日** = 交易日历中 ``[--since, --until]`` 区间内的**交易日**
  （默认日历来自 baostock ``query_trade_dates``；也可传 ``benchmark.csv`` 离线用）
* **已落盘日** = ``normalized/<dataset>/*.csv`` 的文件名（日期）
* **缺口** = 期望日 − 已落盘日
* **退出码**：缺口数 > ``--allow-gaps`` → **非零**（不得静默通过）

> ⚠️ **库启动日之前的历史空缺不算缺口** —— 那段时间我们还没开始采集，
> 属「没有数据」而非「断更」。默认 ``--since`` 取**最早的已落盘日期**，
> 并把启动前区间的空缺**单独报为信息项**，不参与退出码判定。

用法::

    python scripts/run_pit_gap_check.py --root D:/pit_snapshots --all
    python scripts/run_pit_gap_check.py --root D:/pit_snapshots --dataset l1_stock_basic --since 2026-10-01
    python scripts/run_pit_gap_check.py --calendar D:/tdx_dataset_v3/benchmark.csv --all   # 离线
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pit.baostock_guard import assert_not_truncated  # noqa: E402
from pit.pit_snapshot_store import (  # noqa: E402
    DATASET_REGISTRY,
    PitSnapshotStore,
    now_cst,
)


def _trading_days_baostock(start: str, end: str) -> List[str]:
    """从 baostock 取交易日历（可选依赖，惰性导入）。"""
    try:
        import baostock as bs
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise RuntimeError("未安装 baostock。可用 --calendar <benchmark.csv> 走离线路径") from exc

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_code} {lg.error_msg}")
    try:
        rs = bs.query_trade_dates(start_date=start, end_date=end)
        if rs.error_code != "0":
            raise RuntimeError(f"交易日历查询失败: {rs.error_code} {rs.error_msg}")
        out: List[str] = []
        n_raw = 0
        while rs.next():
            # ⚠️ 必须**只取一次** row —— 连写两次 rs.get_row_data() 会在第二次越界
            # （baostock 的 ResultData 在 next() 之后只保证一次有效读取）。
            row = rs.get_row_data()
            n_raw += 1
            if str(row[1]).strip() == "1":
                out.append(str(row[0]))
    finally:
        bs.logout()
    # ⚠️ 日历被分页静默截断 → 会报出**假缺口**或漏报缺口。宁可失败。
    assert_not_truncated(n_raw, f"baostock query_trade_dates({start}~{end})")
    return out


def _trading_days_csv(path: str, start: str, end: str) -> List[str]:
    """从 benchmark.csv 取交易日（离线兜底）。"""
    out: List[str] = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            d = str(row.get("date", ""))[:10]
            if start <= d <= end:
                out.append(d)
    return sorted(out)


def _calendar(args: argparse.Namespace, start: str, end: str) -> List[str]:
    if args.calendar and args.calendar != "baostock":
        return _trading_days_csv(args.calendar, start, end)
    return _trading_days_baostock(start, end)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PIT 快照断更检测")
    ap.add_argument("--root", default="D:/pit_snapshots")
    ap.add_argument("--dataset", default="l1_stock_basic", choices=sorted(DATASET_REGISTRY))
    ap.add_argument("--all", action="store_true", help="检查全部已登记数据集")
    ap.add_argument("--since", default=None, help="起始日（默认取最早的已落盘日期）")
    ap.add_argument("--until", default=None, help="结束日（默认今天）")
    ap.add_argument("--calendar", default="baostock",
                    help="交易日历来源：baostock（默认）或 benchmark.csv 路径（离线）")
    ap.add_argument("--allow-gaps", type=int, default=0, help="容忍的缺口数（默认 0）")
    ap.add_argument("--out", default=None, help="结果 JSON 输出路径")
    args = ap.parse_args(argv)

    store = PitSnapshotStore(args.root)
    datasets = sorted(DATASET_REGISTRY) if args.all else [args.dataset]
    today = now_cst().strftime("%Y-%m-%d")
    until = args.until or today

    print("=" * 96)
    print("PIT 快照断更检测")
    print("=" * 96)
    print(f"  库根目录: {args.root} · 检查日: {until} · 容忍缺口: {args.allow_gaps}")

    report: Dict[str, Any] = {"checked_at": now_cst().isoformat(timespec="seconds"),
                              "root": str(args.root), "until": until, "datasets": {}}
    total_gaps = 0
    rc = 0

    # ⚠️ 交易日历**只拉一次**（首版对每个数据集各拉一次、还各多拉一次「启动前」区间，
    # 导致 4 次 baostock 登录/登出）。全量取回后在内存里切片。
    cal_all = _calendar(args, "1990-01-01", until)
    print(f"  交易日历: {len(cal_all)} 个交易日（1990-01-01 ~ {until}）", flush=True)

    for ds in datasets:
        landed = store.landed_dates(ds)
        if not landed:
            print(f"\n  [{ds}] ⚠️ 无任何落盘记录 → 无法判定（先跑采集）")
            report["datasets"][ds] = {"landed": 0, "gaps": [], "status": "NO_DATA"}
            continue

        first_landed = landed[0]
        since = args.since or first_landed
        cal = [d for d in cal_all if since <= d <= until]
        gaps = store.detect_gaps(ds, cal)
        pre_start = [d for d in cal_all if d < first_landed]

        print(f"\n  [{ds}]")
        print(f"    库启动日 {first_landed} · 已落盘 {len(landed)} 天 "
              f"({landed[0]} ~ {landed[-1]})")
        print(f"    期望交易日（{since} ~ {until}）: {len(cal)} 天")
        print(f"    缺口: {len(gaps)} 天 {gaps[:10] if gaps else '✓'}")
        if pre_start:
            print(f"    （信息）库启动前 {len(pre_start)} 个交易日无数据 —— 属「未开始采集」，不计缺口")

        store.write_gaps(ds, gaps)
        report["datasets"][ds] = {
            "first_landed": first_landed, "last_landed": landed[-1],
            "n_landed": len(landed), "n_expected": len(cal),
            "n_gaps": len(gaps), "gaps": gaps,
            "pre_start_days": len(pre_start),
            "status": "OK" if len(gaps) <= args.allow_gaps else "GAP",
        }
        total_gaps += len(gaps)
        if len(gaps) > args.allow_gaps:
            rc = 3

    print("\n" + "=" * 96)
    if rc:
        print(f"  ❌ 断更告警：共 {total_gaps} 个缺口 > 容忍 {args.allow_gaps} → 非零退出")
        print("     → 补数前先确认源是否**有回溯窗口**：有则用该源的**回溯值**补，")
        print("       无则**如实标记缺失，绝不回填**（原则 #1：数据缺失即缺失）")
    else:
        print(f"  完成：无超限缺口（总缺口 {total_gaps}）")
    print("=" * 96)

    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with outp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"  已写 {outp}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
