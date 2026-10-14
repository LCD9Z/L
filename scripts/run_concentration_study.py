# -*- coding: utf-8 -*-
"""持仓分散度研究：提高分散度能否降低抽样噪声？

## 背景

多股票池重复验证发现：基线策略（持仓 5 只、单仓 25%）在 4 个独立随机抽样上的
年化超额区间为 **[-41.91%, +8.14%]，跨度 50.05pp**。

即**抽样噪声主导结果** —— 策略逻辑的贡献被淹没。
一个具有真实稳健 Alpha 的策略不会因更换随机抽样而变动 50 个百分点。

**推测**：集中度是根因。5 只持仓下，单只股票的极端表现可主导整个组合。

## 本实验要回答

    **提高持仓分散度，能否降低跨抽样的结果离散度？**

这是决定后续实验是否有意义的前提：
若分散后离散度仍大，则继续做策略改进实验无意义。

## 设计

在同一批独立随机抽样（相同种子）上，对比不同集中度：

| 变体 | 持仓数 | 单仓上限 |
|------|-------|---------|
| C5  | 5  | 25.0% |
| C10 | 10 | 10.0% |
| C20 | 20 | 5.0% |
| C30 | 30 | 3.3% |

**策略信号、阈值、持仓周期、成本模型全部保持不变** —— 只改集中度。

关键指标是**离散度**（标准差、区间跨度），而非均值。

用法::

    python run_concentration_study.py --dataset D:/tdx_dataset --seeds 11,22,33
"""
from __future__ import annotations

import argparse
import csv as _csv
import json
import os
import random
import statistics
import sys
import time
from itertools import pairwise
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _study_common import load_codes as _load_codes, pool_codes as _pool_codes  # noqa: E402 — P2 收敛（审计 §3.1 #8/#10）

