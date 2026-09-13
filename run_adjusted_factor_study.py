# -*- coding: utf-8 -*-
"""复权价格 vs 原始价格的因子对比研究。

## 要回答的问题

此前在**未复权**价格上测得动量因子显著为负（5 日 IC=-0.030、20 日 IC=-0.055），
并据此判断"基线策略买在负 IC 因子尾部"。

但未复权价含**除权跳空**。实测茅台 2024-06-19 除权日：
原始价显示 -1.35%，复权后实际是 **+0.70%** —— 一次上涨被记成了下跌。

**预测**：这类假下跌会被反转因子当成"超跌"信号，
而这些股票随后会**机械性回补**（除权是技术性的，不是真实亏损），
从而**人为放大反转效应**。因此：

    复权后，反转/动量因子的 IC 绝对值应当**下降**。

本脚本直接检验该预测。

## 设计

同一批股票、同一套因子、同一调仓规则，只改一件事：
**用复权价代替原始价**。然后对比 IC。

用法::

    python run_adjusted_factor_study.py --dataset D:/tdx_dataset
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factor_ic_lab import (  # noqa: E402
    FACTOR_LABELS,
    quintile_returns,
    run_ic_study,
)

OHLC = ("open", "high", "low", "close")


def load_actions(path: str) -> Dict[str, List[Any]]:
    """读入公司行动 CSV，按股票代码分组为 CorporateAction 列表。"""
    from corporate_action_provider import normalize_tushare_dividend
    out: Dict[str, List[Any]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            a = normalize_tushare_dividend(row)
            if a is None:
                continue
            out.setdefault(a.normalized_code(), []).append(a)
    return out


def adjust_bars(bars: List[Dict[str, Any]], actions: List[Any]) -> List[Dict[str, Any]]:
    """把 OHLC 全部乘以后复权因子。

    `build_back_adjustment_factors` 只处理 close；这里把同一因子应用到
    open/high/low，保证 OHLC 内部一致（否则 high/low 与 close 会失配，
    污染依赖区间位置的因子）。
    """
    from corporate_actions import build_back_adjustment_factors
    if not actions:
        return bars
    tagged = build_back_adjustment_factors(bars, actions)
    out: List[Dict[str, Any]] = []
    for r in tagged:
        f = float(r.get("back_adjustment_factor", 1.0))
        if f == 1.0:
            out.append(dict(r))
            continue
        item = dict(r)
        for k in OHLC:
            v = r.get(k)
            if v not in (None, ""):
                item[k] = float(v) * f
        out.append(item)
    return out


def _verdict(f: Dict[str, Any]) -> str:
    if "error" in f:
        return "证据不足"
    ic, t, prior = f["ic_mean"], f["t"], f["prior_sign"]
    if prior == 0:
        return "方向待定"
    consistent = (ic > 0) if prior > 0 else (ic < 0)
    if not consistent:
        return "与先验相反"
    return "支持（强）" if abs(t) >= 2 else "方向一致（弱）"


def main() -> int:
    ap = argparse.ArgumentParser(description="复权 vs 原始 因子对比")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--actions", default="",
                    help="公司行动 CSV（默认 {dataset}/corporate_actions.csv）")
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    actions_path = args.actions or os.path.join(dataset, "corporate_actions.csv")
    if not os.path.exists(actions_path):
        print(f"!! 缺少公司行动数据: {actions_path}")
        print("   请先运行: python fetch_corporate_actions.py --out <路径>")
        return 2

    print("=" * 104)
    print("复权价格 vs 原始价格 · 因子对比（同一批股票、同一套因子、只改价格口径）")
    print("=" * 104)
    t0 = time.time()

    from real_alpha_pipeline import load_certified_csv
    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if args.max_stocks > 0 and len(codes) > args.max_stocks:
        step = len(codes) / args.max_stocks
        codes = [codes[int(i * step)] for i in range(args.max_stocks)]

    print("[1/3] 加载数据与公司行动 ...")
    acts = load_actions(actions_path)
    print(f"      公司行动: {sum(len(v) for v in acts.values()):,} 条，覆盖 "
          f"{len(acts):,} 只股票")

    raw_data: Dict[str, List[Dict[str, Any]]] = {}
    adj_data: Dict[str, List[Dict[str, Any]]] = {}
    n_adj_events = 0
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        bars = load_certified_csv(p, m)
        raw_data[c] = bars
        stock_acts = acts.get(c, [])
        if stock_acts:
            n_adj_events += len(stock_acts)
            adj_data[c] = adjust_bars(bars, stock_acts)
        else:
            adj_data[c] = bars
    print(f"      股票 {len(raw_data):,} 只，其中 {sum(1 for c in raw_data if acts.get(c)):,} "
          f"只有分红记录（共 {n_adj_events:,} 个事件）  ({time.time()-t0:.0f}s)")

    print("\n[2/3] 原始价 IC 检验 ...")
    raw_res = run_ic_study(raw_data, horizon=args.horizon, step=args.step)
    print(f"      调仓期数 {raw_res['n_rebalance_dates']}，"
          f"平均截面 {raw_res['avg_cross_section']:.0f}  ({time.time()-t0:.0f}s)")

    print("\n[3/3] 复权价 IC 检验 ...")
    adj_res = run_ic_study(adj_data, horizon=args.horizon, step=args.step)
    print(f"      调仓期数 {adj_res['n_rebalance_dates']}  ({time.time()-t0:.0f}s)")

    # ---- 对比 ----
    print("\n" + "=" * 104)
    print("对比：原始价 vs 复权价")
    print("=" * 104)
    print(f"{'因子':20s} {'原始 IC':>10s} {'原始 t':>8s} {'复权 IC':>10s} {'复权 t':>8s} "
          f"{'IC 变化':>10s} {'|IC|变化':>10s}  判定")
    print("-" * 104)
    comparison: Dict[str, Any] = {}
    for k in FACTOR_LABELS:
        r = raw_res["factors"].get(k, {})
        a = adj_res["factors"].get(k, {})
        if "error" in r or "error" in a:
            continue
        d = a["ic_mean"] - r["ic_mean"]
        dabs = abs(a["ic_mean"]) - abs(r["ic_mean"])
        comparison[k] = {"raw_ic": r["ic_mean"], "raw_t": r["t"],
                         "adj_ic": a["ic_mean"], "adj_t": a["t"],
                         "ic_delta": d, "abs_ic_delta": dabs,
                         "raw_verdict": _verdict(r), "adj_verdict": _verdict(a)}
        print(f"{k:20s} {r['ic_mean']:>+10.4f} {r['t']:>8.2f} "
              f"{a['ic_mean']:>+10.4f} {a['t']:>8.2f} {d:>+10.4f} {dabs:>+10.4f}  "
              f"{_verdict(a)}")

    # ---- 关键检验：反转因子的 |IC| 是否下降 ----
    print("\n" + "-" * 104)
    print("关键检验：假下跌被修正后，反转类因子的 |IC| 是否下降？")
    print("-" * 104)
    rev = ["ret_1", "ret_5", "ret_20"]
    shrink = [k for k in rev if comparison.get(k, {}).get("abs_ic_delta", 0) < 0]
    grow = [k for k in rev if comparison.get(k, {}).get("abs_ic_delta", 0) > 0]
    for k in rev:
        cmp_row = comparison.get(k)
        if not cmp_row:
            continue
        print(f"  {k:10s} |IC| {abs(cmp_row['raw_ic']):.4f} → {abs(cmp_row['adj_ic']):.4f}  "
              f"({'下降' if cmp_row['abs_ic_delta'] < 0 else '上升'} {abs(cmp_row['abs_ic_delta']):.4f})")
    print()
    if len(shrink) == len(rev):
        print("  结论：三个反转因子 |IC| 全部下降 → **假下跌确实在放大反转效应**")
    elif len(shrink) > len(grow):
        print(f"  结论：{len(shrink)}/{len(rev)} 个反转因子 |IC| 下降 → 方向支持预测，但不完全")
    else:
        print("  结论：预测未获支持（复权未降低反转因子强度）")

    # ---- 分位组对比（反转因子）----
    print("\n" + "-" * 104)
    print("分位组对比（Q1=因子最低，Q5=因子最高；单位 %）")
    print("-" * 104)
    print(f"{'因子':12s} {'口径':6s} {'Q1':>9s} {'Q2':>9s} {'Q3':>9s} {'Q4':>9s} "
          f"{'Q5':>9s} {'Q5-Q1':>9s}")
    for k in ["ret_5", "ret_20", "max_ret_20"]:
        for label, dat in (("原始", raw_data), ("复权", adj_data)):
            q = quintile_returns(dat, k, horizon=args.horizon, step=args.step)
            if not q:
                continue
            g = [x * 100 for x in q["group_mean_returns"]]
            print(f"{k:12s} {label:6s} {g[0]:>+9.3f} {g[1]:>+9.3f} {g[2]:>+9.3f} "
                  f"{g[3]:>+9.3f} {g[4]:>+9.3f} {q['long_short_pct']:>+9.3f}")

    print()
    print("声明：本检验未调任何参数，只改价格口径（原始 vs 复权）。")
    print("      数据仍存在幸存者偏差（不含退市股），结果不构成投资结论。")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"comparison": comparison,
                       "raw": raw_res["factors"], "adjusted": adj_res["factors"],
                       "n_events": n_adj_events,
                       "n_stocks": len(raw_data), "args": vars(args)},
                      fh, ensure_ascii=False, indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    print(f"总耗时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
