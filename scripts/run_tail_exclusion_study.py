# -*- coding: utf-8 -*-
"""尾部剔除实验：把因子结论转化为**事前设定**的单一修改并检验。

## 事前设定的变体（非网格搜索）

诊断已证明：基线策略选股落在 `ret_5` 的 0.863 分位、`ret_20` 的 0.801 分位，
即精确买在负 IC 因子的最差尾部。据此设定：

| 变体 | 修改 | 依据 |
|------|------|------|
| **V0** | 无（对照组） | — |
| **V1** | 剔除 `ret_20` 最高 20% 的候选 | 选股分位 0.801；`ret_20` IC=-0.055 (t=-5.59) |
| **V2** | V1 + 剔除 `vol_ratio` 最高 20% | 选股分位 0.711；`vol_ratio` IC=-0.035 (t=-5.46) |

**只做这三个**，不扫参数、不调阈值、不改持仓周期。每个变体都有明确的因子证据支撑。

## 成本处理

小盘/低流动性组的价差相当部分是流动性补偿，必须做成本对照，因此每个变体跑两遍：

- **净收益**：使用项目真实成本模型（佣金 + 印花税 + 流动性感知滑点）
- **毛收益**：零成本（monkeypatch 掉 `dynamic_slippage` 与 `Costs`）

毛净差额即**成本拖累**，这是判断改进是否真实可用的关键。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from itertools import pairwise
from typing import Any, Dict, List, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _study_common import make_filter as _make_filter  # noqa: E402 — P2 收敛（审计 §3.1 #13）
from factors.factor_ic_lab import MIN_HISTORY, compute_factors  # noqa: E402
from research_artifacts import write_final, write_partial  # noqa: E402
from alpha.alpha_survival_lab import (  # noqa: E402
    annualized_excess_arithmetic,
    excess_t_statistics,
)

# 变体定义：剔除哪些因子的最高分位
VARIANTS: Dict[str, List[str]] = {
    "V0_baseline": [],
    "V1_excl_ret20_top20": ["ret_20"],
    "V2_excl_ret20_volratio_top20": ["ret_20", "vol_ratio"],
}
DEFAULT_WINDOWS = ["2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02", "2025-07-01"]


def _cost_drag_window(windows: Sequence[str]) -> str:
    """成本拖累对照所用的窗口 —— 取**实际跑过的第一个窗口**。

    原实现把 `"2024-01-02"` 硬编码进 `next(...)`，当 `--windows` 不含该日期时
    （例如只跑单窗口 `--windows 2023-07-03`）直接抛 `StopIteration`，
    使整个研究在最后一步崩溃 —— 前面几十分钟的计算全部作废。

    现改为从实参推导；空列表显式报 `ValueError`，而非让它以 `IndexError`
    的形式在下游冒出来。
    """
    if not windows:
        raise ValueError("--windows 为空，无法确定成本拖累对照窗口")
    return windows[0]


def _load(dataset: str, max_stocks: int, universe_only: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """加载股票池。

    universe_only=True（默认）：只从 PIT 股票池取码 —— 与 `run_tdx_evaluation.py`
        和 `run_tdx_rolling_eval.py` 保持一致，结果可直接比较。

    universe_only=False：从目录全部 CSV 取码。目录中可能残留早前构建的文件，
        抽样结果会混入非池代码，**仅用于稳健性交叉验证，不要与其它实验直接比绝对水平**。
    """
    from real_alpha_pipeline import load_certified_csv
    stock_dir = os.path.join(dataset, "stocks")

    if universe_only:
        uni_path = os.path.join(dataset, "pit_universe.json")
        with open(uni_path, encoding="utf-8") as fh:
            snaps = json.load(fh)["snapshots"]
        pool = set()
        for v in snaps.values():
            pool.update(v)
        codes = sorted(c for c in pool
                       if os.path.exists(os.path.join(stock_dir, f"{c}.csv"))
                       and os.path.exists(os.path.join(stock_dir, f"{c}.metadata.json")))
    else:
        codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))

    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]

    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if os.path.exists(p) and os.path.exists(m):
            data[c] = load_certified_csv(p, m)
    return data


def build_exclusion_maps(
    data: Dict[str, List[Dict[str, Any]]],
    factors: Sequence[str],
    *,
    top_frac: float = 0.20,
    min_cross_section: int = 50,
) -> Dict[str, Dict[str, set]]:
    """预计算：每个因子、每个交易日，处于最高 top_frac 分位的股票集合。

    返回 {factor: {day: set(codes)}}。**只看当日及之前的数据**，无未来函数。
    """
    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    dates: set = set()
    for bars in data.values():
        dates.update(str(b["date"]) for b in bars if b.get("date"))
    panel = sorted(dates)

    out: Dict[str, Dict[str, set]] = {f: {} for f in factors}
    for day in panel:
        vals: Dict[str, List[Tuple[str, float]]] = {f: [] for f in factors}
        for code, bars in data.items():
            i = idx_map[code].get(day)
            if i is None or i < MIN_HISTORY:
                continue
            fac = compute_factors(bars, i)
            if fac is None:
                continue
            for f in factors:
                vals[f].append((code, fac[f]))
        for f in factors:
            pairs = vals[f]
            if len(pairs) < min_cross_section:
                continue
            pairs.sort(key=lambda t: t[1])
            cut = int(len(pairs) * (1 - top_frac))
            out[f][day] = {c for c, _ in pairs[cut:]}
    return out


def _zero_cost_patch():
    """临时把成本模型置零，用于取得毛收益。

    注意：`portfolio_backtest` 用 `from ... import` 绑定了自己的引用，
    因此必须打补丁到 **该模块**，改 `backtest_engine` / `liquidity` 无效。
    """
    import portfolio_backtest as pb
    orig = (pb._trade_cost, pb.dynamic_slippage)
    # _trade_cost 现支持可选的第 4 参 trade_date（印花税分段），用 *args 兼容
    pb._trade_cost = lambda *args, **kwargs: 0.0
    pb.dynamic_slippage = lambda *args, **kwargs: 0.0
    return orig


def _restore(orig) -> None:
    import portfolio_backtest as pb
    pb._trade_cost, pb.dynamic_slippage = orig


def main() -> int:
    ap = argparse.ArgumentParser(description="尾部剔除实验（事前设定，非网格搜索）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=400)
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--top-frac", type=float, default=0.20)
    ap.add_argument("--top-n", type=int, default=5,
                    help="同时持仓上限（C20 分散实验取 20）")
    ap.add_argument("--position-pct", type=float, default=0.25,
                    help="单仓占初始资金上限（C20 分散实验取 0.05）")
    ap.add_argument("--benchmark", default="",
                    help="基准 CSV（默认 <dataset>/benchmark.csv；"
                         "等权基准用 D:/tdx_dataset_v2/benchmark_ew.csv）")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--all-csv", action="store_true",
                    help="从目录全部 CSV 取码（含早前残留），仅用于稳健性交叉验证")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]
    all_factors = sorted({f for fs in VARIANTS.values() for f in fs})

    print("=" * 108)
    print("尾部剔除实验 · 事前设定变体（不扫参数、不改阈值、不改持仓周期）")
    print("=" * 108)

    t0 = time.time()
    data = _load(dataset, args.max_stocks, universe_only=not args.all_csv)
    print(f"股票 {len(data):,} 只，共 {sum(len(v) for v in data.values()):,} 行  "
          f"({time.time()-t0:.0f}s)")

    print(f"[1/3] 预计算剔除集合（{all_factors}，最高 {args.top_frac:.0%}）...")
    excl = build_exclusion_maps(data, all_factors, top_frac=args.top_frac)
    for f in all_factors:
        days = len(excl[f])
        avg = (sum(len(v) for v in excl[f].values()) / days) if days else 0
        print(f"      {f:12s} 覆盖 {days} 个交易日，日均剔除 {avg:.0f} 只")
    print(f"      ({time.time()-t0:.0f}s)")

    from historical_universe import point_in_time_universe
    from portfolio_backtest import portfolio_backtest
    from real_alpha_pipeline import _curve_returns

    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as fh:
        universe = json.load(fh)["snapshots"]
    import csv as _csv
    bench_path = args.benchmark or os.path.join(dataset, "benchmark.csv")
    with open(bench_path, encoding="utf-8") as fh:
        bench_all = list(_csv.DictReader(fh))
    print(f"      基准: {os.path.basename(bench_path)}")

    print("[2/3] 逐变体 × 逐窗口回测（净收益）...")
    rows: List[Dict[str, Any]] = []
    for vname, facs in VARIANTS.items():
        flt = _make_filter(excl, facs)
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
            bench = [b for b in bench_all if b["date"] >= w]
            res = portfolio_backtest(restricted, universe_snapshot_map=universe,
                                     threshold=70, top_n=args.top_n,
                                     max_position_pct=args.position_pct,
                                     horizon=args.horizon,
                                     start_signal_date=w, candidate_filter=flt)
            s_ret = _curve_returns(res.get("equity_curve", []))
            b_ret = {b["date"]: 0.0 for b in bench}
            for a, b in pairwise(bench):
                if float(a["close"]) > 0:
                    b_ret[b["date"]] = float(b["close"]) / float(a["close"]) - 1
            common = sorted(set(s_ret) & set(b_ret))
            bm = (float(bench[-1]["close"]) / float(bench[0]["close"]) - 1) * 100 if bench else 0.0
            # 先物化为列表：既算年化，也算 t/p（统计量必须一并落盘）
            excess = [s_ret[d] - b_ret[d] for d in common]
            exc = annualized_excess_arithmetic(excess, as_percent=True)
            st = excess_t_statistics(excess)
            rows.append({"variant": vname, "window": w, "aligned": len(common),
                         "trades": res.get("trades"),
                         "win_rate_pct": res.get("win_rate_pct"),
                         "total_return_pct": res.get("total_return_pct"),
                         "max_drawdown_pct": res.get("max_drawdown_pct"),
                         "benchmark_return_pct": round(bm, 2),
                         "annualized_excess_pct": round(exc, 2),
                         "t_stat": st["t"], "p_value": st["p"]})
            # 增量落盘：本实验约 1~2 小时，进程可能静默死亡（见 research_artifacts）
            write_partial(args.out, {"rows": rows, "args": vars(args)},
                          note=f"已完成 {len(rows)} 个（变体×窗口）单元")
            print(f"  {vname:30s} {w}  交易 {res.get('trades'):>4}  "
                  f"收益 {res.get('total_return_pct'):>8}%  "
                  f"基准 {bm:>7.2f}%  年化超额 {exc:>+7.2f}%  ({time.time()-t0:.0f}s)",
                  flush=True)

    # 成本拖累对照：用**实际跑过的第一个窗口**，而不是硬编码 2024-01-02。
    # 原实现硬编码该窗口，当 `--windows` 不含它时会在 next(...) 处抛 StopIteration。
    cost_window = _cost_drag_window(windows)
    print(f"\n[3/3] 成本拖累对照（V0 与 V1，窗口 {cost_window}）...")
    orig = _zero_cost_patch()
    cost_rows = []
    try:
        for vname in ("V0_baseline", "V1_excl_ret20_top20"):
            flt = _make_filter(excl, VARIANTS[vname])
            w = cost_window
            oos_dates = sorted({str(b["date"]) for bars in data.values()
                                for b in bars if str(b["date"]) >= w})
            allowed = {d: set(point_in_time_universe(universe, d)) for d in oos_dates}
            restricted = {}
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
            g = portfolio_backtest(restricted, universe_snapshot_map=universe,
                                   threshold=70, top_n=args.top_n,
                                   max_position_pct=args.position_pct,
                                   horizon=args.horizon,
                                   start_signal_date=w, candidate_filter=flt)
            net_row = next((r for r in rows
                            if r["variant"] == vname and r["window"] == w), None)
            if net_row is None:
                print(f"  {vname:30s} 该窗口无净收益记录，跳过")
                continue
            net = net_row
            cost_rows.append({"variant": vname, "gross_pct": g.get("total_return_pct"),
                              "net_pct": net["total_return_pct"],
                              "drag_pct": round((g.get("total_return_pct") or 0)
                                                - (net["total_return_pct"] or 0), 2),
                              "gross_trades": g.get("trades")})
            print(f"  {vname:30s} 毛 {g.get('total_return_pct'):>8}%  "
                  f"净 {net['total_return_pct']:>8}%  "
                  f"成本拖累 {cost_rows[-1]['drag_pct']:>+7.2f}pp", flush=True)
    finally:
        _restore(orig)

    print("\n" + "=" * 108)
    print("汇总：各变体的年化超额（净收益口径）")
    print("=" * 108)
    print(f"{'变体':32s} {'均值':>9s} {'中位数':>9s} {'为正窗口':>9s} {'最差':>9s} {'最好':>9s}")
    print("-" * 108)
    summary = {}
    for vname in VARIANTS:
        e = [r["annualized_excess_pct"] for r in rows if r["variant"] == vname]
        if not e:
            continue
        s = {"mean": statistics.mean(e), "median": statistics.median(e),
             "positive": sum(1 for x in e if x > 0), "min": min(e), "max": max(e)}
        summary[vname] = s
        print(f"{vname:32s} {s['mean']:>+9.2f} {s['median']:>+9.2f} "
              f"{s['positive']:>5}/{len(e):<3} {s['min']:>+9.2f} {s['max']:>+9.2f}")

    print()
    print("-" * 108)
    print("逐窗口明细")
    print("-" * 108)
    print(f"{'变体':32s} {'窗口':12s} {'交易':>5s} {'胜率':>7s} {'收益%':>9s} "
          f"{'基准%':>8s} {'回撤%':>8s} {'年化超额%':>10s}")
    for r in rows:
        print(f"{r['variant']:32s} {r['window']:12s} {r['trades']:>5} "
              f"{r['win_rate_pct']:>7} {r['total_return_pct']:>9} "
              f"{r['benchmark_return_pct']:>8} {r['max_drawdown_pct']:>8} "
              f"{r['annualized_excess_pct']:>+10.2f}")

    print()
    print("声明：本实验未扫参数；数据缺陷以数据集 evidence.json 为准"
          "（v3 已消除幸存者偏差与不复权两项），")
    print("      结果仅反映该改动在此数据集上的表现，不构成投资结论。")

    if args.out:
        # 2026-10-14 A2 合并：主干侧原为裸 json.dump 结尾（含 10-06 增补的
        # 「生效基准路径」benchmark 字段）；本侧纪律是 write_final（原子写）。
        # 合并 = write_final 落盘 + 保留 benchmark 字段（基准口径留痕）。
        write_final(args.out, {"rows": rows, "summary": summary,
                               "cost_comparison": cost_rows,
                               "variants": VARIANTS, "args": vars(args),
                               # 生效基准路径（2026-10-06 增补）
                               "benchmark": bench_path})
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
