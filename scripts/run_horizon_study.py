# -*- coding: utf-8 -*-
r"""持有期净效果研究：5 / 10 / 20 / 40 日持有的**组合层面净收益**对比。

## 为什么做这个

`FACTOR_HORIZON_DECAY_REPORT.md` 测出「慢变量（规模/波动/流动性/价格）的 IC
随持有期单调增强至 40 日」，但**明确声明不能据此推出"延长持有期更好"** ——
因为年化毛超额 ∝ IC(H)/√H 随 H 下降，而成本 ∝ 1/H 也下降，
**两者同向下降，净效果符号无法由 IC 数据判定**。

本脚本补上那一环：**直接测组合层面的净年化超额**。

## 口径

* 信号 / 阈值 / 持仓数 / 成本模型**全部不变**，**只改持有期与调仓间隔**
  （调仓间隔 = 持有期，保证前瞻不重叠）
* 净收益口径（含成本）；超额 = 组合 vs 自建等权全A基准（自建基准口径正确，
  见 `P0_P1_EXECUTION_REPORT.md` §3.2）
* 每个「持有期 × 窗口」单元完成后**增量落盘**（见 `research_artifacts`）

## 成本拖累的换算（本脚本只测净收益）

成本与成交笔数成正比，故 `成本拖累(H) ≈ 成本拖累(5) × 笔数(H)/笔数(5)`。
本脚本落盘每档的 `trades`，使该换算**可审计**。
H=5 的成本拖累基准取自 `reports/tail_exclusion_with_p.json`（同口径实测 16.58pp/年）。

## 用法

::

    python scripts/run_horizon_study.py --dataset D:/tdx_dataset_v3 \
        --horizons 5,10,20,40 --out reports/horizon_study.json
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from itertools import pairwise
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_artifacts import write_final, write_partial  # noqa: E402
from alpha.alpha_survival_lab import (  # noqa: E402
    annualized_excess_arithmetic,
    excess_t_statistics,
)
from portfolio_backtest import portfolio_backtest  # noqa: E402
from real_alpha_pipeline import _curve_returns  # noqa: E402

DEFAULT_WINDOWS = ["2023-07-03", "2024-01-02", "2025-01-02"]
# H=5 的实测成本拖累（v3 / 400 只 / 2023-07-03 窗口，见 tail_exclusion_with_p.json）
COST_DRAG_AT_H5_PP = 16.58
COST_DRAG_BASE_TRADES = 747


def _load(dataset: str, max_stocks: int, min_rows: int = 200
          ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, str]]:
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                   if f.endswith(".csv") and f[:-4].isdigit())
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    data: Dict[str, List[Dict[str, Any]]] = {}
    meta: Dict[str, str] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        try:
            bars = load_certified_csv(p, m)
        except Exception:
            continue
        if len(bars) >= min_rows:
            data[c] = bars
            meta[c] = c
    return data, meta


def main() -> int:
    ap = argparse.ArgumentParser(description="持有期净效果研究（组合层面）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--horizons", default="5,10,20,40")
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--max-stocks", type=int, default=300)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--position-pct", type=float, default=0.25)
    ap.add_argument("--threshold", type=float, default=70.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    horizons = [int(x) for x in args.horizons.split(",") if x.strip()]
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 100)
    print("持有期净效果研究 · 信号/阈值/持仓/成本全部不变，**只改持有期与调仓间隔**")
    print("=" * 100)
    print(f"持有期 {horizons} | 窗口 {windows} | top_n={args.top_n} | "
          f"净收益口径（含成本）\n")

    t0 = time.time()
    data, _ = _load(args.dataset, args.max_stocks)
    print(f"股票 {len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)

    # PIT 股票池快照：限制每日可选集合（与 tail_exclusion / concentration 口径一致）
    import json as _json
    universe: Dict[str, Any] = {}
    up = os.path.join(args.dataset, "pit_universe.json")
    if os.path.exists(up):
        with open(up, encoding="utf-8") as fh:
            universe = _json.load(fh)["snapshots"]
        print(f"PIT 股票池快照 {len(universe):,} 个交易日", flush=True)
    else:
        print("⚠️ 未找到 pit_universe.json，将不做 PIT 池限制", flush=True)

    # 自建等权全A基准（口径正确；见 P0_P1_EXECUTION_REPORT §3.2）
    bench_all: List[Dict[str, Any]] = []
    bp = os.path.join(args.dataset, "benchmark_equal_weight.csv")
    if not os.path.exists(bp):
        bp = os.path.join(args.dataset, "benchmark.csv")
    if os.path.exists(bp):
        import csv as _csv
        with open(bp, encoding="utf-8-sig", newline="") as fh:
            bench_all = list(_csv.DictReader(fh))
        print(f"基准 {len(bench_all):,} 根（{os.path.basename(bp)}）", flush=True)
    else:
        print("⚠️ 未找到基准文件，超额无法计算", flush=True)

    rows: List[Dict[str, Any]] = []
    total = len(horizons) * len(windows)
    for h in horizons:
        for w in windows:
            bench = [b for b in bench_all if str(b.get("date")) >= w]
            res = portfolio_backtest(
                data, universe_snapshot_map=universe or None,
                threshold=args.threshold, top_n=args.top_n,
                horizon=h, max_position_pct=args.position_pct,
                start_signal_date=w)
            s_ret = _curve_returns(res.get("equity_curve", []))
            b_ret: Dict[str, float] = {}
            for a, b in pairwise(bench):
                if float(a["close"]) > 0:
                    b_ret[str(b["date"])] = float(b["close"]) / float(a["close"]) - 1
            common = sorted(set(s_ret) & set(b_ret))
            excess = [s_ret[d] - b_ret[d] for d in common]
            exc = annualized_excess_arithmetic(excess, as_percent=True) if common else None
            st = excess_t_statistics(excess) if common else {"t": None, "p": None}
            bm = ((float(bench[-1]["close"]) / float(bench[0]["close"]) - 1) * 100
                  if bench else 0.0)
            trades = res.get("trades")
            # 成本拖累换算（与成交笔数成正比；H=5 为实测基准）
            drag = (COST_DRAG_AT_H5_PP * trades / COST_DRAG_BASE_TRADES
                    if trades else None)
            rows.append({
                "horizon": h, "window": w, "aligned_days": len(common),
                "trades": trades, "win_rate_pct": res.get("win_rate_pct"),
                "total_return_pct": res.get("total_return_pct"),
                "max_drawdown_pct": res.get("max_drawdown_pct"),
                "benchmark_return_pct": round(bm, 2),
                "net_annualized_excess_pct": (round(exc, 2) if exc is not None else None),
                "t_stat": st["t"], "p_value": st["p"],
                "est_cost_drag_pp": (round(drag, 2) if drag is not None else None),
                "gross_est_excess_pct": (round(exc + drag, 2)
                                         if (exc is not None and drag is not None) else None),
            })
            write_partial(args.out, {"rows": rows, "args": vars(args)},
                          note=f"已完成 {len(rows)}/{total} 个（持有期×窗口）单元")
            # 先算好再打印：避免在 f-string 里对 Optional 做算术（mypy 无法收窄）
            net_txt = f"{exc:+.2f}" if exc is not None else "—"
            drag_txt = f"{drag:.2f}" if drag is not None else "—"
            gross_txt = (f"{exc + drag:+.2f}"
                         if (exc is not None and drag is not None) else "—")
            print(f"  h={h:<3} {w}  笔数 {trades:>4}  净超额 {net_txt}%  "
                  f"（成本拖累估算 {drag_txt}pp → 毛超额估算 {gross_txt}%）  "
                  f"回撤 {res.get('max_drawdown_pct')}%", flush=True)

    # ---- 汇总 ----
    print("\n" + "=" * 100)
    print("汇总：各持有期的净年化超额（% ，跨窗口均值）")
    print("=" * 100)
    print(f"{'持有期':>6}{'笔数均值':>10}{'净超额均值':>12}{'成本拖累估算':>14}"
          f"{'毛超额估算':>12}{'为正窗口':>10}")
    summary: Dict[str, Any] = {}
    for h in horizons:
        rs = [r for r in rows if r["horizon"] == h]
        nets = [r["net_annualized_excess_pct"] for r in rs
                if r["net_annualized_excess_pct"] is not None]
        drags = [r["est_cost_drag_pp"] for r in rs if r["est_cost_drag_pp"] is not None]
        gross = [r["gross_est_excess_pct"] for r in rs
                 if r["gross_est_excess_pct"] is not None]
        tr = [r["trades"] for r in rs if r["trades"]]
        if not nets:
            continue
        summary[str(h)] = {
            "n_windows": len(nets), "net_mean": statistics.mean(nets),
            "net_min": min(nets), "net_max": max(nets),
            "positive_windows": sum(1 for v in nets if v > 0),
            "trades_mean": statistics.mean(tr) if tr else None,
            "est_cost_drag_mean": statistics.mean(drags) if drags else None,
            "gross_est_mean": statistics.mean(gross) if gross else None,
        }
        print(f"{h:>6}{statistics.mean(tr) if tr else 0:>10.0f}"
              f"{statistics.mean(nets):>+12.2f}"
              f"{statistics.mean(drags) if drags else 0:>14.2f}"
              f"{statistics.mean(gross) if gross else 0:>+12.2f}"
              f"{sum(1 for v in nets if v > 0):>7}/{len(nets)}")

    print("\n" + "=" * 100)
    print("声明")
    print("=" * 100)
    print("  · 只改持有期与调仓间隔，信号/阈值/持仓数/成本模型**全部不变**")
    print("  · 调仓间隔 = 持有期，**前瞻不重叠**")
    print("  · ⚠️ 成本拖累为**换算值**（按成交笔数比例，以 H=5 的 16.58pp/年实测为基准），")
    print("     非本脚本直接测量 —— 目的是让毛/净的分解可审计，不构成独立证据")
    print("  · 窗口数少（3 个），均值仅作**方向性**参考，不做显著性判定")
    print("  · 未做参数网格搜索；本实验是**结构性**问题（持有期值不值），非调参")
    print("  · 结论不构成投资建议")

    write_final(args.out, {"rows": rows, "summary": summary, "args": vars(args),
                           "horizons": horizons, "windows": windows})
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
