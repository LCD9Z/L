# -*- coding: utf-8 -*-
"""ADX 市场状态仓位叠加层 · 观察性检验（真实 TDX 数据）。

问题：把 KHunter 的 ADX 三档路由作为**仓位叠加层**后，基线策略的负超额
是否收窄？（报告《GITHUB_REFERENCE_INTEGRATION_REPORT.md》第 2 步）

## 实验设计（事前设定，非参数寻优）

- 基线：`portfolio_backtest`，参数与滚动检验完全一致
  （threshold=70 / top_n=5 / horizon=5 / PIT 股票池 / 现行 Costs）。
- 叠加层：`position_scaler=router.make_position_scaler()`，只按交易日缩放
  **新开仓预算**（明确 1.0 / 萌芽 0.5 / 震荡 0.3），不改信号、阈值、周期、成本。
- 状态源：数据集基准指数（000300）日K。**与 KHunter 不同**（其用全A指数
  000985.CSI）：本地认证数据集只含 000300 基准，此差异已在报告与模块
  docstring 中声明。
- 阈值（20/25）与系数（0.5/0.3）来自 KHunter 的事前设定，**未经本地调优**；
  因此本检验只做观察，不产生"策略改进"结论。

## 结论口径

- 每窗口报告 基线 vs 叠加 的年化超额与 Δ（pp），并统计 Δ>0 的窗口数；
- Alpha 结论一律经 `release_gate` 裁决（无证据清单时降级为 INCONCLUSIVE）；
- 数据存在幸存者偏差与不复权两项已知缺陷，结论仅反映本数据集。
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 与 README 多窗口表一致的 5 个样本外起点
DEFAULT_WINDOWS = [
    "2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02", "2025-07-01",
]

VERDICT_MAP = {
    "SUPPORTED": "ALPHA_SUPPORTED",
    "NOT_SUPPORTED": "ALPHA_NOT_ESTABLISHED",
    "INCONCLUSIVE": "INCONCLUSIVE",
}


def _load_universe(dataset: str) -> Dict[str, List[str]]:
    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as f:
        return json.load(f)["snapshots"]


def _load_manifest(dataset: str, max_stocks: int) -> Dict[str, Any]:
    stock_dir = os.path.join(dataset, "stocks")
    in_universe = set()
    for v in _load_universe(dataset).values():
        in_universe.update(v)
    codes = sorted(
        c for c in in_universe
        if os.path.exists(os.path.join(stock_dir, f"{c}.csv"))
        and os.path.exists(os.path.join(stock_dir, f"{c}.metadata.json"))
    )
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    return {
        "files": {c: os.path.join(stock_dir, f"{c}.csv") for c in codes},
        "metas": {c: os.path.join(stock_dir, f"{c}.metadata.json") for c in codes},
        "codes": codes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="ADX 仓位叠加层观察性检验（baseline vs overlay）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=400)
    ap.add_argument("--min-periods", type=int, default=252)
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--variants", default="baseline,overlay,const05",
                    help="逗号分隔的变体子集（如仅补 const05 对照时用 'const05'）")
    ap.add_argument("--config", default="",
                    help="regime 配置 JSON（键见 regime_router.example.json）；"
                         "缺省用模块默认（enabled=True，阈值/系数为 KHunter 事前设定）")
    ap.add_argument("--out", default="")
    ap.add_argument("--survivorship-evidence", default="",
                    help="研究完整性证据清单 JSON（键名见 release_gate.EVIDENCE_KEYS）。"
                         "未提供时 Alpha 结论降级为 INCONCLUSIVE。")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]

    print("=" * 100)
    print("ADX 仓位叠加层 · 观察性检验（只缩放新开仓预算，不改信号/阈值/周期/成本）")
    print("=" * 100)

    man = _load_manifest(dataset, args.max_stocks)
    print(f"股票池: {len(man['codes']):,} 只")

    print("[1/4] 一次性审计（sha256 + 全量行校验）...")
    from professional_audit import audit_research_evidence
    bench = os.path.join(dataset, "benchmark.csv")
    bench_meta = os.path.join(dataset, "benchmark.metadata.json")
    pre = audit_research_evidence(man["files"], man["metas"], bench, bench_meta,
                                  min_assets=2, min_rows_per_asset=args.min_periods * 2)
    print(f"      preflight: {pre['verdict']}")
    if pre["verdict"] != "PASS":
        print(f"      阻断项 {len(pre['issues'])} 个，前 5: {pre['issues'][:5]}")
        return 2

    print("[2/4] 加载数据（只读一次）...")
    from real_alpha_pipeline import load_certified_csv
    data: Dict[str, List[dict]] = {}
    for code, path in man["files"].items():
        data[code] = load_certified_csv(path, man["metas"].get(code))
    benchmark = load_certified_csv(bench, bench_meta)
    print(f"      已加载 {len(data):,} 只，共 {sum(len(v) for v in data.values()):,} 行")

    print("[3/4] 构建 ADX 路由（状态源 = 数据集基准 000300，与 KHunter 全A口径不同，已声明）...")
    from regime.adx_router import RegimeRouter, load_config
    cfg = load_config(args.config) if args.config else {"enabled": True}
    cfg.setdefault("enabled", True)
    router = RegimeRouter(cfg, index_bars=benchmark)
    scaler = router.make_position_scaler()
    print(f"      enabled={router.enabled}  thresholds=({cfg.get('oscillation_lt', 20.0)},"
          f"{cfg.get('trending_ge', 25.0)})  confirm_days={cfg.get('confirm_days', 1)}")
    if not router.enabled:
        print("      !! 路由未启用，叠加层将等于基线（只用于验证通路）")

    # 研究完整性门禁：与滚动检验一致，证据未声明即降级
    from release_gate import (
        build_survivorship_audit, gate_alpha_claim, load_survivorship_evidence,
        missing_evidence,
    )
    survivorship_audit = build_survivorship_audit(
        load_survivorship_evidence(args.survivorship_evidence or None),
        pit_universe_verified=True,
    )
    if survivorship_audit.ok:
        print("      研究完整性证据：完整 → Alpha 结论可作为可发布结论")
    else:
        print("      研究完整性证据：不完整 → Alpha 结论降级为 INCONCLUSIVE")
        print(f"        缺失项: {', '.join(missing_evidence(survivorship_audit))}")

    print(f"[4/4] 逐窗口对照（{len(windows)} 个窗口 × 基线/叠加）...\n")
    from portfolio_backtest import portfolio_backtest
    from alpha.alpha_survival_lab import analyse_alpha
    from historical_universe import point_in_time_universe
    from real_alpha_pipeline import _benchmark_returns, _curve_returns

    universe = _load_universe(dataset)
    rows: List[Dict[str, Any]] = []

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
        b_ret = _benchmark_returns(bench_oos)

        rec: Dict[str, Any] = {"oos_start": oos_start, "assets": len(restricted)}
        # const05 = 恒定 0.5× 敞口对照：用于把「ADX 状态识别的贡献」与
        # 「单纯降低敞口的机械减亏」区分开（归因对照，事前设定）。
        all_variants = {"baseline": None, "overlay": scaler, "const05": lambda day: 0.5}
        want = {v.strip() for v in args.variants.split(",") if v.strip()}
        unknown = want - set(all_variants)
        if unknown:
            print(f"未知变体 {sorted(unknown)}，可用: {sorted(all_variants)}")
            return 2
        variants = {k: v for k, v in all_variants.items() if k in want}
        for name, scaler_fn in variants.items():
            kwargs: Dict[str, Any] = dict(
                universe_snapshot_map=universe, threshold=70, top_n=5, horizon=5,
                start_signal_date=oos_start)
            if scaler_fn is not None:
                kwargs["position_scaler"] = scaler_fn
            result = portfolio_backtest(restricted, **kwargs)
            s_ret = _curve_returns(result.get("equity_curve", []))
            common = sorted(set(s_ret) & set(b_ret))
            entry: Dict[str, Any] = {
                "total_return_pct": result.get("total_return_pct"),
                "max_drawdown_pct": result.get("max_drawdown_pct"),
                "trades": result.get("trades"),
                "win_rate_pct": result.get("win_rate_pct"),
            }
            if len(common) >= args.min_periods:
                a = analyse_alpha({d: s_ret[d] for d in common},
                                  {d: b_ret[d] for d in common},
                                  min_periods=args.min_periods)
                statistical_verdict = VERDICT_MAP.get(a.get("verdict"), a.get("verdict"))
                gated = gate_alpha_claim(statistical_verdict, survivorship_audit)
                entry.update({
                    "annualized_excess": a.get("annualized_excess_estimate"),
                    "verdict": gated["verdict"],
                })
            rec[name] = entry

        if rec.get("baseline", {}).get("annualized_excess") is not None \
                and rec.get("overlay", {}).get("annualized_excess") is not None:
            rec["excess_delta_pp"] = round(
                (rec["overlay"]["annualized_excess"]
                 - rec["baseline"]["annualized_excess"]) * 100, 3)
        # 窗口内 regime 分布（仅统计信号日）
        regime_counts = collections.Counter(
            router.decide(d).regime or "insufficient" for d in oos_dates)
        rec["regime_day_counts"] = dict(regime_counts)
        rows.append(rec)

        parts = []
        for name, label in (("baseline", "基线"), ("overlay", "叠加"), ("const05", "恒定0.5×")):
            if name in rec:
                v = rec[name]
                e = v.get("annualized_excess")
                parts.append(f"{label}: 超额 {e if e is not None else 0:>8.2%}"
                             f" 回撤 {v['max_drawdown_pct']:>7}%")
        parts.append(f"Δ超额 {rec.get('excess_delta_pp', 0):+.2f}pp")
        parts.append(f"档位分布 {dict(rec['regime_day_counts'])}")
        parts.append(f"({time.time()-_t0:.0f}s)")
        print(f"  {oos_start}  " + "  |  ".join(parts), flush=True)

    print("\n" + "=" * 100)
    print("汇总（观察口径，不构成策略有效性结论）")
    print("=" * 100)
    deltas = [r["excess_delta_pp"] for r in rows if r.get("excess_delta_pp") is not None]
    if deltas:
        n_pos = sum(1 for d in deltas if d > 0)
        print(f"  Δ超额为正（叠加优于基线）: {n_pos} / {len(deltas)} 窗口")
        print(f"  Δ超额中位数: {sorted(deltas)[len(deltas)//2]:+.2f}pp   "
              f"区间: [{min(deltas):+.2f}, {max(deltas):+.2f}]pp")
        dd_base = [r["baseline"]["max_drawdown_pct"] for r in rows if "baseline" in r]
        dd_over = [r["overlay"]["max_drawdown_pct"] for r in rows if "overlay" in r]
        if dd_base and dd_over:
            print(f"  回撤中位数: 基线 {sorted(dd_base)[len(dd_base)//2]:.2f}% → "
                  f"叠加 {sorted(dd_over)[len(dd_over)//2]:.2f}%")
    print("  声明：阈值与仓位系数来自 KHunter 事前设定（未经本地调优）；")
    print("        状态源为 000300（KHunter 用全A指数）；")
    print("        数据存在幸存者偏差与不复权两项缺陷，结论仅反映本数据集。")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"windows": rows, "args": vars(args),
                       # 生效基准路径（2026-10-06 增补）：默认为 benchmark.csv 即沪深300
                       "benchmark": bench},
                      f, ensure_ascii=False, indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
