# -*- coding: utf-8 -*-
r"""估值权重调节器 A/B：把 `pb`/`pe_ttm` 从「排序因子」升级为「仓位权重」的实证。

## 被检验的处方

2026-09-30 专家圆桌审查中，**估值分析师**指出系统「只称 PE 的分子，从没算过分母」，
并给出处方：

> 「**最该补的不是「再加一个因子」，而是把 `pb`/`pe_ttm` 从「排序因子」升级成
> 「仓位权重调节器」** —— 同样的信号，估值在下轨的给高权重、在上轨的给低权重甚至不建仓。」

**为什么这条路设计上更可能有效**：`pb`/`pe_ttm` 是项目**仅有的两个通过
BH+Bonferroni 双校正**的因子，且**与三个价量维度低相关** → 提供一路**正交**权重来源。

## 事前登记（跑前固定，不得依据结果调整）

| 项 | 设定 |
|----|------|
| 估值指标 | `pe_ttm`（项目双校正因子之一） |
| 分档 | 当日候选池内横截面分位：下轨 `<0.33` / 中 `0.33~0.67` / 上轨 `>0.67` |
| 权重 | 下轨 **1.5** / 中 **1.0** / 上轨 **0.5**；**缺失 → 1.0（不干预）** |
| 对照 | `weight_func=None`（等权，即历史行为） |
| 基线 | 尾部剔除（`ret_20`+`vol_ratio` 顶 20%）—— 与 `run_stop_loss_ab.py` 一致 |
| PIT | `PitFundamentals.factors_as_of(code, day, price=当日收盘)` |

## 验收标准（估值分析师原文）

> 「同信号下加估值分档 vs 等权：**离散度下降**；权重差异方向与 `pb`/`pe_ttm` 一致」

本脚本报告：Δ超额、Δ回撤、Δ交易数、权重分档计数。
**离散度检验需独立设计（多次随机抽样），本轮不做，在报告中显式标注。**

## 用法

::

    python scripts/run_valuation_weight_ab.py --dataset D:/tdx_dataset_v3 \
        --windows 2023-07-03,2024-01-02,2025-01-02 --out reports/valuation_weight_ab.json
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

from research_artifacts import write_final, write_partial  # noqa: E402
from real_alpha_pipeline import _curve_returns  # noqa: E402
from _study_common import load_certified_stocks as _load  # noqa: E402 — P2 收敛（审计 3.1 #1，A 族默认参数）
from portfolio_backtest import portfolio_backtest  # noqa: E402
from alpha.alpha_survival_lab import annualized_excess_arithmetic  # noqa: E402
from risk.expert_filter import build_expert_filter  # noqa: E402
from risk.valuation_weight import build_valuation_weight  # noqa: E402

DEFAULT_WINDOWS = ["2023-07-03", "2024-01-02", "2025-01-02"]


def main() -> int:
    ap = argparse.ArgumentParser(description="估值权重调节器 A/B")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--max-stocks", type=int, default=300)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--metric", default="pe_ttm")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    windows = [w.strip() for w in args.windows.split(",") if w.strip()]
    print("=" * 100)
    print(f"估值权重调节器 A/B · 把 {args.metric} 从「排序因子」升级为「仓位权重」")
    print("=" * 100)
    print(f"窗口 {windows} | C{args.top_n} / h={args.horizon} / 尾部剔除基线 | "
          f"分档 1.5 / 1.0 / 0.5\n")

    t0 = time.time()
    data = _load(args.dataset, args.max_stocks)
    print(f"股票 {len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)

    # 基线：尾部剔除（与止损 A/B 同口径，保证可比）
    flt, _ = build_expert_filter(data, use_market=False, use_turnover=False,
                                 use_streak=False, use_tail=True)

    # 只对调仓日算权重（全部交易日太慢）
    all_days = sorted({str(b["date"]) for bars in data.values() for b in bars})
    rebal_days = [d for d in all_days if any(d >= w for w in windows)][::args.horizon]
    print(f"[1/2] 预计算估值权重（{len(rebal_days)} 个候选日）...", flush=True)
    wf, wstats = build_valuation_weight(args.dataset, data, metric=args.metric,
                                        rebalance_days=rebal_days)
    print(f"      覆盖 {wstats['days_covered']} 日 · 分档 "
          f"低{wstats['n_low']}/中{wstats['n_mid']}/高{wstats['n_high']} · "
          f"财务覆盖率 {(wstats.get('coverage') or {}).get('ratio')}", flush=True)

    with open(os.path.join(args.dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = json.load(fh)["snapshots"]
    import csv as _csv
    with open(os.path.join(args.dataset, "benchmark.csv"), encoding="utf-8") as fh:
        bench_all = list(_csv.DictReader(fh))

    print("\n[2/2] 逐窗口 A/B ...", flush=True)
    rows: List[Dict[str, Any]] = []
    for w in windows:
        bench = [b for b in bench_all if str(b["date"]) >= w]
        b_ret: Dict[str, float] = {}
        for a, b in pairwise(bench):
            if float(a["close"]) > 0:
                b_ret[str(b["date"])] = float(b["close"]) / float(a["close"]) - 1
        for label, wfn in (("A_等权", None), ("B_估值加权", wf)):
            res = portfolio_backtest(
                data, universe_snapshot_map=universe, threshold=70, top_n=args.top_n,
                horizon=args.horizon, max_position_pct=0.25, start_signal_date=w,
                candidate_filter=flt, weight_func=wfn)
            s_ret = _curve_returns(res.get("equity_curve", []))
            common = sorted(set(s_ret) & set(b_ret))
            exc = (annualized_excess_arithmetic([s_ret[d] - b_ret[d] for d in common],
                                                as_percent=True) if common else None)
            rows.append({
                "variant": label, "window": w,
                "annualized_excess_pct": round(exc, 2) if exc is not None else None,
                "trades": res.get("trades"),
                "max_drawdown_pct": res.get("max_drawdown_pct"),
                "total_return_pct": res.get("total_return_pct"),
            })
            write_partial(args.out, {"rows": rows, "args": vars(args),
                                     "weight_stats": wstats},
                          note=f"已完成 {len(rows)}/{len(windows) * 2} 个单元")
            print(f"  {label:<12} {w}  净超额 {exc:+7.2f}%  交易 {res.get('trades'):>4}  "
                  f"回撤 {res.get('max_drawdown_pct')}%  ({time.time() - t0:.0f}s)",
                  flush=True)

    # ---- 汇总 ----
    print("\n" + "=" * 100)
    print("汇总")
    print("=" * 100)
    summary: Dict[str, Any] = {}
    for label in ("A_等权", "B_估值加权"):
        rs = [r for r in rows if r["variant"] == label]
        vals = [r["annualized_excess_pct"] for r in rs if r["annualized_excess_pct"] is not None]
        dd = [r["max_drawdown_pct"] for r in rs if r["max_drawdown_pct"] is not None]
        if not vals:
            continue
        summary[label] = {"mean": statistics.mean(vals),
                          "median": statistics.median(vals),
                          "dd_mean": statistics.mean(dd) if dd else None,
                          "values": vals}
        print(f"  {label:<12} 均值 {statistics.mean(vals):+.2f}%  中位 "
              f"{statistics.median(vals):+.2f}%  回撤均值 "
              f"{(statistics.mean(dd) if dd else 0):.2f}%")

    # ⚠️ 变量名不得复用 `a`/`b` —— 它们在上面已被绑为 benchmark 行 dict，
    # mypy 的流分析会把列表赋值推成 dict 而报 incompatible assignment。
    vals_eq = [r["annualized_excess_pct"] for r in rows if r["variant"] == "A_等权"]
    vals_vw = [r["annualized_excess_pct"] for r in rows if r["variant"] == "B_估值加权"]
    if len(vals_eq) == len(vals_vw) and vals_eq:
        deltas = [y - x for x, y in zip(vals_eq, vals_vw, strict=False)]
        print(f"\n  同窗口配对 Δ超额 = {[round(d, 2) for d in deltas]}")
        print(f"  估值加权优于等权的窗口: {sum(1 for d in deltas if d > 0)}/{len(deltas)}"
              f"，Δ中位 {statistics.median(deltas):+.2f}pp")
        if len(deltas) > 1:
            sd = statistics.stdev(deltas)
            t = statistics.mean(deltas) / (sd / len(deltas) ** 0.5) if sd > 0 else None
            summary["paired"] = {"deltas": deltas, "median": statistics.median(deltas),
                                 "mean": statistics.mean(deltas), "t": t}
            print(f"  Δ均值 {statistics.mean(deltas):+.2f}pp  t={t:.2f}"
                  if t is not None else "  （样本不足，t 未计算）")

    print("\n" + "=" * 100)
    print("声明")
    print("=" * 100)
    print("  · 分档与权重**事前固定**（0.33/0.67 → 1.5/1.0/0.5），不得依据结果调整")
    print("  · 权重缺失 → 1.0（不干预）；PIT 用当日收盘价算 PE，无未来信息")
    print("  · ⚠️ 估值分析师要求的「离散度下降」检验需多次随机抽样，**本轮未做**")
    print("  · ⚠️ 窗口数有限，**不构成结论**")
    print("  · 结论不构成投资建议")

    write_final(args.out, {"rows": rows, "summary": summary, "args": vars(args),
                           "weight_stats": wstats})
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
