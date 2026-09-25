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

## 双基准（2026-09-19 新增）

策略池是**全市场抽样**，而数据集自带的 `benchmark.csv` 是**沪深300**——
两者口径不同。实测（`ALPHA_CAPABILITY_GAP_ANALYSIS.md` §3.1）二者在部分窗口
相差 11~16pp，方向为「等权全市场 > 沪深300」，即只报沪深300 会**系统性高估**
策略超额。故本脚本默认同时报告**等权全市场**（第二基准）的超额：

* 同一策略收益序列，**只换基准**，两个超额并列报告，不取"更有利者"；
* 等权基准口径见 `validation.benchmark.equal_weight_returns`（PIT 成分、
  停牌按 0 收益持有、日频再平衡、不含成本）；
* 用 `--no-ew-benchmark` 可退回只报沪深300 的旧口径。

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


def _load_manifest(dataset: str, max_stocks: int, min_rows_asset: int = 0,
                   codes_file: str = "") -> Dict[str, Any]:
    stock_dir = os.path.join(dataset, "stocks")
    if codes_file:
        # 固定池：直接用清单，不做抽样 —— 清单里缺文件的代码如实剔除并报告
        wanted = []
        with open(codes_file, encoding="utf-8") as fh:
            for line in fh:
                c = line.strip()
                if c and not c.startswith("#"):
                    wanted.append(c.zfill(6))
        missing = [c for c in wanted
                   if not (os.path.exists(os.path.join(stock_dir, f"{c}.csv"))
                           and os.path.exists(os.path.join(stock_dir, f"{c}.metadata.json")))]
        codes = [c for c in wanted if c not in set(missing)]
        print(f"  固定池: 清单 {len(wanted)} 只，本数据集缺失 {len(missing)} 只"
              f"→ 实际使用 {len(codes)} 只")
        if missing[:5]:
            print(f"    缺失样例: {missing[:5]}")
        return {
            "files": {c: os.path.join(stock_dir, f"{c}.csv") for c in codes},
            "metas": {c: os.path.join(stock_dir, f"{c}.metadata.json") for c in codes},
            "codes": codes,
            "codes_file": codes_file,
        }

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


