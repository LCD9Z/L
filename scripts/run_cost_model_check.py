# -*- coding: utf-8 -*-
"""成本模型修正的敏感性检查（真实 TDX 数据，观察性对照）。

2026-09-19 成本模型修正内容（出处见 backtest_engine.py 顶部注释）：
  1. 新增过户费 0.01‰ 双向（中国结算 2022-04-29 起，沪深两市均收）；
  2. 印花税按交易日分段：2023-08-28 前卖出 1‰，之后 0.5‰
     （财政部/税务总局 2023-08-28 减半征收公告）。

本脚本回答一个问题：这两项修正对基线策略的回测结论改变多大？

对照设计（同一数据、同一信号、只换成本模型）：
  - legacy：无过户费、全程 0.5‰ 印花税（修正前的 Cost 模型）
  - new   ：现行默认 Costs()（过户费 + 分段印花税）

窗口选择：2023-07-03（跨 2023-08-28 生效日，分段计费真实生效）
          与 2024-01-02（全在新税率区，理论上只差过户费）。

声明：本脚本只测量成本口径变化的敏感性，不构成策略有效性结论；
数据存在幸存者偏差与不复权两项已知缺陷（见 DATASET_PROFILE.md）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research_artifacts import write_final, write_partial  # noqa: E402

DEFAULT_WINDOWS = ["2023-07-03", "2024-01-02"]

# 修正前的成本模型：无过户费、印花税全程按现行税率（不分段）
LEGACY_COSTS_KWARGS: Dict[str, Any] = {
    "transfer_fee_rate": 0.0, "stamp_duty_change_date": "0001-01-01",
}

def _load_universe(dataset: str) -> Dict[str, List[str]]:
    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as f:
        return json.load(f)["snapshots"]


def _load_manifest(dataset: str, max_stocks: int, min_rows_asset: int = 0) -> Dict[str, Any]:
    stock_dir = os.path.join(dataset, "stocks")
    in_universe = set()
    for v in _load_universe(dataset).values():
        in_universe.update(v)
    codes = sorted(
        c for c in in_universe
        if os.path.exists(os.path.join(stock_dir, f"{c}.csv"))
        and os.path.exists(os.path.join(stock_dir, f"{c}.metadata.json"))
    )
    if min_rows_asset > 0:
        # 认证审计要求每只资产 >= min_rows_per_asset；不预过滤会在 preflight 直接失败
        kept, excluded = [], 0
        for c in codes:
            mp = os.path.join(stock_dir, f"{c}.metadata.json")
            try:
                with open(mp, encoding="utf-8") as f:
                    rows = int(json.load(f).get("rows", 0))
            except (OSError, ValueError):
                rows = 0
            if rows >= min_rows_asset:
                kept.append(c)
            else:
                excluded += 1
        codes = kept
        print(f"  行数预过滤: 保留 {len(codes)} 只，排除短历史 {excluded} 只"
              f"（< {min_rows_asset} 行）")
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    return {
        "files": {c: os.path.join(stock_dir, f"{c}.csv") for c in codes},
        "metas": {c: os.path.join(stock_dir, f"{c}.metadata.json") for c in codes},
        "codes": codes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="成本模型修正敏感性检查（legacy vs new）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=400)
    ap.add_argument("--min-periods", type=int, default=252)
    ap.add_argument("--min-rows-asset", type=int, default=0,
                    help="按 metadata 行数预过滤资产（需通过审计时取 min-periods*2）")
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    from backtest_engine import Costs

    print("=" * 96)
    print("成本模型敏感性检查 · 同数据同信号，只换成本模型（legacy=修正前口径）")
    print("=" * 96)

    man = _load_manifest(dataset, args.max_stocks, args.min_rows_asset)
    man = _load_manifest(dataset, args.max_stocks)
    print(f"股票池: {len(man['codes']):,} 只")

    print("[1/3] 一次性审计（sha256 + 全量行校验）...")
    from professional_audit import audit_research_evidence
    bench = os.path.join(dataset, "benchmark.csv")
    bench_meta = os.path.join(dataset, "benchmark.metadata.json")
    pre = audit_research_evidence(man["files"], man["metas"], bench, bench_meta,
                                  min_assets=2, min_rows_per_asset=args.min_periods * 2)
    print(f"      preflight: {pre['verdict']}")
    if pre["verdict"] != "PASS":
        print(f"      阻断项 {len(pre['issues'])} 个，前 5: {pre['issues'][:5]}")
        return 2

    print("[2/3] 加载数据（只读一次）...")
    from real_alpha_pipeline import load_certified_csv
    data: Dict[str, List[dict]] = {}
    for code, path in man["files"].items():
        data[code] = load_certified_csv(path, man["metas"].get(code))
    benchmark = load_certified_csv(bench, bench_meta)
    print(f"      已加载 {len(data):,} 只，共 {sum(len(v) for v in data.values()):,} 行")

    print(f"[3/3] 逐窗口对照（{len(windows)} 个窗口 × 2 种成本模型）...\n")
    from portfolio_backtest import portfolio_backtest
    from alpha.alpha_survival_lab import analyse_alpha
    from historical_universe import point_in_time_universe
    from real_alpha_pipeline import _benchmark_returns, _curve_returns

    universe = _load_universe(dataset)
    cost_models = {
        "legacy": Costs(**LEGACY_COSTS_KWARGS),
        "new": Costs(),
    }
    rows: List[Dict[str, Any]] = []

    for oos_start in windows:
        oos_dates = sorted({str(b["date"]) for bars in data.values()
                            for b in bars if str(b["date"]) >= oos_start})
        allowed_oos = {d: set(point_in_time_universe(universe, d)) for d in oos_dates}
        restricted: Dict[str, List[dict]] = {}
        for code, bars in data.items():
            kept, ever = [], False
            for b in bars:
                d = str(b["date"])
                if d >= oos_start and code not in allowed_oos.get(d, set()):
                    continue
                kept.append(b)
                if d >= oos_start:
                    ever = True
            if ever:
                restricted[code] = kept
        bench_oos = [b for b in benchmark if str(b["date"]) >= oos_start]

        rec: Dict[str, Any] = {"oos_start": oos_start, "assets": len(restricted)}
        for name, costs in cost_models.items():
            result = portfolio_backtest(restricted, costs=costs,
                                        universe_snapshot_map=universe,
                                        threshold=70, top_n=5, horizon=5,
                                        start_signal_date=oos_start)
            s_ret = _curve_returns(result.get("equity_curve", []))
            b_ret = _benchmark_returns(bench_oos)
            common = sorted(set(s_ret) & set(b_ret))
            entry: Dict[str, Any] = {
                "total_return_pct": result.get("total_return_pct"),
                "max_drawdown_pct": result.get("max_drawdown_pct"),
                "trades": result.get("trades"),
            }
            if len(common) >= args.min_periods:
                a = analyse_alpha({d: s_ret[d] for d in common},
                                  {d: b_ret[d] for d in common},
                                  min_periods=args.min_periods)
                entry["annualized_excess"] = a.get("annualized_excess_estimate")
                # 统计量一并落盘（见 2026-09-22 的教训）
                entry["t_stat"] = a.get("t_stat_normal_approx")
                entry["p_value"] = a.get("normal_approx_pvalue")
            rec[name] = entry
        # 增量落盘：多窗口 × 2 种成本模型，进程可能静默死亡（见 research_artifacts）
        write_partial(args.out, {"windows": rows, "args": vars(args)},
                      note=f"已完成 {len(rows)} 个窗口")

        if rec["legacy"].get("annualized_excess") is not None \
                and rec["new"].get("annualized_excess") is not None:
            rec["excess_delta_pp"] = round(
                (rec["new"]["annualized_excess"] - rec["legacy"]["annualized_excess"]) * 100, 3)
        rows.append(rec)

        print(f"  {oos_start}  legacy: 策略 {rec['legacy']['total_return_pct']:>8}%  "
              f"年化超额 {rec['legacy'].get('annualized_excess', 0):>8.2%}  |  "
              f"new: 策略 {rec['new']['total_return_pct']:>8}%  "
              f"年化超额 {rec['new'].get('annualized_excess', 0):>8.2%}  |  "
              f"Δ超额 {rec.get('excess_delta_pp', 0):+.3f}pp",
              flush=True)

    print("\n" + "=" * 96)
    print("结论口径")
    print("=" * 96)
    deltas = [r["excess_delta_pp"] for r in rows if r.get("excess_delta_pp") is not None]
    if deltas:
        print(f"  年化超额变化（new - legacy）: {['%+.3f' % d for d in deltas]} pp")
        print(f"  中位数: {sorted(deltas)[len(deltas)//2]:+.3f}pp")
    print("  说明：过户费单边 0.01‰、印花税分段只影响 2023-08-28 前的卖出，")
    print("        对结果的改变属于成本口径校准，量级应以本表实测为准。")
    print("  声明：本检查不构成策略有效性结论；数据存在幸存者偏差与不复权两项缺陷。")

    if args.out:
        # 2026-10-14 A2 合并：主干侧原为裸 json.dump 结尾（含 10-06 增补的
        # 「生效基准路径」benchmark 字段）；本侧纪律是 write_final（原子写）。
        # 合并 = write_final 落盘 + 保留 benchmark 字段（基准口径留痕）。
        write_final(args.out, {"windows": rows, "cost_models": {
                k: dict(vars(v)) for k, v in cost_models.items()},
                "args": vars(args),
                # 生效基准路径（2026-10-06 增补）：默认为 benchmark.csv 即沪深300
                "benchmark": bench})
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
