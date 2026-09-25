# -*- coding: utf-8 -*-
r"""构建**全池**等权全市场基准的日收益序列。

## 为什么单独写一个脚本

`run_tdx_rolling_eval.py` 现算的等权基准只能用**回测抽样池**（受 `--max-stocks` 限制）——
PIT 池越大，覆盖率反而越低：实测 v2 为 **26.8%**、v3 仅 **18.1%**。
而基准的代表性直接决定"超额"这个数字能不能信。

本脚本**流式**读完全部个股 CSV，只维护**每日累加器**（`{date: 收益和}`），
内存与**交易日数**成正比（约 2,600），与股票数无关 ——
因此可对全部 5,667 只计算，覆盖率接近 100%。

## 成分口径（与 `pit_universe.json` 快照等价）

快照的成员条件是 ``list_date <= d < delist_date 且 first_date <= d``
（停牌不除名）。本脚本直接由 `pool_v2.csv` 的上市/退市日复现同一条件，
从而**无需把 112 MB 的快照 JSON 展开成 1,470 万个字符串**。

## 收益口径（与 `validation/benchmark.equal_weight_returns` 一致）

* **停牌**：当日无行情按**收益 0** 计入 —— 即**计入分母、不进分子**；
  若把停牌剔出分母，会系统性**高估**基准；
* **再平衡**：日频、**不含交易成本** → 真实可实现收益更低，**不得当作可交易基准**。

产出格式与 `run_alpha_gap_probe.py --out-series` 相同，
可直接喂给 `run_tdx_rolling_eval.py --ew-series`。

用法::

    python scripts/build_equal_weight_benchmark.py --dataset D:/tdx_dataset_v3 \
        --out reports/ew_benchmark_v3.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

POOL_CANDIDATES = ("pool_v2.csv", "pool.csv")


def load_pool(dataset: Path) -> Dict[str, Tuple[str, str, str]]:
    """``{code: (list_date, delist_date, first_date)}``。"""
    for name in POOL_CANDIDATES:
        p = dataset / name
        if p.exists():
            out: Dict[str, Tuple[str, str, str]] = {}
            with p.open(encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    out[r["code"].zfill(6)] = (r.get("list_date", ""),
                                               r.get("delist_date", ""),
                                               r.get("first_date", ""))
            return out
    raise FileNotFoundError(f"{dataset} 下未找到 {'/'.join(POOL_CANDIDATES)}")


def load_calendar(dataset: Path) -> List[str]:
    bm = dataset / "benchmark.csv"
    if bm.exists():
        with bm.open(encoding="utf-8-sig", newline="") as fh:
            return sorted(r["date"] for r in csv.DictReader(fh))
    return []


def member_count_by_day(pool: Dict[str, Tuple[str, str, str]],
                        calendar: List[str]) -> Dict[str, int]:
    """每个交易日的 PIT 成员数（停牌不除名）。"""
    out: Dict[str, int] = {}
    items = list(pool.values())
    for day in calendar:
        n = 0
        for list_date, delist_date, first_date in items:
            if list_date and list_date > day:
                continue
            if delist_date and delist_date <= day:
                continue
            if first_date and first_date > day:
                continue
            n += 1
        out[day] = n
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="全池等权全市场基准（流式）")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v3")
    ap.add_argument("--min-members", type=int, default=2)
    ap.add_argument("--limit-stocks", type=int, default=0,
                    help="只处理前 N 只（0 = 全部）。用于快速冒烟。")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    stock_dir = dataset / "stocks"
    t0 = time.time()

    pool = load_pool(dataset)
    calendar = load_calendar(dataset)
    print(f"池内 {len(pool):,} 只；交易日历 {len(calendar):,} 天", flush=True)

    print("计算每日 PIT 成员数 ...", flush=True)
    mcount = member_count_by_day(pool, calendar)
    if mcount:
        sizes = list(mcount.values())
        print(f"  成员数 {min(sizes)}~{max(sizes)}"
              f"（均值 {statistics.mean(sizes):.0f}）", flush=True)

    codes = sorted(p.stem for p in stock_dir.glob("*.csv"))
    if args.limit_stocks:
        codes = codes[:args.limit_stocks]
    print(f"个股 {len(codes):,} 只", flush=True)

    cal_set = set(calendar)
    sums: Dict[str, float] = {}
    traded: Dict[str, int] = {}
    loaded = 0

    for n, code in enumerate(codes, 1):
        path = stock_dir / f"{code}.csv"
        if not path.exists():
            continue
        prev: Optional[float] = None
        try:
            with path.open(encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    try:
                        close = float(row["close"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if close <= 0:
                        continue
                    day = row["date"]
                    if prev is not None and day in cal_set:
                        # 停牌日无 bar → 不进 sums（等价 0 收益），但仍在分母里
                        sums[day] = sums.get(day, 0.0) + (close / prev - 1.0)
                        traded[day] = traded.get(day, 0) + 1
                    prev = close
        except OSError:
            continue
        loaded += 1
        if n % 500 == 0:
            print(f"  已处理 {n:,}/{len(codes):,}（{time.time() - t0:.0f}s）", flush=True)

    if not sums:
        print("无有效数据。", flush=True)
        return 2

    series: Dict[str, float] = {}
    for day, total in sums.items():
        n_members = mcount.get(day, 0)
        if n_members >= args.min_members:
            series[day] = total / n_members

    ds = sorted(series)
    diag = {
        "dates": len(series),
        "members_min": min(mcount[d] for d in ds),
        "members_max": max(mcount[d] for d in ds),
        "members_mean": round(statistics.mean(mcount[d] for d in ds), 2),
        "traded_ratio_mean": round(
            statistics.mean(traded.get(d, 0) / max(1, mcount[d]) for d in ds), 4),
        "universe_coverage": round(
            statistics.mean(mcount[d] / max(1, len(pool)) for d in ds), 4),
        "stocks_loaded": loaded,
        "note": "分母 = 该日 PIT 成员数（含停牌，按 0 收益计入）；"
                "traded_ratio_mean = 有行情成员占比（其余为停牌）",
    }

    print(f"\n等权全市场基准：{diag['dates']:,} 日，"
          f"分母 {diag['members_min']}~{diag['members_max']} 只"
          f"（均值 {diag['members_mean']}）")
    print(f"  有行情成员占比 {diag['traded_ratio_mean']:.1%}，"
          f"载入个股 {loaded:,} 只，用时 {time.time() - t0:.0f}s", flush=True)

    if args.out:
        payload = {
            "series": series,
            "diagnostics": diag,
            "n_stocks_loaded": loaded,
            "source": f"build_equal_weight_benchmark.py --dataset {dataset}（流式全池）",
            "caveat": "日频再平衡、不含成本的理论构造；真实可实现收益更低，"
                      "不得当作可交易基准",
        }
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
        print(f"已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
