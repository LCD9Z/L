# -*- coding: utf-8 -*-
"""多窗口滚动样本外稳健性检验。

单一 2024-01 起点的结论可能只是特定区间的偶然。本脚本在多个样本外起点上
重复评估**同一个**内置基线策略，用于回答：

    -19.43% 的年化超额是稳定特征，还是被某一小段行情带偏的结果？

## 与参数寻优的区别

本脚本**不调整任何策略参数**（阈值/TopN/周期/仓位全部固定）。
它只改变评估窗口，属于稳健性检验，不是曲线拟合。

## 效率设计

`run_real_alpha_pipeline` 每次都要对全部股票做 sha256 + 全量行解析（约 8 分钟）。
数据在各窗口之间**完全相同**，因此这里只做一次审计，之后复用已加载数据，
直接调用 `portfolio_backtest` 与 `analyse_alpha`。

用法::

    python run_tdx_rolling_eval.py --dataset D:/tdx_dataset --max-stocks 800
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 默认滚动起点：覆盖 2023-01 ~ 2025-07，保证每窗口样本外 >= 252 个交易日
DEFAULT_WINDOWS = [
    "2023-01-03", "2023-07-03", "2024-01-02",
    "2024-07-01", "2025-01-02", "2025-07-01",
]

# 统计结论的措辞，与 real_alpha_pipeline 保持一致，避免两处口径漂移
VERDICT_MAP = {
    "SUPPORTED": "ALPHA_SUPPORTED",
    "NOT_SUPPORTED": "ALPHA_NOT_ESTABLISHED",
    "INCONCLUSIVE": "INCONCLUSIVE",
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
        # 认证审计要求每只资产 ≥ min_rows_per_asset；在此按 metadata 声明的行数预过滤，
        # 并如实记录被排除的 PIT 成员数（ excluded 计数随 manifest 返回）。
        kept = []
        excluded = 0
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
              f"（< {min_rows_asset} 行，多为窗口中后期退市/新上市）")
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    return {
        "files": {c: os.path.join(stock_dir, f"{c}.csv") for c in codes},
        "metas": {c: os.path.join(stock_dir, f"{c}.metadata.json") for c in codes},
        "codes": codes,
    }


def _resolve_bench_meta(bench: str, explicit: str = "") -> str:
    """解析基准元数据路径（缺陷 #20：默认路径曾经拼错）。

    数据集里两种命名习惯**并存**：

    - `benchmark.csv`      → `benchmark.metadata.json`（去扩展名）
    - `benchmark_ew.csv`   → `benchmark_ew.csv.metadata.json`（保留 .csv）

    原实现硬编码 `bench + ".metadata.json"`，对沪深300 得到不存在的
    `benchmark.csv.metadata.json` ⇒ 审计报 `metadata_missing` ⇒ preflight
    `LIMITED_OR_FAIL`，默认参数下**直接跑不起来**（用 `--skip-audit` 则会静默绕过）。
    这里改为按候选顺序探测；`--benchmark-meta` 显式给出时优先。
    """
    if explicit:
        return explicit
    stem = os.path.splitext(bench)[0] + ".metadata.json"
    suffix = bench + ".metadata.json"
    for cand in (stem, suffix):
        if os.path.exists(cand):
            return cand
    return stem   # 都不存在时返回去扩展名的形式，让审计如实报 metadata_missing


def main() -> int:
    ap = argparse.ArgumentParser(description="多窗口滚动样本外稳健性检验")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=800)
    ap.add_argument("--min-periods", type=int, default=252)
    ap.add_argument("--min-rows-asset", type=int, default=0,
                    help="按 metadata 行数预过滤资产（默认 0=不过滤）。"
                         "需通过审计时取 min-periods*2。")
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--survivorship-evidence", default="",
        help="研究完整性证据清单 JSON（键名见 release_gate.EVIDENCE_KEYS）。"
             "未提供时视为全部缺失，Alpha 结论会被门禁降级为 INCONCLUSIVE。")
    ap.add_argument("--benchmark", default="",
                    help="基准 CSV 路径（默认 <dataset>/benchmark.csv）。"
                         "等权基准对照用：--benchmark D:/tdx_dataset_v2/benchmark_ew.csv")
    ap.add_argument("--benchmark-meta", default="",
                    help="基准 metadata 路径（默认同基准 CSV 名的 .metadata.json）")
    ap.add_argument("--skip-audit", action="store_true",
                    help="跳过 sha256 全量审计（数据集在本会话已通过时复用，会打印声明）")
    ap.add_argument("--dump-logs", action="store_true",
                    help="在每个窗口记录中附带 equity_curve 与 trade_log（只写不读，"
                         "不参与任何计算）。用于 regime 分层归因等事后切片分析；"
                         "默认关闭 ⇒ 产物键与历史版本完全一致。"
                         "见 REGIME_ATTRIBUTION_PREREG.md §三。")
    ap.add_argument("--flush-each-window", action="store_true",
                    help="每跑完一个窗口就把结果落盘（默认只在全部跑完后写一次）。"
                         "长批次被外部超时中断时，已完成的窗口不会丢。"
                         "默认关闭 ⇒ 落盘时机与历史版本一致。")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 96)
    print("多窗口滚动样本外稳健性检验 · 内置基线策略（参数完全固定，不做任何寻优）")
    print("=" * 96)

    man = _load_manifest(dataset, args.max_stocks, args.min_rows_asset)
    print(f"股票池: {len(man['codes']):,} 只")

    # ---- 一次性审计（数据在各窗口间相同，无需重复校验）----
    from professional_audit import audit_research_evidence
    bench = args.benchmark or os.path.join(dataset, "benchmark.csv")
    bench_meta = _resolve_bench_meta(bench, args.benchmark_meta)
    print(f"\n[1/3] 一次性审计（sha256 + 全量行校验）... 基准: {os.path.basename(bench)}"
          f"  meta: {os.path.basename(bench_meta)}")
    if args.skip_audit:
        print("\n[1/3] 审计已跳过（--skip-audit）：本数据集在本会话已通过认证审计，"
              "重复审计仅耗 CPU；数据文件未变动。")
    else:
        pre = audit_research_evidence(man["files"], man["metas"], bench, bench_meta,
                                      min_assets=2,
                                      min_rows_per_asset=args.min_periods * 2)
        print(f"      preflight: {pre['verdict']}")
        if pre["verdict"] != "PASS":
            print(f"      阻断项 {len(pre['issues'])} 个，前 5: {pre['issues'][:5]}")
            return 2

    # ---- 一次性加载 ----
    print("[2/3] 加载数据（只读一次）...")
    from real_alpha_pipeline import load_certified_csv
    data: Dict[str, List[dict]] = {}
    for code, path in man["files"].items():
        data[code] = load_certified_csv(path, man["metas"].get(code))
    benchmark = load_certified_csv(bench, bench_meta)
    print(f"      已加载 {len(data):,} 只，共 {sum(len(v) for v in data.values()):,} 行")

    # ---- 逐窗口评估 ----
    print(f"[3/3] 逐窗口评估（{len(windows)} 个窗口）...\n")
    from portfolio_backtest import portfolio_backtest
    from alpha.alpha_survival_lab import analyse_alpha
    from historical_universe import point_in_time_universe
    from real_alpha_pipeline import _benchmark_returns, _curve_returns
    from release_gate import (
        build_survivorship_audit, gate_alpha_claim, load_survivorship_evidence,
    )

    # 研究完整性门禁：本脚本自行校验了 PIT 股票池（universe 快照来自认证数据集），
    # 其余证据必须由调用方显式声明；未声明即视为缺失，Alpha 结论会被降级。
    survivorship_audit = build_survivorship_audit(
        load_survivorship_evidence(args.survivorship_evidence or None),
        pit_universe_verified=True,
    )
    if survivorship_audit.ok:
        print("      研究完整性证据：完整 → Alpha 结论可作为可发布结论")
    else:
        from release_gate import missing_evidence
        print("      研究完整性证据：不完整 → Alpha 结论将降级为 INCONCLUSIVE")
        print(f"        缺失项: {', '.join(missing_evidence(survivorship_audit))}")

    universe = _load_universe(dataset)
    rows: List[Dict[str, Any]] = []

    def _write_out() -> None:
        """落盘（抽成函数以便 `--flush-each-window` 复用同一份序列化逻辑）。"""
        if not args.out:
            return
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"windows": rows, "args": vars(args),
                       # 落盘**生效**的基准路径（2026-10-06 增补）。
                       # 本脚本 --benchmark 默认空串，真实值由上面的兜底逻辑
                       # 解析为 bench（注意默认是 benchmark.csv 即**沪深300**，
                       # **不是**等权全A）——不记录则事后无法判断某批结果
                       # 用的哪个基准，这是跨口径比较出错的主要来源。
                       # 见 reports/EVIDENCE_INDEX.md 第六节缺口清单。
                       "benchmark": bench},
                      f, ensure_ascii=False, indent=1, default=str)

    for oos_start in windows:
        _t0 = time.time()
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
        result = portfolio_backtest(restricted, universe_snapshot_map=universe,
                                    threshold=70, top_n=5, horizon=5,
                                    start_signal_date=oos_start)
        s_ret = _curve_returns(result.get("equity_curve", []))
        b_ret = _benchmark_returns(bench_oos)
        common = sorted(set(s_ret) & set(b_ret))

        rec: Dict[str, Any] = {"oos_start": oos_start, "aligned": len(common),
                               "assets": len(restricted)}
        if len(common) >= args.min_periods:
            a = analyse_alpha({d: s_ret[d] for d in common},
                              {d: b_ret[d] for d in common},
                              min_periods=args.min_periods)
            statistical_verdict = VERDICT_MAP.get(a.get("verdict"), a.get("verdict"))
            gated = gate_alpha_claim(statistical_verdict, survivorship_audit)
            rec.update({
                "verdict": gated["verdict"],
                "statistical_verdict": gated["statistical_verdict"],
                "alpha_status": gated["alpha_status"],
                "annualized_excess": a.get("annualized_excess_estimate"),
                "t_stat": a.get("t_stat_normal_approx"),
                "p_value": a.get("normal_approx_pvalue"),
                "ci_lower": (a.get("bootstrap_mean_ci") or {}).get("lower"),
                "ci_upper": (a.get("bootstrap_mean_ci") or {}).get("upper"),
            })
            # 基准同期收益
            if bench_oos:
                first, last = bench_oos[0]["close"], bench_oos[-1]["close"]
                rec["benchmark_return_pct"] = round((last / first - 1) * 100, 2)
        else:
            rec["verdict"] = "SKIPPED"
            rec["reason"] = f"aligned<{args.min_periods}"
        rec.update({
            "trades": result.get("trades"),
            "win_rate_pct": result.get("win_rate_pct"),
            "total_return_pct": result.get("total_return_pct"),
            "max_drawdown_pct": result.get("max_drawdown_pct"),
        })
        if args.dump_logs:
            # 只写不读：这两个键由 portfolio_backtest 返回，**不参与**上面的任何
            # 计算（`aligned` / `annualized_excess` / `verdict` 都在此之前算完）。
            # 默认关闭，确保 reports/ 下既有归档产物的键集合不被改动。
            rec["equity_curve"] = result.get("equity_curve", [])
            rec["trade_log"] = result.get("trade_log", [])
            rec["execution_stats"] = result.get("execution_stats")
        rows.append(rec)
        _el = time.time() - _t0
        if isinstance(rec.get("annualized_excess"), float):
            print(f"  {oos_start}  对齐 {rec['aligned']:>4} 日  "
                  f"策略 {rec['total_return_pct']:>8}%  "
                  f"基准 {rec.get('benchmark_return_pct', 0):>8}%  "
                  f"年化超额 {rec['annualized_excess']:>+8.2%}  ({_el:.0f}s)",
                  flush=True)
        else:
            print(f"  {oos_start}  对齐 {rec['aligned']:>4} 日  "
                  f"{rec.get('verdict')}（{rec.get('reason')}）  ({_el:.0f}s)",
                  flush=True)

    # ---- 汇总 ----
    valid = [r for r in rows if r.get("verdict") not in (None, "SKIPPED")]
    print("\n" + "=" * 96)
    print("汇总")
    print("=" * 96)
    if valid:
        exc = [r["annualized_excess"] for r in valid]
        n_pos = sum(1 for e in exc if e > 0)
        print(f"  有效窗口数      : {len(valid)}")
        print(f"  年化超额为正    : {n_pos} / {len(valid)}")
        print(f"  年化超额中位数  : {sorted(exc)[len(exc)//2]:+.2%}")
        print(f"  年化超额均值    : {sum(exc)/len(exc):+.2%}")
        print(f"  年化超额区间    : [{min(exc):+.2%}, {max(exc):+.2%}]")
        print(f"  判定为 SUPPORTED: {sum(1 for r in valid if r.get('verdict') == 'SUPPORTED')}"
              f" / {len(valid)}")
        print()
        print("  逐窗口明细：")
        print(f"    {'起点':12s} {'对齐日':>6s} {'策略%':>9s} {'基准%':>9s} "
              f"{'年化超额':>10s} {'t':>7s} {'p':>7s}  判定")
        for r in rows:
            if r.get("verdict") == "SKIPPED":
                print(f"    {r['oos_start']:12s} {r['aligned']:>6}  "
                      f"{'—':>9} {'—':>9} {'—':>10} {'—':>7} {'—':>7}  SKIPPED")
                continue
            print(f"    {r['oos_start']:12s} {r['aligned']:>6} "
                  f"{r['total_return_pct']:>9} {r.get('benchmark_return_pct', 0):>9} "
                  f"{r['annualized_excess']:>+10.2%} {r['t_stat']:>7.2f} "
                  f"{r['p_value']:>7.3f}  {r['verdict']}")
    print("\n  声明：本检验未调整任何策略参数；数据存在幸存者偏差与不复权两项缺陷，")
    print("        结论仅反映该策略在此数据集上的表现，不构成投资结论。")

    _write_out()
    if args.out:
        print(f"\n结果已写入: {args.out}")
        print(f"生效基准: {bench}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
