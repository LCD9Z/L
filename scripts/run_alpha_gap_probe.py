# -*- coding: utf-8 -*-
r"""Alpha 能力缺口探查：基准错配与因子冗余的实测。

只读脚本，不修改任何数据。产出两项在 `ALPHA_CAPABILITY_GAP_ANALYSIS.md`
§3 中引用的实测结果：

**A. 基准错配** —— 构造 v2 认证池的**日频等权全市场**收益序列，
与数据集自带的沪深300 对比。项目此前的超额一律以沪深300 为基准，
而策略池是全市场抽样；若两者差距显著，则沪深300 会系统性高估策略超额。

**B. 因子冗余** —— 计算复合五因子在每个横截面内的 Spearman 秩相关，
再对截面取均值。秩相关接近 ±1 的因子对在等权合成时**重复计票**。

用法::

    python scripts/run_alpha_gap_probe.py --dataset D:/tdx_dataset_v2 --n-stocks 800

口径声明（引用结果时必须一并说明）：

* 等权序列为**日频再平衡、不含交易成本**的理论构造，真实可实现收益更低；
* 等权序列基于 ``--n-stocks`` 只抽样，是 PIT 池的**子集**，非完整全市场；
* 因子相关在**秩空间**计算（与 IC 检验口径一致），不是 Pearson 相关。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.factor_ic_lab import COMPOSITE_FACTORS  # noqa: E402
from validation.benchmark import (  # noqa: E402
    equal_weight_diagnostics,
    equal_weight_returns,
)

WINDOWS = [
    ("2024-01-02", "2026-09-10"),
    ("2023-07-03", "2026-09-10"),
    ("2025-01-02", "2026-09-10"),
    ("2021-08-02", "2026-09-10"),
]
SAMPLE_STEP = 5
MIN_HISTORY = 21


def load_bars(path: Path) -> Optional[List[Tuple[str, float, float]]]:
    """读个股 CSV → [(date, close, amount)]；无效行跳过，不补造。"""
    if not path.exists():
        return None
    out: List[Tuple[str, float, float]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                close = float(row["close"])
                amount = float(row["amount"] or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if close > 0:
                out.append((row["date"], close, amount))
    return out or None


def load_universe(dataset: Path) -> Dict[str, List[str]]:
    """读**完整** PIT 快照（不过滤）。

    必须传完整池给 `equal_weight_returns` / `equal_weight_diagnostics`：

    * 前者内部会跳过"数据未覆盖"的成员（不计入分母），故传完整池与传过滤池
      **收益率完全相同**；
    * 但后者的**覆盖率**必须相对完整池计算 —— 若先按已加载代码过滤，
      覆盖率会恒等于 100%（平凡真值），从而把"抽样只有三成覆盖"报成"全覆盖"。
    """
    raw = json.loads((dataset / "pit_universe.json").read_text(encoding="utf-8"))
    return raw["snapshots"]


def load_benchmark(dataset: Path) -> Dict[str, float]:
    out: Dict[str, float] = {}
    with (dataset / "benchmark.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["date"]] = float(row["close"])
    return out


def load_pool(dataset: Path, n_stocks: int) -> List[str]:
    codes: List[str] = []
    with (dataset / "pool_v2.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            codes.append(row["code"])
    return codes[:n_stocks]


def cumulative(curve: Dict[str, float], start: str, end: str) -> Optional[float]:
    pts = [(d, v) for d, v in sorted(curve.items()) if start <= d <= end]
    if len(pts) < 2:
        return None
    return pts[-1][1] / pts[0][1] - 1.0


def to_curve(returns: Dict[str, float]) -> Dict[str, float]:
    """日收益 → 累计净值曲线。"""
    out: Dict[str, float] = {}
    g = 1.0
    for d in sorted(returns):
        g *= 1.0 + returns[d]
        out[d] = g
    return out


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 10:
        return None

    def rank(v: Sequence[float]) -> List[float]:
        order = sorted(range(n), key=lambda k: v[k])
        rk = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk

    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else None


def factor_values(bars: Sequence[Tuple[str, float, float]], k: int) -> Optional[Dict[str, float]]:
    """在第 k 根 K 线上计算复合五因子（只用 k 及之前的数据）。"""
    if k < MIN_HISTORY:
        return None
    window = bars[k - 20:k + 1]
    closes = [w[1] for w in window]
    if any(c <= 0 for c in closes):
        return None
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    amounts = [w[2] for w in window]
    avg_amt = sum(amounts) / len(amounts)
    if avg_amt <= 0 or not rets:
        return None
    amihud = [abs(rets[i]) / amounts[i + 1] for i in range(len(rets)) if amounts[i + 1] > 0]
    if not amihud:
        return None
    return {
        "ret_20": closes[-1] / closes[-21] - 1.0,
        "vol_20": statistics.pstdev(rets) if len(rets) > 1 else 0.0,
        "amihud_20": sum(amihud) / len(amihud) * 1e8,
        "log_amount_20": math.log(avg_amt),
        "max_ret_20": max(rets),
    }


def probe_benchmark(data: Dict[str, List[Tuple[str, float, float]]],
                    universe: Dict[str, List[str]],
                    benchmark: Dict[str, float]) -> Dict[str, Any]:
    bars_by_code = {c: [{"date": d, "close": cl} for d, cl, _ in bars]
                    for c, bars in data.items()}
    cal = sorted(benchmark)
    ew_ret = equal_weight_returns(bars_by_code, universe, dates=cal)
    diag = equal_weight_diagnostics(bars_by_code, universe, dates=cal)
    ew_curve = to_curve(ew_ret)
    base = benchmark[cal[0]]
    hs_curve = {d: benchmark[d] / base for d in cal}

    rows = []
    for start, end in WINDOWS:
        ew = cumulative(ew_curve, start, end)
        hs = cumulative(hs_curve, start, end)
        if ew is None or hs is None:
            continue
        rows.append({"start": start, "end": end, "ew_pct": ew * 100,
                     "hs300_pct": hs * 100, "diff_pp": (ew - hs) * 100})

    per_stock = []
    for bars in data.values():
        seg = [b for b in bars if "2024-01-02" <= b[0] <= "2026-09-10"]
        if len(seg) > 100:
            per_stock.append(seg[-1][1] / seg[0][1] - 1.0)
    stock_stats: Dict[str, Any] = {"n": len(per_stock)}
    if per_stock:
        per_stock.sort()
        n = len(per_stock)
        stock_stats.update({
            "median_pct": per_stock[n // 2] * 100,
            "mean_pct": statistics.mean(per_stock) * 100,
            "positive_share": sum(1 for x in per_stock if x > 0) / n,
        })
    return {"windows": rows, "diagnostics": diag, "stocks_2024_2026": stock_stats,
            "returns": ew_ret}


def probe_factor_redundancy(data: Dict[str, List[Tuple[str, float, float]]]) -> Dict[str, Any]:
    names = list(COMPOSITE_FACTORS)
    pairs = [(names[i], names[j]) for i in range(len(names)) for j in range(i + 1, len(names))]
    by_day: Dict[Tuple[str, str], Tuple[List[float], List[float]]] = {}

    all_dates = sorted({d for bars in data.values() for d, _, _ in bars})
    sample_dates = set(all_dates[::SAMPLE_STEP])

    for bars in data.values():
        for k in range(MIN_HISTORY, len(bars)):
            day = bars[k][0]
            if day not in sample_dates:
                continue
            fac = factor_values(bars, k)
            if fac is None:
                continue
            for a, b in pairs:
                pair_key = f"{a}~{b}"
                cur = by_day.setdefault((pair_key, day), ([], []))
                cur[0].append(fac[a])
                cur[1].append(fac[b])

    acc: Dict[str, List[float]] = {f"{a}~{b}": [] for a, b in pairs}
    for (pair_key, _day), (xs, ys) in by_day.items():
        rho = spearman(xs, ys)
        if rho is not None:
            acc[pair_key].append(rho)

    out: Dict[str, Any] = {}
    for pair_key, vals in acc.items():
        if not vals:
            out[pair_key] = {"mean_rho": None, "abs_gt_0_5_rate": None, "n_cross_sections": 0}
            continue
        out[pair_key] = {
            "mean_rho": statistics.mean(vals),
            "abs_gt_0_5_rate": sum(1 for v in vals if abs(v) > 0.5) / len(vals),
            "n_cross_sections": len(vals),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Alpha 能力缺口探查（只读）")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v2")
    ap.add_argument("--n-stocks", type=int, default=800)
    ap.add_argument("--out", default="")
    ap.add_argument("--skip-factors", action="store_true",
                    help="只做基准部分（B 部分因子相关较慢，用于快速复算覆盖率）")
    ap.add_argument("--out-series", default="",
                    help="把等权全市场**日收益序列**另存为 JSON，供 "
                         "run_tdx_rolling_eval.py --ew-series 复用 —— "
                         "使基准覆盖完整池，而不是回测的抽样池")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    codes = load_pool(dataset, args.n_stocks)
    print(f"池内股票 {len(codes)} 只（抽样，非完整全市场）", flush=True)

    data: Dict[str, List[Tuple[str, float, float]]] = {}
    for i, code in enumerate(codes):
        bars = load_bars(dataset / "stocks" / f"{code}.csv")
        if bars and len(bars) >= 120:
            data[code] = bars
        if (i + 1) % 200 == 0:
            print(f"  已载入 {i + 1}/{len(codes)}", flush=True)

    universe = load_universe(dataset)
    benchmark = load_benchmark(dataset)

    print("\n=== A. 基准错配：等权全市场 vs 沪深300 ===")
    a = probe_benchmark(data, universe, benchmark)
    d = a["diagnostics"]
    print(f"等权基准：{d['dates']:,} 日，成员 {d['members_min']}~{d['members_max']} 只"
          f"（均值 {d['members_mean']}），PIT 覆盖度 {d['universe_coverage']:.1%}")
    print(f"{'窗口':<26}{'等权全市场':>12}{'沪深300':>12}{'差(pp)':>10}")
    for r in a["windows"]:
        print(f"{r['start'] + '~' + r['end']:<26}{r['ew_pct']:>11.2f}%"
              f"{r['hs300_pct']:>11.2f}%{r['diff_pp']:>9.2f}")
    s = a["stocks_2024_2026"]
    if s.get("n"):
        print(f"\n个股 2024-01-02~2026-09-10 累计收益：中位 {s['median_pct']:.2f}%"
              f" · 均值 {s['mean_pct']:.2f}% · 正收益占比 {s['positive_share']:.1%}（{s['n']} 只）")

    b: Dict[str, Any] = {}
    if args.skip_factors:
        print("\n（--skip-factors：跳过 B 部分）")
    else:
        print("\n=== B. 复合五因子横截面秩相关（每 5 日采样）===")
        b = probe_factor_redundancy(data)
    if b:
        print(f"{'因子对':<26}{'平均秩相关':>12}{'|r|>0.5 截面占比':>18}{'截面数':>8}")
        for key, v in sorted(b.items(), key=lambda kv: -abs(kv[1]["mean_rho"] or 0)):
            if v["mean_rho"] is None:
                print(f"{key:<26}{'n/a':>12}")
                continue
            print(f"{key:<26}{v['mean_rho']:>12.3f}{v['abs_gt_0_5_rate']:>17.1%}"
                  f"{v['n_cross_sections']:>8}")

    print("\n口径声明：等权序列为日频再平衡、不含成本的理论构造，且基于抽样（非完整全市场）；")
    print("          因子相关在秩空间计算。引用数字时必须一并声明以上限定。")

    if args.out_series:
        series_payload = {
            "series": a["returns"],
            "diagnostics": d,
            "n_stocks_loaded": len(data),
            "source": f"run_alpha_gap_probe.py --dataset {dataset} "
                      f"--n-stocks {args.n_stocks}",
            "caveat": "日频再平衡、不含成本的理论构造；真实可实现收益更低，"
                      "不得当作可交易基准",
        }
        Path(args.out_series).write_text(
            json.dumps(series_payload, ensure_ascii=False), encoding="utf-8",
            newline="\n")
        print(f"等权序列已写入: {args.out_series}（{len(a['returns']):,} 日，"
              f"覆盖度 {d['universe_coverage']:.1%}）")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"benchmark": a, "factor_redundancy": b, "args": vars(args)},
                      f, ensure_ascii=False, indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
