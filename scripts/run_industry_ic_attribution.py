# -*- coding: utf-8 -*-
r"""行业分层 IC 归因：直接检验「IC 强显著但组合不赚钱」的产业解释。

## 被检验的命题

2026-09-30 专家圆桌审查中，**产业策略师**给出的解释是：

> 「反转/波动类因子**在不同景气度的行业里方向相反** —— 景气上行行业里「高波动」是趋势延续，
> 景气下行行业里「高波动」是出逃踩踏。把全市场池在一起算 IC，得到的 −0.05
> 是**正负相抵后的残渣**。」

## 检验设计（比 Brinson 更锋利）

若该命题成立，则**同一个因子**在「行业内」的 IC 应显著强于「混合池」的 IC ——
因为混合池里方向相反的行业互相抵消。

对每个调仓日 `T`（PIT）计算两个量：

| 口径 | 定义 |
|------|------|
| **混合 IC** | 全池 `spearman(factor, fwd_ret)` |
| **行业内 IC** | 逐统计行业算 `spearman`，再按行业规模**加权平均** |

判据（事前固定）：**行业内 IC 的 \|均值\| > 混合 IC 的 \|均值\|**，
且提升幅度 ≥ 10%（相对），方支持「抵消」解释。

## ⚠️ 口径声明

- 行业标签是 `pit.statistical_industry` 的**统计行业**（收益相关性聚类），
  **不是官方行业** —— 结论必须带此限制
- 聚类用**剔除市场因子后的残差收益**（否则会链式坍缩成 1~2 个巨簇）
- 全部只用 `T` 及之前的数据（PIT）

## 用法

::

    python scripts/run_industry_ic_attribution.py --dataset D:/tdx_dataset_v3 \
        --max-stocks 300 --out reports/industry_ic_attribution.json
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_artifacts import write_final, write_partial  # noqa: E402
from real_alpha_pipeline import load_certified_csv  # noqa: E402
from factors.factor_ic_lab import MIN_HISTORY, compute_factors, spearman  # noqa: E402
from pit.statistical_industry import (  # noqa: E402
    DEFAULT_LOOKBACK, DEFAULT_N_CLUSTERS, DEFAULT_RECLUSTER_EVERY,
    build_statistical_industry,
)

FACTORS = ("ret_20", "vol_20", "max_ret_20", "log_amount_20", "amihud_20")
HORIZON = 20
STEP = 20                       # 不重叠
MIN_CLUSTER_SIZE = 5            # 簇内少于该数不算行业内 IC
MIN_IMPROVEMENT_PCT = 10.0      # 判据：提升 ≥ 10%


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
    ap = argparse.ArgumentParser(description="行业分层 IC 归因")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=300)
    ap.add_argument("--n-clusters", type=int, default=DEFAULT_N_CLUSTERS)
    ap.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK)
    ap.add_argument("--recluster-every", type=int, default=DEFAULT_RECLUSTER_EVERY)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    print("=" * 100)
    print("行业分层 IC 归因 · 检验「因子在不同行业方向相反 → 混算是残渣」")
    print("=" * 100)
    t0 = time.time()
    data = _load(args.dataset, args.max_stocks)
    print(f"股票 {len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)

    print("\n[1/3] 统计行业聚类（PIT，剔除市场因子）...", flush=True)
    labels = build_statistical_industry(
        data, lookback=args.lookback, recluster_every=args.recluster_every,
        n_clusters=args.n_clusters)
    days_lab = sorted(labels)
    print(f"      覆盖 {len(days_lab):,} 个交易日（{time.time() - t0:.0f}s）", flush=True)

    print("\n[2/3] 逐调仓日计算两口径 IC ...", flush=True)
    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    all_days = sorted({str(b["date"]) for bars in data.values() for b in bars})
    rebal = all_days[::STEP]
    rows: List[Dict[str, Any]] = []
    for day in rebal:
        lab = labels.get(day)
        if not lab:
            continue
        pooled: Dict[str, List[Tuple[float, float]]] = {f: [] for f in FACTORS}
        by_cluster: Dict[int, Dict[str, List[Tuple[float, float]]]] = {}
        for code, bars in data.items():
            i = idx_map[code].get(day)
            if i is None or i < MIN_HISTORY:
                continue
            fac = compute_factors(bars, i)
            if fac is None:
                continue
            fwd_i = i + HORIZON
            if fwd_i >= len(bars):
                continue
            c0, c1 = float(bars[i]["close"]), float(bars[fwd_i]["close"])
            if c0 <= 0:
                continue
            fwd = c1 / c0 - 1.0
            cid = lab.get(code)
            for f in FACTORS:
                v = fac.get(f)
                if v is None or v != v:
                    continue
                pooled[f].append((v, fwd))
                if cid is not None:
                    by_cluster.setdefault(cid, {f: [] for f in FACTORS})[f].append((v, fwd))

        rec: Dict[str, Any] = {"day": day, "n_stocks": len(pooled[FACTORS[0]]),
                               "n_clusters": len(by_cluster)}
        for f in FACTORS:
            xs = [p[0] for p in pooled[f]]
            ys = [p[1] for p in pooled[f]]
            ic_pool = spearman(xs, ys) if len(xs) >= 50 else None
            # 行业内 IC：按簇规模加权平均
            tot_w = 0
            acc = 0.0
            for _cid, d in by_cluster.items():
                pairs = d.get(f) or []
                if len(pairs) < MIN_CLUSTER_SIZE:
                    continue
                ic_c = spearman([p[0] for p in pairs], [p[1] for p in pairs])
                if ic_c is None:
                    continue
                acc += ic_c * len(pairs)
                tot_w += len(pairs)
            ic_ind = (acc / tot_w) if tot_w else None
            rec[f"{f}_pooled"] = ic_pool
            rec[f"{f}_industry"] = ic_ind
        rows.append(rec)
        if len(rows) % 10 == 0:
            write_partial(args.out, {"rows": rows, "args": vars(args)},
                          note=f"已完成 {len(rows)} 个调仓日")
    print(f"      完成 {len(rows)} 个调仓日（{time.time() - t0:.0f}s）", flush=True)

    print("\n[3/3] 汇总", flush=True)
    print(f"{'因子':<16}{'混合IC均值':>12}{'行业内IC均值':>14}{'提升':>10}{'判定':>12}")
    summary: Dict[str, Any] = {}
    for f in FACTORS:
        p = [r[f"{f}_pooled"] for r in rows if r.get(f"{f}_pooled") is not None]
        q = [r[f"{f}_industry"] for r in rows if r.get(f"{f}_industry") is not None]
        if not p or not q:
            continue
        mp, mq = statistics.mean(p), statistics.mean(q)
        imp = (abs(mq) / abs(mp) - 1) * 100 if mp else None
        verdict = ("支持抵消解释" if (imp is not None and imp >= MIN_IMPROVEMENT_PCT)
                   else "不支持")
        summary[f] = {"pooled_mean": mp, "industry_mean": mq,
                      "improvement_pct": imp, "verdict": verdict,
                      "n_pooled": len(p), "n_industry": len(q)}
        print(f"{f:<16}{mp:>+12.4f}{mq:>+14.4f}"
              f"{(f'{imp:+.1f}%' if imp is not None else '—'):>10}{verdict:>12}")

    print("\n" + "=" * 100)
    print("声明")
    print("=" * 100)
    print("  · 行业标签是**统计行业**（收益相关性聚类），**不是官方行业** —— 结论须带此限制")
    print("  · 聚类用**剔除市场因子后的残差收益**（否则链式坍缩成 1~2 个巨簇）")
    print("  · 判据事前固定：行业内 IC 提升 ≥ 10% 才支持「抵消」解释")
    print("  · 全部只用 T 及之前数据（PIT）；调仓日不重叠（step=horizon）")
    print("  · 结论不构成投资建议")

    write_final(args.out, {"rows": rows, "summary": summary, "args": vars(args)})
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
