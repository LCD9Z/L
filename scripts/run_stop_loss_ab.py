# -*- coding: utf-8 -*-
r"""ATR 移动止损 A/B 研究：把「能力孤岛」接进回测闭环后的实证。

## 背景

2026-09-30 专家圆桌审查中，**短线冲浪手**指出：

> `risk/a_share_risk.py::position_plan` 的 **ATR 止损 `last−2*ATR`、跟踪止损 `last−3*ATR`**
> **回测只按固定持有期卖，从未用过**。

核实：`position_plan` 只在 `daily_stock_pick.py` 被调用，`portfolio_backtest` 的卖出路径
完全没碰它。本脚本检验「接上止损」是否真的改善。

## 事前登记（跑前固定，不得事后调整）

| 项 | 设定 |
|----|------|
| 规则 | 移动止损 `stop = 持仓期最高收盘 − k × ATR(14)` |
| ATR 窗口 | **截至前一日**的 14 根（PIT，不含当日） |
| 触发 | 当日收盘 < stop → 按**当日收盘价**平仓（与 `exit_due` 同约定） |
| k | **2.0**（与 `position_plan` 的 `last − 2*ATR` 同源） |
| 对照 | `k=0`（固定持有期，即历史行为） |
| 配置 | C5 / 持有 20 日 / 尾部剔除（项目已确立基线） |
| 必报 | **止损率** + **平均触发天数**（短线冲浪手 P0-2 验收要求） |

## 用法

::

    python scripts/run_stop_loss_ab.py --dataset D:/tdx_dataset_v3 \
        --windows 2023-07-03,2024-01-02,2025-01-02 --out reports/stop_loss_ab.json
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
from real_alpha_pipeline import _curve_returns, load_certified_csv  # noqa: E402
from portfolio_backtest import portfolio_backtest  # noqa: E402
from alpha.alpha_survival_lab import annualized_excess_arithmetic  # noqa: E402
from risk.expert_filter import build_expert_filter  # noqa: E402

STOP_K = 2.0
DEFAULT_WINDOWS = ["2023-07-03", "2024-01-02", "2025-01-02"]


def _load(dataset: str, max_stocks: int) -> Dict[str, List[Dict[str, Any]]]:
    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                   if f.endswith(".csv") and f[:-4].isdigit())
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    out: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        try:
            out[c] = load_certified_csv(p, m)
        except Exception:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="ATR 移动止损 A/B")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--max-stocks", type=int, default=300)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--stop-k", type=float, default=STOP_K)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    windows = [w.strip() for w in args.windows.split(",") if w.strip()]
    print("=" * 100)
    print("ATR 移动止损 A/B · 「能力孤岛」接线实证")
    print("=" * 100)
    print(f"止损 k={args.stop_k} | 窗口 {windows} | C{args.top_n} / h={args.horizon} / 尾部剔除基线\n")

    t0 = time.time()
    data = _load(args.dataset, args.max_stocks)
    print(f"股票 {len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)

    # 项目已确立基线：尾部剔除（filter 与止损是正交的两层，都要开）
    flt, _ = build_expert_filter(data, use_market=False, use_turnover=False,
                                 use_streak=False, use_tail=True)

    with open(os.path.join(args.dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = json.load(fh)["snapshots"]
    import csv as _csv
    with open(os.path.join(args.dataset, "benchmark.csv"), encoding="utf-8") as fh:
        bench_all = list(_csv.DictReader(fh))

    rows: List[Dict[str, Any]] = []
    for w in windows:
        bench = [b for b in bench_all if str(b["date"]) >= w]
        b_ret: Dict[str, float] = {}
        for a, b in pairwise(bench):
            if float(a["close"]) > 0:
                b_ret[str(b["date"])] = float(b["close"]) / float(a["close"]) - 1
        for label, k in (("A_固定持有", 0.0), (f"B_ATR止损_k{args.stop_k}", args.stop_k)):
            res = portfolio_backtest(
                data, universe_snapshot_map=universe, threshold=70, top_n=args.top_n,
                horizon=args.horizon, max_position_pct=0.25, start_signal_date=w,
                candidate_filter=flt, stop_atr_k=k)
            s_ret = _curve_returns(res.get("equity_curve", []))
            common = sorted(set(s_ret) & set(b_ret))
            exc = (annualized_excess_arithmetic([s_ret[d] - b_ret[d] for d in common],
                                                as_percent=True) if common else None)
            st = res.get("stop_stats") or {}
            rows.append({
                "variant": label, "window": w, "stop_atr_k": k,
                "annualized_excess_pct": round(exc, 2) if exc is not None else None,
                "trades": res.get("trades"),
                "max_drawdown_pct": res.get("max_drawdown_pct"),
                "win_rate_pct": res.get("win_rate_pct"),
                "n_stops": st.get("n_stops"),
                "stop_rate_pct": st.get("stop_rate_pct"),
                "avg_days_to_stop": st.get("avg_days_to_stop"),
            })
            write_partial(args.out, {"rows": rows, "args": vars(args)},
                          note=f"已完成 {len(rows)}/{len(windows) * 2} 个单元")
            print(f"  {label:<20} {w}  净超额 {exc:+7.2f}%  交易 {res.get('trades'):>4}  "
                  f"回撤 {res.get('max_drawdown_pct')}%  止损 {st.get('n_stops')} 次"
                  f"（率 {st.get('stop_rate_pct')}%，均 {st.get('avg_days_to_stop')} 天）"
                  f"  ({time.time() - t0:.0f}s)", flush=True)

    # ---- 汇总 ----
    print("\n" + "=" * 100)
    print("汇总")
    print("=" * 100)
    print(f"{'变体':<22}{'净超额均值':>12}{'回撤均值':>11}{'交易均值':>10}"
          f"{'止损率均值':>12}{'均触发天数':>12}")
    summary: Dict[str, Any] = {}
    for label in ("A_固定持有", f"B_ATR止损_k{args.stop_k}"):
        rs = [r for r in rows if r["variant"] == label]
        vals = [r["annualized_excess_pct"] for r in rs if r["annualized_excess_pct"] is not None]
        dd = [r["max_drawdown_pct"] for r in rs if r["max_drawdown_pct"] is not None]
        tr = [r["trades"] for r in rs if r["trades"]]
        sr = [r["stop_rate_pct"] for r in rs if r["stop_rate_pct"] is not None]
        ad = [r["avg_days_to_stop"] for r in rs if r["avg_days_to_stop"] is not None]
        if not vals:
            continue
        summary[label] = {"mean": statistics.mean(vals), "dd_mean": statistics.mean(dd) if dd else None,
                          "trades_mean": statistics.mean(tr) if tr else None,
                          "stop_rate_mean": statistics.mean(sr) if sr else None,
                          "avg_days_mean": statistics.mean(ad) if ad else None,
                          "values": vals}
        print(f"{label:<22}{statistics.mean(vals):>+12.2f}"
              f"{(statistics.mean(dd) if dd else 0):>11.2f}"
              f"{(statistics.mean(tr) if tr else 0):>10.0f}"
              f"{(statistics.mean(sr) if sr else 0):>12.2f}"
              f"{(statistics.mean(ad) if ad else 0):>12.2f}")

    # 配对比较（同窗口）
    a_vals = [r["annualized_excess_pct"] for r in rows if r["variant"] == "A_固定持有"]
    b_vals = [r["annualized_excess_pct"] for r in rows
              if r["variant"] == f"B_ATR止损_k{args.stop_k}"]
    if len(a_vals) == len(b_vals) and a_vals:
        deltas = [b - a for a, b in zip(a_vals, b_vals, strict=False)]
        print(f"\n同窗口配对：Δ超额 = {[round(d, 2) for d in deltas]}")
        print(f"  止损版优于固定持有的窗口: {sum(1 for d in deltas if d > 0)}/{len(deltas)}"
              f"，Δ中位 {statistics.median(deltas):+.2f}pp")

    print("\n" + "=" * 104)
    print("声明")
    print("=" * 104)
    print("  · 止损规则与 k **事前固定**；ATR 只用截至前一日的 14 根（PIT，不含当日）")
    print("  · 触发后按**当日收盘价**平仓，与既有 exit_due 的平仓约定一致")
    print("  · ⚠️ 窗口数有限，**不构成结论**；判定需更多独立窗口")
    print("  · 结论不构成投资建议")

    write_final(args.out, {"rows": rows, "summary": summary, "args": vars(args)})
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
