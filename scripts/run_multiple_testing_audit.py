# -*- coding: utf-8 -*-
r"""多重检验校正审计：把「跑了很多次」算进已发布结论的显著性里。

## 为什么需要

本项目累计跑了远多于 1 次的统计检验（因子 IC、复合反转、尾部剔除、集中度、
多股票池、多窗口、ADX 叠加……），而**全部按单次检验的 t / p 门槛判定**。
在 m 次检验中即使所有假设都为假，"至少出现一个 p < 0.05"的概率是
``1 - 0.95^m`` —— m = 30 时约 **78.5%**。未校正的"显著"因此不能作为证据强度。

本脚本对**有机器可读 p 值**的检验做 BH-FDR 与 Bonferroni 校正，
并给出全部已跑检验次数对应的族错误率，作为对无 p 值结论的警示。

## 口径与局限（必须随结论声明）

1. **检验之间不独立**：同一份数据、高度相关的因子、重叠的窗口。
   BH-FDR 在独立或 PRDS 假设下控制 FDR；此处不满足，故结果是**下界式的参考**，
   不是严格的 FDR 保证。
2. **v1 与 v2 不是两次独立假设**：v2 是同一批因子在更干净数据上的**复检**，
   不是新假设。故按"族"分别校正，并另报合并口径。
3. **只有 IC 族有 p 值**：策略层面的实验（A/B、尾部剔除、集中度、ADX）
   归档的是判定与超额，没有 p 值，**无法逐项校正** —— 它们的次数只体现在
   族错误率的警示里。这是本项目研究记录的一处结构性缺口。

用法::

    python scripts/run_multiple_testing_audit.py --out reports/multiple_testing_audit.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validation.multiple_testing import (  # noqa: E402
    benjamini_hochberg,
    bonferroni,
    family_wise_error_rate,
)

# 项目已归档、含机器可读 p 值的检验来源
SOURCES = [
    ("v1 全样本 IC（10 因子）", "tdx_factor_summary.json", ("full_sample", "factors")),
    ("v2 全样本 IC（10 因子）", "reports/v2_factor_study.json", ("full", "factors")),
]

# 无 p 值、但确实执行过的检验（用于族错误率警示；计数有据可查）
DECLARED_NON_IC_TESTS = [
    "H-C1 复合反转 · IC 层面（ALPHA_HYPOTHESIS_PREREG.md）",
    "H-C1 复合反转 · 组合层面 A/B 一阶段（PORTFOLIO_AB_REPORT.md）",
    "H-C1 复合反转 · 组合层面 A/B 二阶段（PORTFOLIO_AB_REPORT_2.md）",
    "H-C1 复合反转 · 组合层面 A/B 三阶段（PORTFOLIO_AB_REPORT_3.md）",
    "尾部剔除 V1（TAIL_EXCLUSION_REPORT.md）",
    "尾部剔除 V2（TAIL_EXCLUSION_REPORT.md）",
    "集中度 C10 / C20 / C30（CONCENTRATION_REPORT.md）",
    "采样敏感性 4 组独立抽样（SAMPLING_SENSITIVITY_REPORT.md）",
    "多股票池重复验证 6 组（UNIVERSE_REPLICATION_REPORT.md）",
    "多窗口滚动检验 6 窗口（STEP1_3_EXECUTION_REPORT.md §5.2）",
    "ADX 叠加 5 窗口 + 常数敞口对照 5 窗口（STEP1_3_EXECUTION_REPORT.md §6.4）",
    "成本模型 legacy/new 对照 2 窗口（reports/cost_model_check.json）",
]

# 策略层面**有机器可读 p 值**的归档（滚动评估族）。
# 每一项是 (标签, 产物路径, p 值字段, t 值字段)。
STRATEGY_SOURCES = [
    ("基线 V0 · v2 抽样池 · 对沪深300", "reports/v2_rolling_eval_ew.json",
     "p_value", "t_stat"),
    ("基线 V0 · v2 抽样池 · 对等权全市场", "reports/v2_rolling_eval_ew.json",
     "ew_p_value", "ew_t_stat"),
    ("基线 V0 · v3 全池 · 对沪深300", "reports/v3_rolling_eval_ew_full.json",
     "p_value", "t_stat"),
    ("基线 V0 · v3 全池 · 对等权全市场", "reports/v3_rolling_eval_ew_full.json",
     "ew_p_value", "ew_t_stat"),
    ("基线 V0 · 固定池 600（v2 数据）", "reports/fixedpool_v2.json",
     "p_value", "t_stat"),
    ("基线 V0 · 固定池 600（v3 数据）", "reports/fixedpool_v3.json",
     "p_value", "t_stat"),
]

# 策略层面的**不同假设/配置**（用于族错误率；窗口是同一配置的重复评估，**不计入**）
DISTINCT_STRATEGY_CONFIGS = [
    "基线 V0（内置动量追高）",
    "H-C1 复合反转 · A/B 三阶段",
    "尾部剔除 V1",
    "尾部剔除 V2",
    "集中度 C10",
    "集中度 C20",
    "集中度 C30",
    "ADX 状态叠加",
    "ADX 常数敞口对照",
    "成本模型 legacy",
    "成本模型 new",
    "采样敏感性 4 组抽样",
    "多股票池重复验证 6 组",
]


def _dig(obj: Any, path) -> Any:
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj


def collect(project_root: Path) -> Dict[str, List[Dict[str, Any]]]:
    """按来源收集 ``{family: [{name, p, t, n, source}]}``。"""
    families: Dict[str, List[Dict[str, Any]]] = {}
    for label, rel, path in SOURCES:
        f = project_root / rel
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        factors = _dig(data, path)
        if not isinstance(factors, dict):
            continue
        rows = []
        for name, meta in factors.items():
            if not isinstance(meta, dict) or meta.get("p") is None:
                continue
            rows.append({"name": name, "p": float(meta["p"]),
                         "t": meta.get("t"), "n_periods": meta.get("n_periods"),
                         "source": rel})
        if rows:
            families[label] = rows
    return families


def collect_strategy(project_root: Path) -> Dict[str, List[Dict[str, Any]]]:
    """按配置收集策略层面滚动评估的**逐窗口** p 值。

    ⚠️ 同一配置的多个窗口是**同一假设的重复评估**（同一份数据、重叠区间），
    不是独立检验。因此下游只把「每个配置的中位 p」当作该假设的摘要，
    **不把窗口数计入检验次数**。
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    for label, rel, pfield, tfield in STRATEGY_SOURCES:
        f = project_root / rel
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rows: List[Dict[str, Any]] = []
        for w in data.get("windows") or []:
            p = w.get(pfield)
            if p is None:
                continue
            rows.append({"window": w.get("oos_start"), "p": float(p),
                         "t": w.get(tfield), "source": rel})
        if rows:
            out[label] = rows
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="多重检验校正审计")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = Path(args.root)
    families = collect(root)
    if not families:
        print("未找到任何可读的 p 值来源，无法校正。", flush=True)
        return 2

    report: Dict[str, Any] = {"alpha": args.alpha, "families": {}, "notes": []}
    print("=" * 92)
    print("多重检验校正审计（BH-FDR / Bonferroni）")
    print("=" * 92)

    total_tests = 0
    all_p: List[float] = []
    for label, rows in families.items():
        ps = [r["p"] for r in rows]
        total_tests += len(ps)
        all_p.extend(ps)
        bh = benjamini_hochberg(ps, args.alpha)
        bonf = bonferroni(ps, args.alpha)
        raw_rej = sum(1 for p in ps if p <= args.alpha)
        print(f"\n【{label}】 m = {len(ps)}")
        print(f"  未校正拒绝数 (p <= {args.alpha}) : {raw_rej}")
        print(f"  BH-FDR 拒绝数                 : {bh['k']}   （阈值 p <= {bh['threshold']}）")
        print(f"  Bonferroni 拒绝数             : {bonf['k']}")
        print(f"  {'因子':<16}{'t':>8}{'p':>10}{'p_BH':>10}{'p_Bonf':>10}  判定")
        bonf_by_index = {r["index"]: r for r in bonf["results"] if r}
        detail = []
        for res in sorted((r for r in bh["results"] if r), key=lambda r: r["p"]):
            src = rows[res["index"]]
            bf = bonf_by_index.get(res["index"])
            verdict = "BH 显著" if res["rejected"] else "校正后不显著"
            if bf and bf["rejected"]:
                verdict = "两者皆显著"
            t = src.get("t")
            t_txt = f"{t:>8.2f}" if isinstance(t, (int, float)) else f"{'—':>8}"
            print(f"  {src['name']:<16}{t_txt}{res['p']:>10.4f}{res['p_adjusted']:>10.4f}"
                  f"{(bf['p_adjusted'] if bf else float('nan')):>10.4f}  {verdict}")
            detail.append({
                "name": src["name"], "t": src.get("t"), "p": res["p"],
                "p_adjusted_bh": res["p_adjusted"], "rejected_bh": res["rejected"],
                "p_adjusted_bonferroni": bf["p_adjusted"] if bf else None,
                "rejected_bonferroni": bf["rejected"] if bf else None,
            })
        report["families"][label] = {
            "m": len(ps),
            "rejected_uncorrected": raw_rej,
            "rejected_bh": bh["k"],
            "rejected_bonferroni": bonf["k"],
            "bh_threshold": bh["threshold"],
            "results": detail,
        }

    # 合并口径（声明不独立）
    combined = benjamini_hochberg(all_p, args.alpha)
    print(f"\n【合并口径】 m = {len(all_p)}（v1/v2 非独立，仅供对照）")
    print(f"  BH-FDR 拒绝数: {combined['k']} / {len(all_p)}")

    # ---- 策略层面：滚动评估族的逐窗口 p 值 ----
    strategy = collect_strategy(root)
    strat_summary: Dict[str, Any] = {}
    if strategy:
        print("\n" + "=" * 92)
        print("策略层面滚动评估族（逐窗口 p 值）")
        print("=" * 92)
        print("⚠️ 同一配置的多个窗口是**同一假设的重复评估**，不是独立检验 ——")
        print("   故只取「该配置的中位 p」作为摘要，窗口数**不计入**检验次数。\n")
        print(f"{'配置':<38}{'窗口':>5}{'中位p':>9}{'最小p':>9}{'最大p':>9}"
              f"{'任一窗口<0.05':>14}")
        med_p: List[float] = []
        for label, rows in strategy.items():
            ps = sorted(r["p"] for r in rows)
            med = statistics.median(ps)
            med_p.append(med)
            any_sig = any(p < args.alpha for p in ps)
            print(f"{label:<38}{len(ps):>5}{med:>9.4f}{ps[0]:>9.4f}{ps[-1]:>9.4f}"
                  f"{('是' if any_sig else '否'):>14}")
            strat_summary[label] = {
                "n_windows": len(ps), "median_p": med, "min_p": ps[0], "max_p": ps[-1],
                "any_window_significant": any_sig,
                "windows": [r["window"] for r in rows],
            }
        bh_s = benjamini_hochberg(med_p, args.alpha)
        print(f"\n  以各配置中位 p 做 BH 校正（m = {len(med_p)}）：拒绝 {bh_s['k']} 个")
        print("  判读：全部配置的中位 p 均远大于 0.05 → "
              "**策略层面的负超额是方向性结论，不是统计显著结论**。")
        strat_summary["_bh_on_median_p"] = {"m": len(med_p), "rejected": bh_s["k"]}

    # 合并口径（声明不独立）

    # ---- 族错误率：分「假设数」与「执行次数」两个口径 ----
    n_ic_hypotheses = max((len(v) for v in families.values()), default=0)  # v1/v2 是同一批因子的复检
    n_strategy_configs = len(DISTINCT_STRATEGY_CONFIGS)
    n_hypotheses = n_ic_hypotheses + n_strategy_configs
    n_executions = total_tests + len(DECLARED_NON_IC_TESTS)
    fwer_h = family_wise_error_rate(n_hypotheses)
    fwer_e = family_wise_error_rate(n_executions)

    print("\n" + "=" * 92)
    print("族错误率警示（未校正时「至少出现一个显著结果」的概率）")
    print("=" * 92)
    print("  口径 A · **不同假设数**（推荐）")
    print(f"     因子假设 {n_ic_hypotheses}（v1/v2 是同一批因子的复检，不重复计数）")
    print(f"     策略配置 {n_strategy_configs}（窗口/股票池/基准是同一配置的重复评估，不计入）")
    print(f"     合计 {n_hypotheses} → FWER = {fwer_h:.1%}")
    print("  口径 B · 检验执行次数（保守）")
    print(f"     有 p 值的检验 {total_tests} + 无 p 值 {len(DECLARED_NON_IC_TESTS)}"
          f" = {n_executions} → FWER = {fwer_e:.1%}")
    print(f"\n  策略层面不同配置（{n_strategy_configs} 个）：")
    for item in DISTINCT_STRATEGY_CONFIGS:
        print(f"    - {item}")
    print(f"\n  无机器可读 p 值的检验（{len(DECLARED_NON_IC_TESTS)} 项，无法逐项校正）：")
    for item in DECLARED_NON_IC_TESTS:
        print(f"    - {item}")

    report["combined"] = {"m": len(all_p), "rejected_bh": combined["k"]}
    report["strategy_family"] = strat_summary
    report["family_wise"] = {
        "n_ic_hypotheses": n_ic_hypotheses,
        "n_strategy_configs": n_strategy_configs,
        "n_hypotheses": n_hypotheses,
        "fwer_by_hypotheses": fwer_h,
        "tests_with_p": total_tests,
        "tests_without_p": len(DECLARED_NON_IC_TESTS),
        "n_executions": n_executions,
        "fwer_by_executions": fwer_e,
        "strategy_configs": DISTINCT_STRATEGY_CONFIGS,
        "without_p_values": DECLARED_NON_IC_TESTS,
    }
    report["notes"] = [
        "检验之间不独立（同数据、相关因子、重叠窗口）→ BH 结果是参考下界，非严格 FDR 保证",
        "v1 与 v2 是同一批因子的复检，不是两次独立假设；故按族分别校正并另报合并口径",
        "策略层面实验无 p 值归档，无法逐项校正 —— 这是研究记录的结构性缺口，"
        "后续实验应在落盘时一并记录 p 值/置信区间",
    ]
    print("\n  声明：")
    for n in report["notes"]:
        print(f"    · {n}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                  encoding="utf-8", newline="\n")
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
