# -*- coding: utf-8 -*-
"""多股票池独立重复验证：V0（基线）vs V1（剔除 ret_20 尾部）是否可复现。

## 为什么需要这个

上一轮实验发现：**股票池构成足以让结论翻转**（某变体的超额从 +4.04pp 变成 -4.32pp）。
而"V1 优于 V0"当时只基于 2 个股票池，其中一个是污染的。

本脚本用**多个独立随机抽样**重复该对比，回答：

    V1 相对 V0 的改善，是稳定特征，还是某个特定抽样的产物？

## 设计要点

1. **分位数阈值在完整 PIT 池上定义**，而非在测试样本内定义。
   真实投资中"最高 20%"应对应可投资全域，样本内定义会让阈值随抽样漂移。
2. **多个随机种子**独立抽样，每个种子一个完整对照实验（含 V0 对照组）。
3. 报告**每个种子的结果**，而非只报平均 —— 要看一致性，不是看均值。

用法::

    python run_universe_replication.py --dataset D:/tdx_dataset --seeds 1,2,3
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from itertools import pairwise
from typing import Any, Dict, List, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.factor_ic_lab import MIN_HISTORY, compute_factors  # noqa: E402
from alpha.alpha_survival_lab import annualized_excess_arithmetic  # noqa: E402

VARIANTS: Dict[str, List[str]] = {
    "V0_baseline": [],
    "V1_excl_ret20_top20": ["ret_20"],
}


def _pool_codes(dataset: str) -> List[str]:
    """完整 PIT 股票池中实际有文件的代码。"""
    d = os.path.join(dataset, "stocks")
    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as f:
        snaps = json.load(f)["snapshots"]
    pool = set()
    for v in snaps.values():
        pool.update(v)
    return sorted(c for c in pool
                  if os.path.exists(os.path.join(d, f"{c}.csv"))
                  and os.path.exists(os.path.join(d, f"{c}.metadata.json")))


def _load_codes(dataset: str, codes: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    from real_alpha_pipeline import load_certified_csv
    d = os.path.join(dataset, "stocks")
    out: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p, m = os.path.join(d, f"{c}.csv"), os.path.join(d, f"{c}.metadata.json")
        if os.path.exists(p) and os.path.exists(m):
            out[c] = load_certified_csv(p, m)
    return out


def _exclusion_on_pool(data: Dict[str, List[Dict[str, Any]]],
                       factors: Sequence[str], top_frac: float,
                       min_cross_section: int = 100) -> Dict[str, Dict[str, set]]:
    """在给定（完整）股票池上计算各因子的最高分位集合。"""
    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    dates: set = set()
    for bars in data.values():
        dates.update(str(b["date"]) for b in bars if b.get("date"))
    out: Dict[str, Dict[str, set]] = {f: {} for f in factors}
    for day in sorted(dates):
        vals: Dict[str, List[tuple]] = {f: [] for f in factors}
        for code, bars in data.items():
            i = idx_map[code].get(day)
            if i is None or i < MIN_HISTORY:
                continue
            fac = compute_factors(bars, i)
            if fac is None:
                continue
            for f in factors:
                vals[f].append((code, fac[f]))
        for f in factors:
            pairs = vals[f]
            if len(pairs) < min_cross_section:
                continue
            pairs.sort(key=lambda t: t[1])
            cut = int(len(pairs) * (1 - top_frac))
            out[f][day] = {c for c, _ in pairs[cut:]}
    return out


def _make_filter(excl: Dict[str, Dict[str, set]], factors: Sequence[str]):
    if not factors:
        return None

    def flt(code: str, hist: List[Dict[str, Any]], day: str) -> bool:
        return all(code not in excl.get(f, {}).get(day, ()) for f in factors)

    return flt


def main() -> int:
    ap = argparse.ArgumentParser(description="多股票池独立重复验证")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--sample-size", type=int, default=200,
                    help="每个种子的抽样股票数")
    ap.add_argument("--seeds", default="11,22,33",
                    help="独立抽样种子（逗号分隔）")
    ap.add_argument("--windows", default="2024-01-02,2024-07-01")
    ap.add_argument("--top-frac", type=float, default=0.20)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--top-n", type=int, default=5,
                    help="持仓数（默认 5=原基线配置；建议改为 20 以避免抽样噪声主导）")
    ap.add_argument("--pos-pct", type=float, default=0.25,
                    help="单仓上限（默认 0.25；与 --top-n 配套，如 20 只配 0.05）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 104)
    print("多股票池独立重复验证 · V0（基线）vs V1（剔除 ret_20 最高 20%）")
    print("=" * 104)
    t0 = time.time()

    pool = _pool_codes(dataset)
    print(f"完整 PIT 股票池: {len(pool):,} 只")

    # ---- 关键：分位数阈值在完整池上定义，与测试样本无关 ----
    print(f"\n[1/3] 在完整池上计算剔除集合（{args.top_frac:.0%} 分位）...")
    pool_data = _load_codes(dataset, pool)
    excl = _exclusion_on_pool(pool_data, ["ret_20"], args.top_frac)
    days = len(excl["ret_20"])
    avg = (sum(len(v) for v in excl["ret_20"].values()) / days) if days else 0
    print(f"      覆盖 {days} 个交易日，日均剔除 {avg:.0f} 只  ({time.time()-t0:.0f}s)")
    del pool_data

    from historical_universe import point_in_time_universe
    from portfolio_backtest import portfolio_backtest
    from real_alpha_pipeline import _curve_returns

    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = json.load(fh)["snapshots"]
    import csv as _csv
    with open(os.path.join(dataset, "benchmark.csv"), encoding="utf-8") as fh:
        bench_all = list(_csv.DictReader(fh))

    def bench_ret_map(w: str) -> Dict[str, float]:
        b = [x for x in bench_all if x["date"] >= w]
        out: Dict[str, float] = {}
        for a, c in pairwise(b):
            if float(a["close"]) > 0:
                out[c["date"]] = float(c["close"]) / float(a["close"]) - 1
        return out

    def bench_total(w: str) -> float:
        b = [x for x in bench_all if x["date"] >= w]
        return (float(b[-1]["close"]) / float(b[0]["close"]) - 1) * 100 if b else 0.0

    print(f"\n[2/3] 逐种子 × 逐变体 × 逐窗口回测（{len(seeds)} 种子 × "
          f"{len(windows)} 窗口 × {len(VARIANTS)} 变体）...")
    rows: List[Dict[str, Any]] = []
    for seed in seeds:
        rng = random.Random(seed)
        codes = sorted(rng.sample(pool, min(args.sample_size, len(pool))))
        data = _load_codes(dataset, codes)
        print(f"\n  --- 种子 {seed}（{len(data)} 只）---", flush=True)
        for vname, facs in VARIANTS.items():
            flt = _make_filter(excl, facs)
            for w in windows:
                oos_dates = sorted({str(b["date"]) for bars in data.values()
                                    for b in bars if str(b["date"]) >= w})
                allowed = {d: set(point_in_time_universe(universe, d))
                           for d in oos_dates}
                restricted: Dict[str, List[dict]] = {}
                for code, bars in data.items():
                    kept, ever = [], False
                    for b in bars:
                        d = str(b["date"])
                        if d >= w and code not in allowed.get(d, set()):
                            continue
                        kept.append(b)
                        if d >= w:
                            ever = True
                    if ever:
                        restricted[code] = kept
                res = portfolio_backtest(restricted, universe_snapshot_map=universe,
                                         threshold=70, top_n=5, horizon=args.horizon,
                                         start_signal_date=w, candidate_filter=flt)
                s_ret = _curve_returns(res.get("equity_curve", []))
                b_ret = bench_ret_map(w)
                common = sorted(set(s_ret) & set(b_ret))
                exc = annualized_excess_arithmetic(
                    (s_ret[d] - b_ret[d] for d in common), as_percent=True)
                rows.append({"seed": seed, "variant": vname, "window": w,
                             "n_stocks": len(data), "trades": res.get("trades"),
                             "win_rate_pct": res.get("win_rate_pct"),
                             "total_return_pct": res.get("total_return_pct"),
                             "max_drawdown_pct": res.get("max_drawdown_pct"),
                             "benchmark_return_pct": round(bench_total(w), 2),
                             "annualized_excess_pct": round(exc, 2)})
                print(f"    {vname:24s} {w}  交易 {res.get('trades'):>4}  "
                      f"胜率 {res.get('win_rate_pct'):>6}  收益 "
                      f"{res.get('total_return_pct'):>8}%  回撤 "
                      f"{res.get('max_drawdown_pct'):>7}%  年化超额 {exc:>+7.2f}%",
                      flush=True)
        del data

    # ---- 汇总：看一致性，不看均值 ----
    print("\n" + "=" * 104)
    print("汇总：逐种子对比（年化超额，净收益口径）")
    print("=" * 104)
    print(f"{'种子':>6s} {'窗口':12s} {'V0 超额':>10s} {'V1 超额':>10s} "
          f"{'改善':>9s} {'V1 回撤':>9s} {'V0 回撤':>9s} {'回撤改善':>9s}")
    print("-" * 104)
    improvements: List[float] = []
    dd_improvements: List[float] = []
    for seed in seeds:
        for w in windows:
            g = {r["variant"]: r for r in rows
                 if r["seed"] == seed and r["window"] == w}
            if len(g) < 2:
                continue
            e0 = g["V0_baseline"]["annualized_excess_pct"]
            e1 = g["V1_excl_ret20_top20"]["annualized_excess_pct"]
            d0 = g["V0_baseline"]["max_drawdown_pct"]
            d1 = g["V1_excl_ret20_top20"]["max_drawdown_pct"]
            improvements.append(e1 - e0)
            dd_improvements.append(d1 - d0)
            print(f"{seed:>6} {w:12s} {e0:>+10.2f} {e1:>+10.2f} "
                  f"{e1-e0:>+9.2f} {d1:>9.2f} {d0:>9.2f} {d1-d0:>+9.2f}")

    n = len(improvements)
    print()
    print("-" * 104)
    if n:
        n_pos = sum(1 for x in improvements if x > 0)
        n_dd = sum(1 for x in dd_improvements if x < 0)
        print(f"  有效对照数            : {n}")
        print(f"  超额改善为正的组数    : {n_pos} / {n}")
        print(f"  超额改善 均值/中位数  : {statistics.mean(improvements):+.2f} / "
              f"{statistics.median(improvements):+.2f} pp")
        print(f"  超额改善 区间         : [{min(improvements):+.2f}, "
              f"{max(improvements):+.2f}] pp")
        print(f"  回撤下降的组数        : {n_dd} / {n}")
        print(f"  回撤改善 均值         : {statistics.mean(dd_improvements):+.2f} pp")
        print()
        if n_pos == n and n_dd == n:
            print("  结论：V1 在所有独立抽样上均改善超额与回撤 → 可复现")
        elif n_pos > n / 2 and n_dd == n:
            print("  结论：回撤改善可复现；超额改善方向多数一致但非全部")
        else:
            print("  结论：改善**不可复现**，不应采信")

    print()
    print("声明：本验证未扫参数；分位数阈值在完整 PIT 池上定义。")
    print("      数据存在幸存者偏差与不复权两项缺陷，结果不构成投资结论。")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"rows": rows, "seeds": seeds, "windows": windows,
                       "args": vars(args)}, fh, ensure_ascii=False,
                      indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    print(f"总耗时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