# (标签, top_n, max_position_pct)
CONCENTRATION_VARIANTS: List[tuple] = [
    ("C5_top5_25pct", 5, 0.250),
    ("C10_top10_10pct", 10, 0.100),
    ("C20_top20_5pct", 20, 0.050),
    ("C30_top30_3pct", 30, 0.033),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="持仓分散度研究")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--sample-size", type=int, default=300)
    ap.add_argument("--seeds", default="11,22,33")
    ap.add_argument("--windows", default="2024-01-02")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=70.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 108)
    print("持仓分散度研究 · 提高分散度能否降低抽样噪声？（信号/阈值/周期/成本全部不变）")
    print("=" * 108)
    t0 = time.time()

    pool = _pool_codes(dataset)
    print(f"完整 PIT 股票池: {len(pool):,} 只")

    from historical_universe import point_in_time_universe
    from portfolio_backtest import portfolio_backtest
    from real_alpha_pipeline import _curve_returns
    from alpha.alpha_survival_lab import (annualized_excess_arithmetic,
                                           excess_t_statistics)
    from research_artifacts import write_final, write_partial  # noqa: E402

    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = json.load(fh)["snapshots"]
    with open(os.path.join(dataset, "benchmark.csv"), encoding="utf-8") as fh:
        bench_all = list(_csv.DictReader(fh))

    def bench_ret_map(w: str) -> Dict[str, float]:
        b = [x for x in bench_all if x["date"] >= w]
        return {c["date"]: float(c["close"]) / float(a["close"]) - 1
                for a, c in pairwise(b) if float(a["close"]) > 0}

    def bench_total(w: str) -> float:
        b = [x for x in bench_all if x["date"] >= w]
        return (float(b[-1]["close"]) / float(b[0]["close"]) - 1) * 100 if b else 0.0

    print(f"\n[1/2] 逐种子 × 逐集中度 × 逐窗口回测"
          f"（{len(seeds)} 种子 × {len(CONCENTRATION_VARIANTS)} 变体 × "
          f"{len(windows)} 窗口）...")

    rows: List[Dict[str, Any]] = []
    for seed in seeds:
        rng = random.Random(seed)
        codes = sorted(rng.sample(pool, min(args.sample_size, len(pool))))
        data = _load_codes(dataset, codes)
        print(f"\n  --- 种子 {seed}（{len(data)} 只）---", flush=True)

        for w in windows:
            oos_dates = sorted({str(b["date"]) for bars in data.values()
                                for b in bars if str(b["date"]) >= w})
            allowed = {d: set(point_in_time_universe(universe, d)) for d in oos_dates}
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
            b_ret = bench_ret_map(w)
            bm = bench_total(w)

            for label, top_n, pos_pct in CONCENTRATION_VARIANTS:
                res = portfolio_backtest(restricted, universe_snapshot_map=universe,
                                         threshold=args.threshold, top_n=top_n,
                                         horizon=args.horizon,
                                         max_position_pct=pos_pct,
                                         start_signal_date=w)
                s_ret = _curve_returns(res.get("equity_curve", []))
                common = sorted(set(s_ret) & set(b_ret))
                # 先物化为列表：既算年化，也算 t/p（统计量必须一并落盘）
                excess = [s_ret[d] - b_ret[d] for d in common]
                exc = annualized_excess_arithmetic(excess, as_percent=True)
                st = excess_t_statistics(excess)
                rows.append({"seed": seed, "window": w, "variant": label,
                             "top_n": top_n, "pos_pct": pos_pct,
                             "n_stocks": len(data), "trades": res.get("trades"),
                             "win_rate_pct": res.get("win_rate_pct"),
                             "total_return_pct": res.get("total_return_pct"),
                             "max_drawdown_pct": res.get("max_drawdown_pct"),
                             "benchmark_return_pct": round(bm, 2),
                             "annualized_excess_pct": round(exc, 2),
                             "t_stat": st["t"], "p_value": st["p"]})
                print(f"    {label:18s} 交易 {res.get('trades'):>4}  "
                      f"胜率 {res.get('win_rate_pct'):>6}  收益 "
                      f"{res.get('total_return_pct'):>9}%  回撤 "
                      f"{res.get('max_drawdown_pct'):>7}%  年化超额 {exc:>+7.2f}%",
                      flush=True)
                # ⚠️ 增量落盘：本实验 12 次回测约 2 小时，而本机后台进程会**静默死亡**。
                # 2026-09-23 实测：跑到第 11 次时进程无报错退出，因只在结尾写一次 JSON，
                # **10 次回测（约 2 小时）的结果全部丢失**。
                # 故每完成一次回测就写 `<out>.partial`；正式 `<out>` 只在全部完成后写，
                # 使部分结果永远可抢救，且不会被误当作完整结果。
                write_partial(args.out,
                              {"rows": rows, "seeds": seeds, "windows": windows,
                               "args": vars(args)},
                              note=f"已完成 {len(rows)}/"
                                   f"{len(seeds) * len(windows) * len(CONCENTRATION_VARIANTS)}"
                                   " 次回测")
        del data

    # ---- 核心：离散度对比 ----
    print("\n" + "=" * 108)
    print("[2/2] 核心指标：跨抽样的离散度（离散度越小 = 结果越可解释）")
    print("=" * 108)

    summary: Dict[str, Any] = {}
    for w in windows:
        print(f"\n  窗口 {w}")
        print(f"    {'变体':20s} {'持仓':>4s} {'单仓':>6s} "
              f"{'超额均值':>9s} {'标准差':>8s} {'区间跨度':>9s} {'最差':>9s} {'最好':>9s}")
        print("    " + "-" * 88)
        for label, top_n, pos_pct in CONCENTRATION_VARIANTS:
            e = [r["annualized_excess_pct"] for r in rows
                 if r["variant"] == label and r["window"] == w]
            if not e:
                continue
            sd = statistics.pstdev(e) if len(e) > 1 else 0.0
            rng_ = max(e) - min(e)
            summary[f"{label}|{w}"] = {"mean": statistics.mean(e), "std": sd,
                                       "range": rng_, "values": e,
                                       "top_n": top_n, "pos_pct": pos_pct}
            print(f"    {label:20s} {top_n:>4} {pos_pct*100:>5.1f}% "
                  f"{statistics.mean(e):>+9.2f} {sd:>8.2f} {rng_:>9.2f} "
                  f"{min(e):>+9.2f} {max(e):>+9.2f}")

    # ---- 离散度是否随分散度下降 ----
    print("\n" + "-" * 108)
    print("  结论判定：离散度是否随分散度单调下降？")
    print("-" * 108)
    for w in windows:
        sds = [summary.get(f"{lab}|{w}", {}).get("std") for lab, _, _ in CONCENTRATION_VARIANTS]
        sds = [x for x in sds if x is not None]
        if len(sds) >= 2:
            decreasing = all(sds[k] >= sds[k + 1] for k in range(len(sds) - 1))
            base, last = sds[0], sds[-1]
            ratio = (last / base) if base > 0 else float("nan")
            print(f"    {w}: 标准差序列 {[round(x,2) for x in sds]}")
            print(f"      单调下降: {'是' if decreasing else '否'}   "
                  f"最分散/最集中 = {ratio:.2f}")

    print()
    print("声明：本实验只改集中度，信号/阈值/周期/成本全部不变。")
    print("      数据缺陷以数据集 evidence.json 为准"
          "（v3 已消除幸存者偏差与不复权两项），结果不构成投资结论。")

    print("      数据存在幸存者偏差与不复权两项缺陷，结果不构成投资结论。")

    if args.out:
        # 2026-10-14 A2 合并：主干侧原为裸 json.dump 结尾（含 10-06 增补的
        # 「生效基准路径」benchmark 字段）；本侧纪律是 write_final（原子写）。
        # 合并 = write_final 落盘 + 保留 benchmark 字段（基准口径留痕）。
        write_final(args.out, {"rows": rows, "summary": summary, "seeds": seeds,
                               "windows": windows, "args": vars(args),
                               # 基准在本脚本中**硬编码**为 benchmark.csv 即沪深300
                               # （2026-10-06 增补记录，否则事后无从判断口径）
                               "benchmark": os.path.join(dataset, "benchmark.csv")})
        print(f"\n结果已写入: {args.out}")
    print(f"总耗时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
