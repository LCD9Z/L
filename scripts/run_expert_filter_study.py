# -*- coding: utf-8 -*-
r"""专家组合过滤器研究：逐条件归因 + 组合对比。

## 设计

以项目**唯一稳健的正向发现（尾部剔除）**为基线，逐个叠加六人圆桌的处方：

| 配置 | 组成 | 来源 |
|------|------|------|
| `base` | 无过滤器 | 对照 |
| `tail` | 尾部剔除（`ret_20`+`vol_ratio` 顶 20%） | 项目已确立 |
| `tail+market` | + 市场级风险日全池排除 | 📡 信号派首席 |
| `tail+turnover` | + 个股换手率 250 日自身分位 > 80% | 🏔️ 逆向投资人 |
| `tail+streak` | + 连板高度 ≥ 2 | ⚡ 短线冲浪手 |
| **`combo`** | **尾部剔除 + 市场 + 换手 + 连板** | **四位专家组合** |

**为什么以 tail 为基线而不是从零开始**：尾部剔除是项目**唯一有配对检验支撑**
（t = +8.35/+3.62/+2.52）的发现，其余专家的条件都是**未经检验的处方**。
从已确立的基线往上叠，才能判断「专家条件是否**增量**有效」。

## ⚠️ 事前登记（跑前固定，不得事后调整）

- 换手率分位阈值 **0.80**、窗 **250 日**、**不含当日**
- 连板阈值 **≥ 2**、用逐日 `limit_ratio` 判涨停
- 尾部剔除 **顶 20%**（沿用项目既有口径）
- 市场级风险日 = `EXTREME`（跌停占比 ≥ 20%），**不带冷却**（冷却属 gate 的语义）
- 组合方式 **AND**（任一条件触发即排除）

## 用法

::

    python scripts/run_expert_filter_study.py --dataset D:/tdx_dataset_v3 \
        --windows 2024-01-02 --max-stocks 300 --out reports/expert_filter_study.json
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
from risk.market_risk_gate import compute_market_risk  # noqa: E402
from risk.expert_filter import build_expert_filter  # noqa: E402

# (标签, use_market, use_turnover, use_streak, use_tail)
VARIANTS: List[tuple] = [
    ("base_无过滤", False, False, False, False),
    ("tail_仅尾部剔除", False, False, False, True),
    ("tail+market_加信号派", True, False, False, True),
    ("tail+turnover_加逆向", False, True, False, True),
    ("tail+streak_加短线", False, False, True, True),
    ("combo_四专家组合", True, True, True, True),
]
DEFAULT_WINDOWS = ["2024-01-02"]


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
    ap = argparse.ArgumentParser(description="专家组合过滤器研究")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--max-stocks", type=int, default=300)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 104)
    print("专家组合过滤器研究 · 以「尾部剔除」为基线，逐个叠加六人圆桌的处方")
    print("=" * 104)
    print(f"变体 {len(VARIANTS)} 个 | 窗口 {windows} | horizon={args.horizon} | "
          f"组合方式 AND\n")

    t0 = time.time()
    data = _load(args.dataset, args.max_stocks)
    print(f"股票 {len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)

    print("[1/2] 计算市场级风险状态 ...", flush=True)
    market = compute_market_risk(
        {c: [{"date": b.get("date"), "close": b.get("close"),
              "amount": b.get("amount"), "limit_ratio": b.get("limit_ratio")}
             for b in bars] for c, bars in data.items()})
    print(f"      EXTREME 日 {sum(1 for v in market.values() if v['state'] == 'EXTREME')} 天",
          flush=True)

    with open(os.path.join(args.dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = json.load(fh)["snapshots"]
    import csv as _csv
    with open(os.path.join(args.dataset, "benchmark.csv"), encoding="utf-8") as fh:
        bench_all = list(_csv.DictReader(fh))

    print("\n[2/2] 逐变体 × 逐窗口回测 ...", flush=True)
    rows: List[Dict[str, Any]] = []
    total = len(VARIANTS) * len(windows)
    for label, use_mkt, use_to, use_st, use_tail in VARIANTS:
        flt, fstats = build_expert_filter(
            data, market_risk=market, use_market=use_mkt, use_turnover=use_to,
            use_streak=use_st, use_tail=use_tail)
        for w in windows:
            bench = [b for b in bench_all if str(b["date"]) >= w]
            b_ret: Dict[str, float] = {}
            for a, b in pairwise(bench):
                if float(a["close"]) > 0:
                    b_ret[str(b["date"])] = float(b["close"]) / float(a["close"]) - 1
            res = portfolio_backtest(
                data, universe_snapshot_map=universe, threshold=70, top_n=args.top_n,
                horizon=args.horizon, max_position_pct=0.25, start_signal_date=w,
                candidate_filter=flt)
            s_ret = _curve_returns(res.get("equity_curve", []))
            common = sorted(set(s_ret) & set(b_ret))
            exc = (annualized_excess_arithmetic([s_ret[d] - b_ret[d] for d in common],
                                                as_percent=True) if common else None)
            rows.append({
                "variant": label, "window": w,
                "annualized_excess_pct": round(exc, 2) if exc is not None else None,
                "trades": res.get("trades"),
                "max_drawdown_pct": res.get("max_drawdown_pct"),
                "filter_stats": fstats,
            })
            write_partial(args.out, {"rows": rows, "args": vars(args)},
                          note=f"已完成 {len(rows)}/{total} 个单元")
            exc_txt = f"{exc:+.2f}" if exc is not None else "—"
            print(f"  {label:<22} {w}  净超额 {exc_txt:>8}%  交易 "
                  f"{res.get('trades'):>5}  回撤 {res.get('max_drawdown_pct')}%  "
                  f"({time.time() - t0:.0f}s)", flush=True)

    # ---- 汇总（以 base 为参照的增量）----
    print("\n" + "=" * 104)
    print("汇总：各变体相对 base 的增量")
    print("=" * 104)
    base_vals = [r["annualized_excess_pct"] for r in rows
                 if r["variant"] == "base_无过滤" and r["annualized_excess_pct"] is not None]
    base_mean = statistics.mean(base_vals) if base_vals else None
    print(f"{'变体':<24}{'净超额均值':>12}{'vs base':>11}{'交易数':>8}{'回撤均值':>11}")
    summary: Dict[str, Any] = {}
    for label, *_ in VARIANTS:
        rs = [r for r in rows if r["variant"] == label]
        vals = [r["annualized_excess_pct"] for r in rs
                if r["annualized_excess_pct"] is not None]
        tr = [r["trades"] for r in rs if r["trades"]]
        dd = [r["max_drawdown_pct"] for r in rs if r["max_drawdown_pct"] is not None]
        if not vals:
            continue
        m = statistics.mean(vals)
        delta = (m - base_mean) if base_mean is not None else None
        summary[label] = {"mean": m, "vs_base": delta, "n": len(vals),
                          "trades_mean": statistics.mean(tr) if tr else None,
                          "dd_mean": statistics.mean(dd) if dd else None,
                          "values": vals}
        d_txt = f"{delta:+.2f}pp" if delta is not None else "—"
        print(f"{label:<24}{m:>+12.2f}{d_txt:>11}"
              f"{(statistics.mean(tr) if tr else 0):>8.0f}"
              f"{(statistics.mean(dd) if dd else 0):>11.2f}")

    print("\n" + "=" * 104)
    print("声明")
    print("=" * 104)
    print("  · 阈值**事前固定**（换手分位 0.80 / 连板 ≥2 / 尾部 20%），不得依据结果调整")
    print("  · 全部条件**只用 day 及之前数据**；换手率分位窗**不含当日**（防自我参照）")
    print("  · ⚠️ 单窗口结果**不构成结论**；圆桌要求 ≥5 窗口，本脚本支持 --windows 多窗口")
    print("  · 组合为 **AND**（任一条件触发即排除）；各条件独立可开关，便于归因")
    print("  · 未实现：产业策略师的统计行业聚类、估值分析师的 PIT 财务分档（需额外工作）")
    print("  · 结论不构成投资建议")

    write_final(args.out, {"rows": rows, "summary": summary, "args": vars(args),
                           "variants": [v[0] for v in VARIANTS]})
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
