# -*- coding: utf-8 -*-
"""采样敏感性研究：提高持仓分散度能否让回测结论稳定下来？

## 背景

排查发现：同一窗口、同一策略，仅因股票采样数不同（400 vs 800），
基线收益从 **-83.06%** 变到 **-28.34%** —— **差 54.72pp**。

原因：策略是 `top_n=5` 的**高度集中**组合，采样一变 Top5 完全换人。
后果：所有回测结论的**绝对幅度**都不可引用。

## 本实验要回答

**提高持仓数（top_n）能否降低"采样敏感性"？**

设计：固定一个较大的候选池，从中抽多个**独立子样本**，
对每个 `top_n` 测出结果分布，看**离散度是否随 top_n 单调下降**。

- 若下降 → 分散化是解法，应先改造持仓结构再评估
- 若不下降 → 问题不在集中度，需另找根因

## 设计要点

* **只改 `top_n` 与 `max_position_pct`**，信号/阈值/周期/成本全部不变
* 子样本用**带种子的确定性洗牌** —— 可复现且样本真正互不相同
* `max_position_pct = 1/top_n` —— 等权满仓，使各 top_n 可比

用法::

    python scripts/run_sampling_sensitivity_study.py --dataset D:/tdx_dataset
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from itertools import pairwise
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _take_sample(codes: List[str], size: int, seed: int) -> List[str]:
    """从 codes 中确定性抽 size 只。

    **不要用"等距抽样 + 偏移量"** —— 实测该做法会退化为同一集合：
    当 ``len(codes)/size`` 与偏移量成整数倍关系时（如 1000 只抽 300 只、
    偏移 200/400/600/800），所有"不同偏移"抽出的都是**同一批股票**，
    于是离散度恒为 0 —— 一个看起来完美、实际完全错误的结论。

    这里改用**带种子的确定性洗牌**：既保证可复现，又保证样本真正不同。
    """
    if size >= len(codes):
        return list(codes)
    import random
    rng = random.Random(seed)
    picked = list(codes)
    rng.shuffle(picked)
    return sorted(picked[:size])


def main() -> int:
    ap = argparse.ArgumentParser(description="采样敏感性 × 持仓分散度")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--pool-size", type=int, default=1000,
                    help="候选池大小（加载一次后复用）")
    ap.add_argument("--sample-size", type=int, default=300, help="每个子样本的股票数")
    ap.add_argument("--n-samples", type=int, default=5, help="子样本个数")
    ap.add_argument("--seed-base", type=int, default=1000,
                    help="子样本洗牌种子起点（确定性可复现）")
    ap.add_argument("--top-ns", default="5,10,20,30")
    ap.add_argument("--window", default="2024-01-02")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=70.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    top_ns = [int(x) for x in args.top_ns.split(",") if x.strip()]

    print("=" * 100)
    print("采样敏感性 × 持仓分散度 · 提高 top_n 能否让结论稳定？")
    print("=" * 100)
    print(f"  窗口 {args.window} · 候选池 {args.pool_size} · "
          f"子样本 {args.n_samples}×{args.sample_size} · top_n {top_ns}")
    t0 = time.time()

    # ---- 加载 ----
    from historical_universe import point_in_time_universe
    from portfolio_backtest import portfolio_backtest
    from real_alpha_pipeline import _curve_returns, load_certified_csv
    from alpha.alpha_survival_lab import annualized_excess_arithmetic

    stock_dir = os.path.join(dataset, "stocks")
    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = json.load(fh)["snapshots"]
    pool_codes: set = set()
    for v in universe.values():
        pool_codes.update(v)
    codes = sorted(c for c in pool_codes
                   if os.path.exists(os.path.join(stock_dir, f"{c}.csv"))
                   and os.path.exists(os.path.join(stock_dir, f"{c}.metadata.json")))
    if args.pool_size > 0 and len(codes) > args.pool_size:
        step = len(codes) / args.pool_size
        codes = [codes[int(i * step)] for i in range(args.pool_size)]
    print(f"\n[1/3] 加载候选池 {len(codes)} 只 ...")
    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        data[c] = load_certified_csv(os.path.join(stock_dir, f"{c}.csv"),
                                     os.path.join(stock_dir, f"{c}.metadata.json"))
    print(f"      完成 ({time.time()-t0:.0f}s)")

    # 基准
    import csv as _csv
    with open(os.path.join(dataset, "benchmark.csv"), encoding="utf-8") as fh:
        bench = list(_csv.DictReader(fh))
    w = args.window
    bench_oos = [b for b in bench if str(b["date"]) >= w]
    b_ret: Dict[str, float] = {}
    for a, b in pairwise(bench_oos):
        if float(a["close"]) > 0:
            b_ret[str(b["date"])] = float(b["close"]) / float(a["close"]) - 1

    print("\n[2/3] 逐 top_n × 逐子样本回测 ...")
    results: Dict[int, List[Dict[str, Any]]] = {n: [] for n in top_ns}
    total = len(top_ns) * args.n_samples
    done = 0
    for top_n in top_ns:
        for s in range(args.n_samples):
            seed = args.seed_base + s
            sub = _take_sample(codes, args.sample_size, seed)
            restricted = {}
            oos_dates = sorted({str(b["date"]) for c in sub for b in data[c]
                                if str(b["date"]) >= w})
            allowed = {d: set(point_in_time_universe(universe, d)) for d in oos_dates}
            for c in sub:
                kept, ever = [], False
                for b in data[c]:
                    d = str(b["date"])
                    if d >= w and c not in allowed.get(d, set()):
                        continue
                    kept.append(b)
                    if d >= w:
                        ever = True
                if ever:
                    restricted[c] = kept
            res = portfolio_backtest(
                restricted, universe_snapshot_map=universe,
                threshold=args.threshold, top_n=top_n, horizon=args.horizon,
                start_signal_date=w, max_position_pct=1.0 / top_n)
            s_ret = _curve_returns(res.get("equity_curve", []))
            common = sorted(set(s_ret) & set(b_ret))
            exc = annualized_excess_arithmetic(
                (s_ret[d] - b_ret[d] for d in common), as_percent=True)
            results[top_n].append({
                "sample": s, "assets": len(restricted),
                "total_return_pct": res.get("total_return_pct"),
                "trades": res.get("trades"),
                "max_drawdown_pct": res.get("max_drawdown_pct"),
                "annualized_excess_pct": round(exc, 2)})
            done += 1
            print(f"      [{done}/{total}] top_n={top_n:>2} 样本{s}  "
                  f"标的{len(restricted):>4}  收益 {res.get('total_return_pct'):>9}%  "
                  f"年化超额 {exc:>+7.2f}%  ({time.time()-t0:.0f}s)", flush=True)

    # ---- 汇总 ----
    print("\n" + "=" * 100)
    print("核心指标：同一 top_n 下跨子样本的离散度（越小 = 结论越稳定）")
    print("=" * 100)
    print(f"{'top_n':>6} {'单仓上限':>9} {'年化超额均值':>13} {'标准差':>9} "
          f"{'区间跨度':>10} {'最差':>9} {'最好':>9}")
    print("-" * 100)
    summary = []
    for top_n in top_ns:
        e = [r["annualized_excess_pct"] for r in results[top_n]]
        if not e:
            continue
        sd = statistics.pstdev(e) if len(e) > 1 else 0.0
        row = {"top_n": top_n, "max_position_pct": round(1.0 / top_n, 4),
               "mean": round(statistics.mean(e), 2), "std": round(sd, 2),
               "range": round(max(e) - min(e), 2),
               "min": min(e), "max": max(e), "n": len(e)}
        summary.append(row)
        print(f"{top_n:>6} {1.0/top_n:>8.1%} {row['mean']:>+13.2f} {sd:>9.2f} "
              f"{row['range']:>10.2f} {row['min']:>+9.2f} {row['max']:>+9.2f}")

    print("\n" + "-" * 100)
    print("关键检验：离散度是否随 top_n 单调下降？")
    print("-" * 100)
    sds = [r["std"] for r in summary]
    print(f"  标准差序列: {sds}")
    mono = all(sds[i] >= sds[i + 1] for i in range(len(sds) - 1))
    if len(sds) >= 2 and sds[0] > 0:
        print(f"  最分散/最集中 = {sds[-1]/sds[0]:.2f}")
    print(f"  单调下降: {'是' if mono else '否'}")
    if mono:
        print("\n  结论：**提高持仓数确实降低采样敏感性** → 分散化是解法，")
        print("        应先改造持仓结构再评估策略。")
    else:
        print("\n  结论：提高持仓数**未**使离散度单调下降 → 集中度不是唯一根因。")

    print()
    print("声明：本实验只改 top_n 与单仓上限，信号/阈值/周期/成本全部不变。")
    print("      数据含第三方来源的退市股（成交额为近似值），结果不构成投资结论。")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"summary": summary, "detail": results, "args": vars(args),
                       # 基准在本脚本中**硬编码**为 benchmark.csv 即沪深300
                       # （2026-10-06 增补记录）
                       "benchmark": os.path.join(dataset, "benchmark.csv")},
                      fh, ensure_ascii=False, indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    print(f"总耗时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
