#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 条件 A/B —— 产业策略师「风格拥挤度 gate」与估值分析师「上轨排除」。

**执行依据**：`EXPERT_FILTER_C2_PREREG.md` §五（变体 / 必报项 / 验收判据）。
**不改** `scripts/run_expert_filter_study.py` 的既有配置（PREREG §六 明令），
故用独立入口，基线口径与既有研究**逐项对齐**：

- 数据集 ``D:/tdx_dataset_v3`` · ``--max-stocks 300`` · 窗口 ``2024-01-02``
- ``horizon=20`` · ``top_n=5`` · ``threshold=70`` · ``max_position_pct=0.25``
- 组合方式 **AND**（任一条件触发即排除）

**基线 ``base`` = 尾部剔除**（PREREG §五 表首行；与既有 `tail_仅尾部剔除` 同口径）。

事前固定（不得按结果调整）：拥挤分位 **0.80** / 回看 **250** / 簇数 **20**；
估值上轨 **80% 分位**；两个归一化口径 ``level`` / ``ratio`` **各自独立报告**。

## 必报项（PREREG §五，本脚本全部输出）

1. Δ年化超额、Δ最大回撤、Δ交易数（以 ``base`` 为参照）
2. **候选池收缩幅度**：每日排除比例的分位（p50 / p90 / max）
3. **排除持续性**：每只股票被排除的连续天数分布（max / p90）
4. **各条件单独命中比例**（归因，不只报组合结果）

## 用法
::

    # 小规模验证（先跑这个）
    python scripts/run_c2_ab.py --dataset D:/tdx_dataset_v3 --max-stocks 80 \
        --windows 2024-01-02 --out reports/_c2_ab_smoke.json

    # 与既有研究同口径
    python scripts/run_c2_ab.py --dataset D:/tdx_dataset_v3 --max-stocks 300 \
        --windows 2024-01-02 --out reports/c2_ab_study.json

⚠️ 本脚本**只产数字，不做「纳入默认」判断**。判据在 PREREG §五：
``Δ年化超额 > 0 且 Δ最大回撤 ≤ 0`` 才允许纳入；且 15 次比较须 BH/Bonferroni 校正。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from itertools import pairwise
from typing import Any, Dict, List, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _study_common import load_certified_stocks as _load  # noqa: E402
from alpha.alpha_survival_lab import annualized_excess_arithmetic  # noqa: E402
from pit.statistical_industry import build_statistical_industry  # noqa: E402
from portfolio_backtest import portfolio_backtest  # noqa: E402
from real_alpha_pipeline import _curve_returns  # noqa: E402
from research_artifacts import write_final, write_partial  # noqa: E402
from risk.expert_filter import (  # noqa: E402
    build_expert_filter,
    precompute_industry_crowding,
    precompute_valuation_cap,
)
from risk.market_risk_gate import compute_market_risk  # noqa: E402

#: (标签, build_expert_filter 的关键字参数)
#: base = 尾部剔除（既有研究基线）；D/E 分别叠加，互不组合（PREREG §五）
VARIANTS: List[Tuple[str, Dict[str, Any]]] = [
    ("base", {"use_tail": True}),
    ("D_level", {"use_tail": True, "use_industry_crowding": True,
                 "ind_normalize": "level"}),
    ("D_ratio", {"use_tail": True, "use_industry_crowding": True,
                 "ind_normalize": "ratio"}),
    ("E_pe", {"use_tail": True, "use_valuation_cap": True,
              "valuation_metric": "pe_ttm"}),
    ("E_pb", {"use_tail": True, "use_valuation_cap": True,
              "valuation_metric": "pb"}),
]

DEFAULT_WINDOW = "2024-01-02"


def _pct(seq: Sequence[float], q: float) -> float | None:
    """分位（线性插值）；空集返回 None —— 不补造。"""
    if not seq:
        return None
    s = sorted(seq)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _max_streaks(days_by_code: Dict[str, List[str]],
                 day_index: Dict[str, int]) -> List[int]:
    """每只股票被排除的**最长连续段**（按交易日索引，不是日期字符串）。

    ⚠️ 首版写成 ``b == a`` 比较相邻日期字符串 —— 集合去重后**恒不相等**，
    于是「最长连续」永远输出 1：不报错、看着像个结果，实际什么都没测到。
    必须映射到**交易日序号**，再判 ``b == a + 1``。
    """
    out: List[int] = []
    for days in days_by_code.values():
        idx = sorted(day_index[d] for d in days if d in day_index)
        if not idx:
            continue
        best = cur = 1
        for a, b in pairwise(idx):
            cur = cur + 1 if b == a + 1 else 1
            best = max(best, cur)
        out.append(best)
    return out


