# -*- coding: utf-8 -*-
r"""组合层研究：**尾部剔除 × 持仓分散度** 的联合效果。

## 为什么做这个

项目至今只有两个**稳健**的正向发现，且**从未联合测试**：

| 发现 | 证据 | 出处 |
|------|------|------|
| **尾部剔除** | 配对 t = +8.35 / +3.62 / +2.52（三个独立口径全部显著） | `P0_P1_EXECUTION_REPORT.md` §7.13 |
| **提高分散度降低离散度** | 跨种子标准差 17.17 → 6.12 | `CONCENTRATION_REPORT.md` / §7.17.1 |

* 尾部剔除提升**点估计**，但不改变噪声量级；
* 分散度降低**离散度**，但不提升点估计（配对检验不显著）。

**两者互补**：若"剔除尾部"提供方向、"分散度"提供精度，联合后可能得到一个
**点估计为正、且置信区间足够窄**的配置。这正是本项目一直在找的东西。

## 口径

信号 / 阈值 / 成本模型 / 窗口全部不变，只改两个维度：
`candidate_filter`（是否剔除尾部）与 `top_n`（持仓数）。

## 用法

::

    python scripts/run_combo_study.py --dataset D:/tdx_dataset_v3 \
        --out reports/combo_study.json
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

# 复用尾部剔除研究的剔除集合构造（保证口径完全一致）
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from run_tail_exclusion_study import (  # noqa: E402
    build_exclusion_maps,
    _make_filter,
)

# (标签, top_n, 单仓上限, 剔除因子)
COMBOS: List[Tuple[str, int, float, List[str]]] = [
    ("C5_V0_基线", 5, 0.250, []),
    ("C5_V2_仅尾部剔除", 5, 0.250, ["ret_20", "vol_ratio"]),
    ("C20_V0_仅分散", 20, 0.050, []),
    ("C20_V2_联合", 20, 0.050, ["ret_20", "vol_ratio"]),
    ("C30_V2_联合", 30, 0.033, ["ret_20", "vol_ratio"]),
]
DEFAULT_WINDOWS = ["2023-07-03", "2024-01-02", "2025-01-02"]


def _load(dataset: str, max_stocks: int, min_rows: int = 200
          ) -> Dict[str, List[Dict[str, Any]]]:
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                   if f.endswith(".csv") and f[:-4].isdigit())
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    data: Dict[str, List[Dict[str, Any]]] = {}
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
    return data


def _restrict_to_pit(data: Dict[str, List[Dict[str, Any]]],
                     universe: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """按 PIT 股票池快照裁剪每只股票的历史（与 tail_exclusion 口径一致）。"""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for code, bars in data.items():
        kept: List[Dict[str, Any]] = []
        ever = False
        for b in bars:
            d = str(b["date"])
            if d in universe and code not in universe[d]:
                continue
            kept.append(b)
            ever = True
        if ever:
            out[code] = kept
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="尾部剔除 × 分散度 联合研究")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--max-stocks", type=int, default=300)
    ap.add_argument("--top-frac", type=float, default=0.20)
    ap.add_argument("--threshold", type=float, default=70.0)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 100)
    print("组合层研究 · 尾部剔除 × 持仓分散度（信号/阈值/成本/窗口全部不变）")
    print("=" * 100)
    print(f"组合 {len(COMBOS)} 个 | 窗口 {len(windows)} 个 | horizon={args.horizon}\n")

    t0 = time.time()
    data = _load(args.dataset, args.max_stocks)
    print(f"股票 {len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)

    import json as _json
    with open(os.path.join(args.dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = _json.load(fh)["snapshots"]
    bench_all: List[Dict[str, Any]] = []
    with open(os.path.join(args.dataset, "benchmark.csv"), encoding="utf-8") as fh:
        import csv as _csv
        bench_all = list(_csv.DictReader(fh))
    print(f"PIT 快照 {len(universe):,} 日 | 基准 {len(bench_all):,} 根", flush=True)

    print("\n[1/2] 预计算剔除集合 ...", flush=True)
    need = sorted({f for _, _, _, facs in COMBOS for f in facs})
    excl = build_exclusion_maps(data, need, top_frac=args.top_frac) if need else {}
    for f in need:
        days = len(excl.get(f, {}))
        print(f"      {f:<12} 覆盖 {days:,} 个交易日", flush=True)

    print("\n[2/2] 逐组合 × 逐窗口回测（净收益）...", flush=True)
    rows: List[Dict[str, Any]] = []
    total = len(COMBOS) * len(windows)
    for label, top_n, pos, facs in COMBOS:
        flt = _make_filter(excl, facs)
        for w in windows:
            restricted = _restrict_to_pit(data, universe)
            bench = [b for b in bench_all if str(b["date"]) >= w]
            res = portfolio_backtest(
                restricted, universe_snapshot_map=universe,
                threshold=args.threshold, top_n=top_n, horizon=args.horizon,
                max_position_pct=pos, start_signal_date=w, candidate_filter=flt)
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
            rows.append({
                "combo": label, "top_n": top_n, "pos_pct": pos,
                "exclusions": list(facs), "window": w,
                "trades": res.get("trades"),
                "total_return_pct": res.get("total_return_pct"),
                "max_drawdown_pct": res.get("max_drawdown_pct"),
                "benchmark_return_pct": round(bm, 2),
                "annualized_excess_pct": (round(exc, 2) if exc is not None else None),
                "t_stat": st["t"], "p_value": st["p"],
            })
            write_partial(args.out, {"rows": rows, "args": vars(args)},
                          note=f"已完成 {len(rows)}/{total} 个（组合×窗口）单元")
            exc_txt = f"{exc:+.2f}" if exc is not None else "—"
            print(f"  {label:<22} {w}  交易 {res.get('trades'):>5}  "
                  f"净超额 {exc_txt:>8}%  回撤 {res.get('max_drawdown_pct')}%  "
                  f"({time.time() - t0:.0f}s)", flush=True)

    # ---- 汇总 ----
    print("\n" + "=" * 100)
    print("汇总：各组合的净年化超额（跨窗口）")
    print("=" * 100)
    print(f"{'组合':<22}{'持仓':>5}{'超额均值':>11}{'标准差':>9}{'区间跨度':>10}"
          f"{'为正窗口':>10}{'交易数均值':>11}")
    summary: Dict[str, Any] = {}
    for label, top_n, _pos, _f in COMBOS:
        rs = [r for r in rows if r["combo"] == label]
        nets = [r["annualized_excess_pct"] for r in rs
                if r["annualized_excess_pct"] is not None]
        tr = [r["trades"] for r in rs if r["trades"]]
        if not nets:
            continue
        sd = statistics.stdev(nets) if len(nets) > 1 else 0.0
        summary[label] = {
            "n_windows": len(nets), "mean": statistics.mean(nets),
            "std": sd, "range": max(nets) - min(nets),
            "positive_windows": sum(1 for v in nets if v > 0),
            "trades_mean": statistics.mean(tr) if tr else None,
            "values": nets,
        }
        print(f"{label:<22}{top_n:>5}{statistics.mean(nets):>+11.2f}{sd:>9.2f}"
              f"{max(nets) - min(nets):>10.2f}"
              f"{sum(1 for v in nets if v > 0):>7}/{len(nets)}"
              f"{(statistics.mean(tr) if tr else 0):>11.0f}")

    print("\n" + "=" * 100)
    print("声明")
    print("=" * 100)
    print("  · 信号 / 阈值 / 成本模型 / 窗口**全部不变**，只改持仓数与是否剔除尾部")
    print("  · 窗口数少（3 个），均值与标准差仅作**方向性**参考")
    print("  · ⚠️ 3 个窗口的配对检验自由度极低，**不输出显著性判定**")
    print("  · 未做参数网格搜索：组合为**事前指定的互补假设**（两个已确立发现），非扫参")
    print("  · 数据缺陷：创业板 ST 标记仅 2020 年起有值（见 HANDOVER 缺陷 C）")
    print("  · 结论不构成投资建议")

    write_final(args.out, {"rows": rows, "summary": summary,
                           "args": vars(args), "windows": windows})
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