def main() -> int:
    ap = argparse.ArgumentParser(description="多窗口滚动样本外稳健性检验")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=800)
    ap.add_argument("--codes-file", default="",
                    help="固定股票池文件（每行一个代码，空行/# 注释忽略）。"
                         "给定后**不做等距抽样**，直接用该清单 —— "
                         "用于在两个数据集上跑**同一批代码**，"
                         "从而分离「数据改善」与「抽样噪声」。")
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
    ap.add_argument(
        "--ew-benchmark", dest="ew_benchmark", action="store_true", default=True,
        help="同时以**等权全市场**为第二基准（默认开启）。策略池是全市场抽样，"
             "而基准文件是沪深300，两者口径不同；实测二者在部分窗口相差 11~16pp，"
             "只报沪深300 会系统性高估策略超额。")
    ap.add_argument(
        "--no-ew-benchmark", dest="ew_benchmark", action="store_false",
        help="关闭等权全市场第二基准（退回只报沪深300 的旧口径）。")
    ap.add_argument(
        "--ew-series", default="",
        help="外部等权全市场**日收益序列** JSON（由 run_alpha_gap_probe.py "
             "--out-series 生成）。给定后不再用回测抽样池现算基准 —— "
             "回测池受 --max-stocks 限制，覆盖率会随 PIT 池变大而下降"
             "（实测 v2 为 26.8%、v3 仅 18.1%）。")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 96)
    print("多窗口滚动样本外稳健性检验 · 内置基线策略（参数完全固定，不做任何寻优）")
    print("=" * 96)

    man = _load_manifest(dataset, args.max_stocks, args.min_rows_asset,
                         args.codes_file)
    print(f"股票池: {len(man['codes']):,} 只")

    # ---- 一次性审计（数据在各窗口间相同，无需重复校验）----
    from professional_audit import audit_research_evidence
    bench = os.path.join(dataset, "benchmark.csv")
    bench_meta = os.path.join(dataset, "benchmark.metadata.json")
    print("\n[1/3] 一次性审计（sha256 + 全量行校验）...")
    pre = audit_research_evidence(man["files"], man["metas"], bench, bench_meta,
                                  min_assets=2, min_rows_per_asset=args.min_periods * 2)
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

    # ---- 等权全市场基准（第二基准，纠正基准错配）----
    # 口径见 validation.benchmark.equal_weight_returns 的 docstring：
    # PIT 成分、停牌按 0 收益持有、日频再平衡、不含成本。
    universe = _load_universe(dataset)
    ew_ret: Dict[str, float] = {}
    ew_diag: Dict[str, Any] = {}
    ew_source = ""
    if args.ew_benchmark and args.ew_series:
        # 外部序列优先：它由完整（或更大）池构造，覆盖率不受回测抽样限制
        with open(args.ew_series, encoding="utf-8") as fh:
            payload = json.load(fh)
        ew_ret = {str(k): float(v) for k, v in (payload.get("series") or {}).items()}
        ew_diag = payload.get("diagnostics") or {}
        ew_source = payload.get("source", args.ew_series)
        print(f"      等权全市场基准：来自外部序列 {args.ew_series}")
        print(f"        来源 {ew_source}")
        if ew_diag.get("universe_coverage") is not None:
            print(f"        覆盖度 {ew_diag['universe_coverage']:.1%}、"
                  f"成员均值 {ew_diag.get('members_mean')} 只、"
                  f"{ew_diag.get('dates')} 个交易日")
    elif args.ew_benchmark:
        from validation.benchmark import equal_weight_diagnostics, equal_weight_returns
        cal = sorted({str(b["date"]) for b in benchmark})
        ew_ret = equal_weight_returns(data, universe, dates=cal)
        ew_diag = equal_weight_diagnostics(data, universe, dates=cal)
        if ew_diag.get("dates"):
            print(f"      等权全市场基准：{ew_diag['dates']:,} 日，"
                  f"成员 {ew_diag['members_min']}~{ew_diag['members_max']} 只"
                  f"（均值 {ew_diag['members_mean']}），"
                  f"PIT 覆盖度 {ew_diag['universe_coverage']:.1%}")
            if ew_diag["universe_coverage"] < 0.5:
                print("        ⚠ 覆盖度 < 50% —— 等权基准仅为 PIT 池的子集，"
                      "该限定条件必须随结论声明")
        else:
            print("      等权全市场基准：无法构造（无可用日期）")
            ew_ret = {}

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

    def _cum_return(rets: Dict[str, float]) -> float:
        """几何累计收益（期末/期初 - 1 的等价形式）。"""
        g = 1.0
        for r in rets.values():
            g *= 1.0 + r
        return g - 1.0

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

            # ---- 第二基准：等权全市场 ----
            # 同一策略序列，只换基准。两个超额并列报告，不做"取更有利者"的选择。
            if ew_ret:
                ew_win = {d: ew_ret[d] for d in common if d in ew_ret}
                if len(ew_win) >= args.min_periods:
                    a_ew = analyse_alpha({d: s_ret[d] for d in common if d in ew_ret},
                                         ew_win, min_periods=args.min_periods)
                    stat_ew = VERDICT_MAP.get(a_ew.get("verdict"), a_ew.get("verdict"))
                    gated_ew = gate_alpha_claim(stat_ew, survivorship_audit)
                    rec.update({
                        "ew_verdict": gated_ew["verdict"],
                        "ew_statistical_verdict": gated_ew["statistical_verdict"],
                        "ew_aligned": len(ew_win),
                        "ew_annualized_excess": a_ew.get("annualized_excess_estimate"),
                        "ew_t_stat": a_ew.get("t_stat_normal_approx"),
                        "ew_p_value": a_ew.get("normal_approx_pvalue"),
                        "ew_ci_lower": (a_ew.get("bootstrap_mean_ci") or {}).get("lower"),
                        "ew_ci_upper": (a_ew.get("bootstrap_mean_ci") or {}).get("upper"),
                        "ew_benchmark_return_pct": round(_cum_return(ew_win) * 100, 2),
                    })
                else:
                    rec["ew_verdict"] = "SKIPPED"
                    rec["ew_reason"] = f"ew_aligned<{args.min_periods}"
        else:
            rec["verdict"] = "SKIPPED"
            rec["reason"] = f"aligned<{args.min_periods}"
        rec.update({
            "trades": result.get("trades"),
            "win_rate_pct": result.get("win_rate_pct"),
            "total_return_pct": result.get("total_return_pct"),
            "max_drawdown_pct": result.get("max_drawdown_pct"),
        })
        rows.append(rec)
        _el = time.time() - _t0
        if isinstance(rec.get("annualized_excess"), float):
            ew_txt = ""
            if isinstance(rec.get("ew_annualized_excess"), float):
                ew_txt = (f"  等权全市场 {rec.get('ew_benchmark_return_pct', 0):>8}%"
                          f"  超额 {rec['ew_annualized_excess']:>+8.2%}")
            print(f"  {oos_start}  对齐 {rec['aligned']:>4} 日  "
                  f"策略 {rec['total_return_pct']:>8}%  "
                  f"沪深300 {rec.get('benchmark_return_pct', 0):>8}%  "
                  f"超额 {rec['annualized_excess']:>+8.2%}{ew_txt}  ({_el:.0f}s)",
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
    exc_ew: List[float] = []
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
        # 第二基准（等权全市场）汇总
        exc_ew = [r["ew_annualized_excess"] for r in valid
                  if isinstance(r.get("ew_annualized_excess"), float)]
        if exc_ew:
            print()
            print("  【第二基准 · 等权全市场】策略池是全市场抽样，基准文件是沪深300，")
            print("   两者口径不同。同口径对照如下（同一策略序列，只换基准）：")
            print(f"     年化超额为正    : {sum(1 for e in exc_ew if e > 0)} / {len(exc_ew)}")
            print(f"     年化超额中位数  : {sorted(exc_ew)[len(exc_ew)//2]:+.2%}")
            print(f"     年化超额均值    : {sum(exc_ew)/len(exc_ew):+.2%}")
            print(f"     年化超额区间    : [{min(exc_ew):+.2%}, {max(exc_ew):+.2%}]")
            if ew_source:
                print(f"     基准来源        : {ew_source}")
            if ew_diag.get("universe_coverage") is not None:
                print(f"     基准构成        : 成员均值 {ew_diag['members_mean']} 只，"
                      f"PIT 覆盖度 {ew_diag['universe_coverage']:.1%}（未覆盖成员不计入分母）")
            print("     口径声明        : 日频再平衡、不含交易成本 → 真实可实现收益更低；")
            print("                       本序列为理论构造，不得当作可交易基准。")
        print()
        print("  逐窗口明细：")
        print(f"    {'起点':12s} {'对齐日':>6s} {'策略%':>9s} {'沪深300%':>9s} "
              f"{'超额':>10s} {'t':>7s} {'p':>7s}  判定")
        for r in rows:
            if r.get("verdict") == "SKIPPED":
                print(f"    {r['oos_start']:12s} {r['aligned']:>6}  "
                      f"{'—':>9} {'—':>9} {'—':>10} {'—':>7} {'—':>7}  SKIPPED")
                continue
            print(f"    {r['oos_start']:12s} {r['aligned']:>6} "
                  f"{r['total_return_pct']:>9} {r.get('benchmark_return_pct', 0):>9} "
                  f"{r['annualized_excess']:>+10.2%} {r['t_stat']:>7.2f} "
                  f"{r['p_value']:>7.3f}  {r['verdict']}")
        if exc_ew:
            print()
            print("  逐窗口明细（第二基准 · 等权全市场）：")
            print(f"    {'起点':12s} {'对齐日':>6s} {'等权全市场%':>12s} "
                  f"{'超额':>10s} {'t':>7s} {'p':>7s}  判定")
            for r in rows:
                if not isinstance(r.get("ew_annualized_excess"), float):
                    continue
                print(f"    {r['oos_start']:12s} {r.get('ew_aligned', 0):>6} "
                      f"{r.get('ew_benchmark_return_pct', 0):>12} "
                      f"{r['ew_annualized_excess']:>+10.2%} {r['ew_t_stat']:>7.2f} "
                      f"{r['ew_p_value']:>7.3f}  {r['ew_verdict']}")
    print("\n  声明：本检验未调整任何策略参数；数据缺陷见数据集 evidence.json，")
    print("        结论仅反映该策略在此数据集上的表现，不构成投资结论。")
    if exc_ew:
        print("        第二基准为日频再平衡、不含成本的理论构造，真实可实现收益更低。")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"windows": rows, "args": vars(args),
                       "ew_benchmark_source": ew_source,
                       "ew_benchmark_diagnostics": ew_diag}, f,
                      ensure_ascii=False, indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
