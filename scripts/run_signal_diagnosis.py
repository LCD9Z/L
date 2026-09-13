# -*- coding: utf-8 -*-
"""基线策略的因子暴露诊断：把"策略亏钱"与"因子暴露"连成因果链。

## 要回答的问题

前面的因子研究已证明若干因子有稳定负 IC（如 `ret_20`、`vol_20`、`vol_ratio`、
`max_ret_20`）。但这是**因子层面**的证据。

本脚本进一步验证：**基线策略选出的股票，是否系统性地落在这些负 IC 因子的极端分位？**

若是，则"策略失败"不是运气，而是**由选股逻辑的因子暴露决定的必然结果** —— 因果闭环。

## 方法

对每个调仓日：

1. 按策略原逻辑给全池打分（`score_history` + 流动性过滤）
2. 取分数最高的 top_n 只（即策略会买入的标的）
3. 记录这些标的各因子的分位（相对当期全池）
4. 记录它们的前瞻收益，与全池平均对比

**注意**：本脚本只做诊断，不构造新策略、不调参。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.factor_ic_lab import (  # noqa: E402
    MIN_HISTORY,
    build_panel,
    compute_factors,
    forward_return,
)

SCORE_KEYS = ["ret_5", "ret_20", "vol_20", "vol_ratio", "max_ret_20",
              "amihud_20", "log_amount_20", "price"]


def _pct_rank(value: float, pool: List[float]) -> float:
    """value 在 pool 中的分位（0~1）。"""
    if not pool:
        return float("nan")
    below = sum(1 for x in pool if x < value)
    return below / len(pool)


def main() -> int:
    ap = argparse.ArgumentParser(description="基线策略因子暴露诊断")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=70.0)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--min-avg-amount", type=float, default=100_000_000)
    ap.add_argument("--lookback", type=int, default=250,
                    help="传给 score_history 的历史窗口（近似原实现的全程回看）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from real_alpha_pipeline import load_certified_csv
    from walk_forward import score_history

    dataset = os.path.abspath(args.dataset)
    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if args.max_stocks > 0 and len(codes) > args.max_stocks:
        step = len(codes) / args.max_stocks
        codes = [codes[int(i * step)] for i in range(args.max_stocks)]

    print("=" * 96)
    print("基线策略因子暴露诊断（验证「策略失败」是否由选股逻辑决定）")
    print("=" * 96)

    t0 = time.time()
    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if os.path.exists(p) and os.path.exists(m):
            data[c] = load_certified_csv(p, m)
    print(f"股票 {len(data):,} 只  ({time.time()-t0:.0f}s)")

    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    panel = build_panel(data)
    rebal = panel[MIN_HISTORY::args.step]

    picked_factor_ranks: Dict[str, List[float]] = {k: [] for k in SCORE_KEYS}
    picked_fwd: List[float] = []
    universe_fwd: List[float] = []
    n_periods = 0
    n_picked_total = 0

    for day in rebal:
        rows = []
        for code, bars in data.items():
            i = idx_map[code].get(day)
            if i is None or i < MIN_HISTORY:
                continue
            hist = bars[max(0, i - args.lookback + 1):i + 1]
            if len(hist) < 30:
                continue
            # 流动性过滤（与原策略一致）
            recent = hist[-20:]
            avg_amt = sum(float(b.get("amount") or 0) for b in recent) / max(1, len(recent))
            if avg_amt < args.min_avg_amount:
                continue
            fac = compute_factors(bars, i)
            if fac is None:
                continue
            fr = forward_return(bars, i, args.horizon)
            if fr is None:
                continue
            sc = score_history(hist)
            rows.append({"code": code, "score": sc["score"], "risk": sc["risk"],
                         "fac": fac, "fwd": fr})
        if len(rows) < 50:
            continue
        n_periods += 1
        universe_fwd.append(sum(r["fwd"] for r in rows) / len(rows))

        # 策略选股：score>=threshold 且 risk<=7，按 (score, -risk) 降序取 top_n
        cands = [r for r in rows if r["score"] >= args.threshold and r["risk"] <= 7]
        cands.sort(key=lambda r: (r["score"], -r["risk"]), reverse=True)
        picked = cands[:args.top_n]
        if not picked:
            continue
        n_picked_total += len(picked)
        for r in picked:
            picked_fwd.append(r["fwd"])
        # 因子分位（相对当期全池）
        for k in SCORE_KEYS:
            pool = [r["fac"][k] for r in rows]
            for r in picked:
                picked_factor_ranks[k].append(_pct_rank(r["fac"][k], pool))

    print(f"调仓期数 {n_periods}，累计选股 {n_picked_total:,} 次  ({time.time()-t0:.0f}s)")

    def _mean(xs: List[float]) -> float:
        return sum(xs) / len(xs) if xs else float("nan")

    print()
    print("-" * 96)
    print("选股组合的因子分位（0=全池最低，1=全池最高；0.5=中位）")
    print("-" * 96)
    print(f"{'因子':22s} {'平均分位':>10s}  解读")
    print("-" * 96)
    ranks_out: Dict[str, float] = {}
    for k in SCORE_KEYS:
        mean_rank = _mean(picked_factor_ranks[k])
        ranks_out[k] = mean_rank
        if mean_rank >= 0.75:
            note = "选在高位（落入 Q5 尾部）"
        elif mean_rank >= 0.6:
            note = "选在偏高位"
        elif mean_rank <= 0.25:
            note = "选在低位（落入 Q1）"
        else:
            note = "接近中性"
        print(f"{k:22s} {mean_rank:>10.3f}  {note}")

    uf, pf = _mean(universe_fwd), _mean(picked_fwd)
    print()
    print("-" * 96)
    print("前瞻收益对比（每 5 个交易日）")
    print("-" * 96)
    print(f"  全池平均前瞻收益        : {uf*100:+.4f}%")
    print(f"  策略选股平均前瞻收益    : {pf*100:+.4f}%")
    print(f"  选股 - 全池             : {(pf-uf)*100:+.4f}%")
    ann = ((1 + pf) ** (252 / args.horizon) - 1) * 100 if pf > -1 else float("nan")
    print(f"  选股组合年化（未扣成本）: {ann:+.2f}%")

    print()
    print("=" * 96)
    print("结论要点")
    print("=" * 96)
    high = [k for k, v in ranks_out.items() if v >= 0.75]
    low = [k for k, v in ranks_out.items() if v <= 0.25]
    print(f"  选股显著偏高的因子（分位 >= 0.75）: {high or '无'}")
    print(f"  选股显著偏低的因子（分位 <= 0.25）: {low or '无'}")
    if pf < uf:
        print(f"  选股前瞻收益低于全池 {(uf-pf)*100:.4f} 个百分点/期 → 选股逻辑具有负向选择效应")
    else:
        print(f"  选股前瞻收益高于全池 {(pf-uf)*100:.4f} 个百分点/期")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"factor_ranks": ranks_out,
                       "universe_fwd_mean": uf, "picked_fwd_mean": pf,
                       "n_periods": n_periods, "n_picked": n_picked_total,
                       "args": vars(args)}, fh, ensure_ascii=False, indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
