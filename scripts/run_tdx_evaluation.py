# -*- coding: utf-8 -*-
"""在 TDX 数据集上运行真实 Alpha 评估。

用法::

    python run_tdx_evaluation.py --dataset D:/tdx_dataset --oos-start 2024-01-01
    python run_tdx_evaluation.py --dataset D:/tdx_dataset --max-stocks 800

## 本脚本的定位

把 `real_alpha_pipeline` 真正跑在真实历史数据上，用于**验证工程链路**并观察
因子在真实数据上的行为。**不是投资结论** —— 数据本身存在两项会直接扭曲结果的缺陷：

1. **幸存者偏差**：数据集不含退市股，回测结果系统性偏乐观
2. **不复权价**：跨除权跳空会污染趋势类因子

因此无论输出 SUPPORTED 还是 NOT_SUPPORTED，都**不能**据此判断策略是否有效。
报告会显式标注这两点。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_manifest(dataset: str, max_stocks: int = 0) -> Dict[str, Any]:
    """读取数据集清单，返回 {code: csv_path} 与元数据路径映射。

    **以 PIT 股票池为准**取代码，而不是目录里所有 .csv ——
    这样即使目录中存在上一次构建的残留文件，也不会污染本次评估。
    """
    stock_dir = os.path.join(dataset, "stocks")
    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as f:
        snaps = json.load(f)["snapshots"]
    in_universe = set()
    for v in snaps.values():
        in_universe.update(v)

    codes = sorted(
        c for c in in_universe
        if os.path.exists(os.path.join(stock_dir, f"{c}.csv"))
        and os.path.exists(os.path.join(stock_dir, f"{c}.metadata.json"))
    )
    if max_stocks > 0 and len(codes) > max_stocks:
        # 确定性等距抽样，避免"取前 N 只"带来的代码段偏差
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    files = {c: os.path.join(stock_dir, f"{c}.csv") for c in codes}
    metas = {c: os.path.join(stock_dir, f"{c}.metadata.json") for c in codes}
    return {"files": files, "metas": metas, "codes": codes,
            "in_universe": len(in_universe)}


def _load_universe(dataset: str) -> Dict[str, List[str]]:
    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as f:
        return json.load(f)["snapshots"]


def _summarize_rows(dataset: str, codes: List[str]) -> Dict[str, Any]:
    """统计抽样股票池的规模与日期覆盖。"""
    lo, hi, total = "9999", "0000", 0
    for c in codes:
        p = os.path.join(dataset, "stocks", f"{c}.csv")
        with open(p, encoding="utf-8") as f:
            rd = csv.DictReader(f)
            first = last = None
            for r in rd:
                total += 1
                if first is None:
                    first = r["date"]
                last = r["date"]
        if first and first < lo:
            lo = first
        if last and last > hi:
            hi = last
    return {"stocks": len(codes), "rows": total, "first": lo, "last": hi}


def main() -> int:
    ap = argparse.ArgumentParser(description="TDX 数据集上的真实 Alpha 评估")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--oos-start", default="2024-01-01")
    ap.add_argument("--max-stocks", type=int, default=800,
                    help="参与评估的股票数（0=全部；默认 800 以控制内存）")
    ap.add_argument("--min-periods", type=int, default=252)
    ap.add_argument("--out", default="", help="结果 JSON 输出路径")
    ap.add_argument(
        "--survivorship-evidence", default="",
        help="研究完整性证据清单 JSON（键名见 release_gate.EVIDENCE_KEYS）。"
             "未提供时视为全部缺失，Alpha 结论会被门禁降级为 INCONCLUSIVE。")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    print("=" * 78)
    print("TDX 数据集 · 真实 Alpha 评估")
    print("=" * 78)

    man = _load_manifest(dataset, args.max_stocks)
    codes = man["codes"]
    if not codes:
        print("!! 数据集中无可用股票，请先运行 build_tdx_dataset.py")
        return 2

    stats = _summarize_rows(dataset, codes)
    print(f"股票池      : {stats['stocks']:,} 只（等距抽样）")
    print(f"总行数      : {stats['rows']:,}")
    print(f"日期覆盖    : {stats['first']} ~ {stats['last']}")
    print(f"样本外起点  : {args.oos_start}")

    bench = os.path.join(dataset, "benchmark.csv")
    bench_meta = os.path.join(dataset, "benchmark.metadata.json")
    if not os.path.exists(bench):
        print("!! 缺少 benchmark.csv")
        return 2

    universe = _load_universe(dataset)
    print(f"PIT 快照数  : {len(universe):,}")

    from real_alpha_pipeline import run_real_alpha_pipeline
    from release_gate import load_survivorship_evidence

    print("\n运行 real_alpha_pipeline ...")
    result = run_real_alpha_pipeline(
        man["files"], bench, args.oos_start,
        metadata_files=man["metas"], benchmark_metadata=bench_meta,
        min_periods=args.min_periods,
        universe_snapshot_map=universe,
        survivorship_evidence=load_survivorship_evidence(
            args.survivorship_evidence or None),
    )

    print("\n" + "=" * 78)
    print(f"结论: {result.get('verdict')}")
    if result.get("reason"):
        print(f"原因: {result['reason']}")
    print("=" * 78)

    # 研究完整性门禁：把「统计结论」与「可发布结论」分开显示。
    # 二者混为一谈会把「证据不足」误读成「策略不行」——这是最容易发生的误读。
    if result.get("statistical_verdict"):
        print(f"\n统计结论  : {result['statistical_verdict']}")
        print(f"可发布结论: {result.get('verdict')}"
              f"（alpha_status={result.get('alpha_status')}）")
        missing = result.get("missing_evidence") or []
        if missing:
            print(f"尚缺证据（{len(missing)}）:")
            for m in missing:
                print(f"  - {m}")

    # 门禁失败时必须给出可定位的原因，而不是只报一个 verdict
    pre = result.get("preflight")
    if pre:
        issues = pre.get("issues") or []
        print(f"\npreflight 结论: {pre.get('verdict')}")
        if issues:
            print(f"阻断项（{len(issues)}）:")
            for it in issues[:40]:
                print(f"  - {it}")
            if len(issues) > 40:
                print(f"  ... 另有 {len(issues) - 40} 项")
        base = pre.get("base") or {}
        reports = base.get("reports") or {}
        bad = {k: v for k, v in reports.items() if not v.get("pass")}
        if bad:
            print(f"\n未通过校验的数据集（{len(bad)} / {len(reports)}）:")
            from collections import Counter as _C
            cnt = _C(i for v in bad.values() for i in v.get("issues", []))
            for iss, n in cnt.most_common(12):
                print(f"  {iss:38s} 影响 {n} 个文件")
            for k, v in list(bad.items())[:8]:
                print(f"    例: {k} rows={v.get('rows')} issues={v.get('issues')}")
        if pre.get("hard_rule"):
            print(f"\n门禁硬规则: {pre['hard_rule']}")

    if result.get("detail"):
        print(f"\n细节: {result['detail']}")
    if result.get("missing_stock_oos"):
        print(f"\n缺失样本外的股票数: {len(result['missing_stock_oos'])}")
    if result.get("aligned_periods") is not None:
        print(f"对齐期数: {result['aligned_periods']} / 要求 {result.get('required_min_periods')}")

    for k in ("aligned_periods", "periods", "mean_excess_daily",
              "annualized_excess_estimate", "t_stat_normal_approx",
              "normal_approx_pvalue", "sign_flip_pvalue"):
        if k in result:
            print(f"  {k:30s}: {result[k]}")
    if result.get("bootstrap_mean_ci"):
        print(f"  {'bootstrap_mean_ci':30s}: {result['bootstrap_mean_ci']}")
    bt = result.get("backtest")
    if bt:
        print(f"  {'backtest.trades':30s}: {bt.get('trades')}")
        print(f"  {'backtest.win_rate_pct':30s}: {bt.get('win_rate_pct')}")
        print(f"  {'backtest.total_return_pct':30s}: {bt.get('total_return_pct')}")
        print(f"  {'backtest.max_drawdown_pct':30s}: {bt.get('max_drawdown_pct')}")

    print("\n" + "-" * 78)
    print("重要声明：本结果**不构成投资结论**。")
    print("  1) 数据集不含退市股 → 幸存者偏差，收益被系统性高估")
    print("  2) 价格为不复权原始价 → 除权跳空污染趋势类因子")
    print("  无论上述结论是 SUPPORTED 还是 NOT_SUPPORTED，都不能据此判断策略有效性。")
    print("-" * 78)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"args": vars(args), "stats": stats, "result": result},
                      f, ensure_ascii=False, indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