def _panel_stats(excl: Dict[str, Set[str]], all_days: List[str],
                 listed_by_day: Dict[str, int]) -> Dict[str, Any]:
    """必报项 2/3/4 的公共面板统计。"""
    by_code: Dict[str, List[str]] = {}
    for day, codes in excl.items():
        for c in codes:
            by_code.setdefault(c, []).append(day)
    shares = [len(excl.get(d, ())) / listed_by_day[d]
              for d in all_days if listed_by_day.get(d)]
    day_index = {d: i for i, d in enumerate(all_days)}
    streaks = _max_streaks(by_code, day_index)
    total_pairs = sum(listed_by_day.values()) or 1
    return {
        "excl_days": len(excl),
        "excl_pairs": sum(len(v) for v in excl.values()),
        "hit_share": round(sum(len(v) for v in excl.values()) / total_pairs, 4),
        "shrink_p50": round(_pct(shares, 0.50) or 0, 4),
        "shrink_p90": round(_pct(shares, 0.90) or 0, 4),
        "shrink_max": round(max(shares), 4) if shares else 0.0,
        "streak_max": max(streaks) if streaks else 0,
        "streak_p90": round(_pct(streaks, 0.90) or 0, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="C2 条件 A/B（PREREG §五）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--windows", default=DEFAULT_WINDOW)
    ap.add_argument("--max-stocks", type=int, default=300)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--out", default="reports/c2_ab_study.json")
    args = ap.parse_args()
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 100)
    print("C2 条件 A/B · base=尾部剔除 · D=簇拥挤 gate · E=估值上轨排除")
    print("=" * 100)
    print(f"变体 {len(VARIANTS)} | 窗口 {windows} | horizon={args.horizon} | "
          f"max_stocks={args.max_stocks}", flush=True)

    t0 = time.time()
    data = _load(args.dataset, args.max_stocks)
    print(f"股票 {len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)

    print("[1/5] 市场级风险 ...", flush=True)
    market = compute_market_risk(
        {c: [{"date": b.get("date"), "close": b.get("close"),
              "amount": b.get("amount"), "limit_ratio": b.get("limit_ratio")}
             for b in bars] for c, bars in data.items()})
    print(f"      EXTREME 日 {sum(1 for v in market.values() if v['state'] == 'EXTREME')}",
          flush=True)

    with open(os.path.join(args.dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = json.load(fh)["snapshots"]
    with open(os.path.join(args.dataset, "benchmark.csv"), encoding="utf-8") as fh:
        bench_all = list(csv.DictReader(fh))

    # 全池逐日「有数据的股票数」——收缩幅度的分母（不猜缺失）
    listed_by_day: Dict[str, int] = {}
    for bars in data.values():
        for b in bars:
            d = str(b.get("date"))
            listed_by_day[d] = listed_by_day.get(d, 0) + 1
    all_days = sorted(listed_by_day)

    print("[2/5] 统计行业聚类（一次性；D 的两个口径共用）...", flush=True)
    t1 = time.time()
    labels = build_statistical_industry(data)
    print(f"      标签日 {len(labels)} / {len(all_days)}（{time.time() - t1:.0f}s）",
          flush=True)

    print("[3/5] 预计算条件面板（必报项 2/3/4）...", flush=True)
    panels: Dict[str, Dict[str, Any]] = {}
    for tag, excl in (
        ("D_level", precompute_industry_crowding(data, labels=labels,
                                                 normalize="level")),
        ("D_ratio", precompute_industry_crowding(data, labels=labels,
                                                 normalize="ratio")),
        ("E_pe", precompute_valuation_cap(data, dataset_dir=args.dataset,
                                          metric="pe_ttm")),
        ("E_pb", precompute_valuation_cap(data, dataset_dir=args.dataset,
                                          metric="pb")),
    ):
        panels[tag] = _panel_stats(excl, all_days, listed_by_day)
        print(f"      {tag}: 命中 {panels[tag]['hit_share']:.2%} · "
              f"收缩 p90={panels[tag]['shrink_p90']:.1%} · "
              f"最长连续 {panels[tag]['streak_max']} 日", flush=True)

    print("[4/5] 逐变体 × 逐窗口回测 ...", flush=True)
    rows: List[Dict[str, Any]] = []
    total = len(VARIANTS) * len(windows)
    for label, kwargs in VARIANTS:
        flt, fstats = build_expert_filter(
            data, market_risk=market, ind_labels=labels,
            valuation_dataset_dir=args.dataset, **kwargs)
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
            exc = (annualized_excess_arithmetic(
                [s_ret[d] - b_ret[d] for d in common], as_percent=True)
                if common else None)
            rows.append({
                "variant": label, "window": w,
                "annualized_excess_pct": round(exc, 2) if exc is not None else None,
                "trades": res.get("trades"),
                "max_drawdown_pct": res.get("max_drawdown_pct"),
                "filter_stats": fstats,
            })
            write_partial(args.out, {"rows": rows, "args": vars(args), "panels": panels},
                          note=f"已完成 {len(rows)}/{total} 个单元")
            print(f"      {label:<9} {w}  超额 {exc:+.2f}%  "
                  f"回撤 {res.get('max_drawdown_pct')}  交易 {res.get('trades')}",
                  flush=True)

    print("[5/5] 汇总 Δ（以 base 为参照）...", flush=True)
    base = next((r for r in rows if r["variant"] == "base"), None)
    deltas = []
    for label, _ in VARIANTS:
        r = next((x for x in rows if x["variant"] == label), None)
        if not r or not base:
            continue
        d_exc = (None if (r["annualized_excess_pct"] is None
                          or base["annualized_excess_pct"] is None)
                 else round(r["annualized_excess_pct"] - base["annualized_excess_pct"], 2))
        d_dd = (None if (r["max_drawdown_pct"] is None
                         or base["max_drawdown_pct"] is None)
                else round(r["max_drawdown_pct"] - base["max_drawdown_pct"], 2))
        d_trades = (None if (r["trades"] is None or base["trades"] is None)
                    else r["trades"] - base["trades"])
        deltas.append({"variant": label, "d_excess_pp": d_exc,
                       "d_max_drawdown_pp": d_dd, "d_trades": d_trades,
                       "panel": panels.get(label)})

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prereg": "EXPERT_FILTER_C2_PREREG.md §五",
        "args": vars(args),
        "rows": rows,
        "deltas_vs_base": deltas,
        "panels": panels,
        "verdict_policy": "Δ超额>0 且 Δ回撤<=0 才可纳入；15 次比较须 BH/Bonferroni 校正",
        "note": "只产数字，不做纳入判断；两个归一化口径各自报告，不得挑选",
    }
    write_final(args.out, payload)
    print(f"\n已写出 {args.out}（{time.time() - t0:.0f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
