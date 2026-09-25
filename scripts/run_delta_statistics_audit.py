# -*- coding: utf-8 -*-
r"""Δ 型策略结论的配对统计量补记。

## 为什么是配对检验

项目里大量结论是**相对**的：「V1 优于 V0」「叠加层 Δ 超额为正」「C20 优于 C5」。
这些不是"某个绝对超额是否显著"，而是**同一窗口/同一股票池上两个变体的差**。

对这类结论，正确的检验是**配对 t 检验**（paired t-test）：
先逐对求差，再对**差值序列**做单样本 t 检验。
配对设计消掉了窗口与股票池的共同效应，功效远高于把两组当独立样本比较。

而 `alpha.alpha_survival_lab.excess_t_statistics` 正好就是单样本 t 检验 ——
**对差值序列调用它即得配对检验结果**。

## 为什么不用重跑

归档的逐窗口产物（`tdx_tail_exclusion_*_summary.json` 等）已含
「变体 × 窗口 × 超额」的完整矩阵。**统计量可以从这些点估计直接算出** ——
这与"只有单个点估计、无法反推 p 值"的情形不同：这里有 n 个配对的点估计，
配对差的样本标准差是可估的。

## 口径声明（必须随结论）

* 配对键相同才成对；缺任一侧的对**直接剔除**并报出剔除数（不插补）。
* 窗口之间**不独立**（同数据、重叠区间）→ p 值偏乐观，视为**参考下界**。
* 不同产物（PIT 口径 vs 全目录口径）**不是独立样本**，分别报告、不合并。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alpha.alpha_survival_lab import excess_t_statistics  # noqa: E402

# 每条 = 一个 Δ 型结论。keys 是配对键（seed/window 视产物而定）。
DELTA_SPECS: List[Dict[str, Any]] = [
    {"label": "尾部剔除 V1 − V0（PIT 口径，5 窗口）",
     "file": "tdx_tail_exclusion_pit_summary.json",
     "a": "V1_excl_ret20_top20", "b": "V0_baseline", "keys": ("window",),
     "claim": "剔除 ret_20 最高 20% 后超额改善"},
    {"label": "尾部剔除 V2 − V1（PIT 口径，5 窗口）",
     "file": "tdx_tail_exclusion_pit_summary.json",
     "a": "V2_excl_ret20_volratio_top20", "b": "V1_excl_ret20_top20", "keys": ("window",),
     "claim": "再叠加剔除 vol_ratio 最高 20% 的增量效果"},
    {"label": "尾部剔除 V1 − V0（全目录口径，5 窗口）",
     "file": "tdx_tail_exclusion_allcsv_summary.json",
     "a": "V1_excl_ret20_top20", "b": "V0_baseline", "keys": ("window",),
     "claim": "同上，换股票池口径"},
    {"label": "多股票池重复：V1 − V0（4 抽样 × 2 窗口）",
     "file": "tdx_universe_replication_summary.json",
     "a": "V1_excl_ret20_top20", "b": "V0_baseline", "keys": ("seed", "window"),
     "claim": "换股票池后 V1 的优势是否复现"},
    {"label": "集中度 C10 − C5（3 抽样 × 1 窗口）",
     "file": "tdx_concentration_summary.json",
     "a": "C10_top10_10pct", "b": "C5_top5_25pct", "keys": ("seed", "window"),
     "claim": "提高分散度的增量效果"},
    {"label": "集中度 C20 − C5（3 抽样 × 1 窗口）",
     "file": "tdx_concentration_summary.json",
     "a": "C20_top20_5pct", "b": "C5_top5_25pct", "keys": ("seed", "window"),
     "claim": "同上（C20 为报告认定的最优档）"},
    {"label": "集中度 C30 − C20（3 抽样 × 1 窗口）",
     "file": "tdx_concentration_summary.json",
     "a": "C30_top30_3pct", "b": "C20_top20_5pct", "keys": ("seed", "window"),
     "claim": "继续提高分散度是否还有增益（报告称略回升）"},
]

METRIC = "annualized_excess_pct"

# ---------------------------------------------------------------------------
# 从**归档报告表格**转录的 Δ（逐窗口 JSON 只覆盖部分窗口，完整 5 窗口值在报告里）
#
# ⚠️ 这些值不是从 JSON 解析的，而是人工从归档报告表格转录 —— 故必须标注出处，
#    且**不得**在报告改写时静默漂移。归档报告是历史证据，不应再改。
# ---------------------------------------------------------------------------
TRANSCRIBED_DELTAS: List[Dict[str, Any]] = [
    {
        "label": "ADX 状态叠加 − 基线（5 窗口）",
        "source": "STEP1_3_EXECUTION_REPORT.md §2.2 表「Δ超额」列",
        "claim": "叠加 ADX 状态路由后超额改善（⚠️ 该改善包含「单纯降敞口」的机械减亏）",
        "deltas": [18.04, 20.56, 30.14, 20.44, 11.69],
        "caveat": "等效于在亏损策略上降低敞口 → Δ>0 是机械结果，不能归因于状态识别",
    },
    {
        "label": "ADX 状态叠加 − 恒定 0.5× 敞口（5 窗口）",
        "source": "STEP1_3_EXECUTION_REPORT.md §6.4 表「ADX − 常数」列",
        "claim": "扣除「单纯降敞口」后，状态识别本身是否还有贡献",
        "deltas": [5.87, 8.19, 9.94, -1.81, -7.07],
        "caveat": "叠加与常数的平均敞口并不相等，对照非严格敞口匹配",
    },
]


def _index(rows: List[Dict[str, Any]], variant: str,
           keys: Tuple[str, ...]) -> Dict[Tuple, float]:
    out: Dict[Tuple, float] = {}
    for r in rows:
        if r.get("variant") != variant:
            continue
        v = r.get(METRIC)
        if v is None:
            continue
        out[tuple(r.get(k) for k in keys)] = float(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Δ 型策略结论的配对统计量补记")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = Path(args.root)
    print("=" * 100)
    print("Δ 型策略结论的配对 t 检验（配对键：窗口/股票池抽样）")
    print("=" * 100)
    print(f"指标：{METRIC}（算术年化超额，百分点）")
    print("标准差一律用**样本**口径（n−1），与 t 检验一致\n")

    results: List[Dict[str, Any]] = []
    for spec in DELTA_SPECS:
        f = root / spec["file"]
        if not f.exists():
            print(f"【{spec['label']}】跳过：{spec['file']} 不存在")
            continue
        rows = json.loads(f.read_text(encoding="utf-8")).get("rows") or []
        a = _index(rows, spec["a"], spec["keys"])
        b = _index(rows, spec["b"], spec["keys"])
        common = sorted(set(a) & set(b))
        dropped = len(set(a) | set(b)) - len(common)
        if len(common) < 3:
            print(f"【{spec['label']}】配对 {len(common)} 对 < 3，不足以检验")
            continue
        diffs = [a[k] - b[k] for k in common]
        st = excess_t_statistics(diffs)
        mean_d = statistics.mean(diffs)
        sd_d = statistics.stdev(diffs)   # 样本标准差，与 t 检验口径一致
        n_pos = sum(1 for d in diffs if d > 0)
        print(f"【{spec['label']}】")
        print(f"  待验命题：{spec['claim']}")
        print(f"  配对 {len(common)} 对（剔除不配对 {dropped} 项）"
              f" · Δ 均值 {mean_d:+.2f}pp · Δ 标准差 {sd_d:.2f}pp · 为正 {n_pos}/{len(common)}")
        t = st["t"]
        p = st["p"]
        if t is None:
            print("  t / p：样本不足或差值无变异 → 无法判定\n")
        else:
            verdict = "显著（p<0.05）" if (p is not None and p < 0.05) else "不显著"
            print(f"  配对 t = {t:+.2f} · p = {p:.4f} → **{verdict}**")
            print(f"  95% 近似置信区间：{mean_d:+.2f} ± {1.96 * sd_d / (len(diffs) ** 0.5):.2f}pp\n")
        results.append({
            "label": spec["label"], "file": spec["file"],
            "a": spec["a"], "b": spec["b"], "claim": spec["claim"],
            "n_pairs": len(common), "n_dropped": dropped,
            "mean_delta_pp": mean_d, "sd_delta_pp": sd_d,
            "n_positive": n_pos, "t": t, "p": p,
            "significant": bool(p is not None and p < 0.05),
        })

    print("=" * 100)
    print("从归档报告表格转录的 Δ（逐窗口 JSON 未覆盖完整窗口）")
    print("=" * 100)
    for spec in TRANSCRIBED_DELTAS:
        diffs = [float(x) for x in spec["deltas"]]
        st = excess_t_statistics(diffs)
        mean_d = statistics.mean(diffs)
        sd_d = statistics.stdev(diffs)   # 样本标准差，与 t 检验口径一致
        n_pos = sum(1 for d in diffs if d > 0)
        print(f"【{spec['label']}】")
        print(f"  来源：{spec['source']}")
        print(f"  待验命题：{spec['claim']}")
        print(f"  逐窗口 Δ：{[round(x, 2) for x in diffs]}")
        print(f"  配对 {len(diffs)} 对 · Δ 均值 {mean_d:+.2f}pp · Δ 标准差 {sd_d:.2f}pp"
              f" · 为正 {n_pos}/{len(diffs)}")
        t = st["t"]
        p = st["p"]
        if t is None:
            print("  t / p：样本不足或差值无变异 → 无法判定\n")
        else:
            verdict = "显著（p<0.05）" if (p is not None and p < 0.05) else "**不显著**"
            print(f"  配对 t = {t:+.2f} · p = {p:.4f} → {verdict}")
            print(f"  95% 近似置信区间：{mean_d:+.2f} ± "
                  f"{1.96 * sd_d / (len(diffs) ** 0.5):.2f}pp")
        print(f"  ⚠️ {spec['caveat']}\n")
        results.append({
            "label": spec["label"], "source": spec["source"],
            "claim": spec["claim"], "transcribed": True,
            "deltas": diffs, "n_pairs": len(diffs),
            "mean_delta_pp": mean_d, "sd_delta_pp": sd_d,
            "n_positive": n_pos, "t": t, "p": p,
            "significant": bool(p is not None and p < 0.05),
            "caveat": spec["caveat"],
        })

    print("=" * 100)
    print("口径声明")
    print("=" * 100)
    print("  · 配对键相同才成对；缺任一侧的对直接剔除并报出数量（不插补）")
    print("  · 窗口之间**不独立**（同数据、重叠区间）→ p 值偏乐观，视为参考下界")
    print("  · 不同产物（PIT 口径 vs 全目录口径）不是独立样本，分别报告、不合并")
    print("  · 本检验只补记统计量，**不改变任何已归档的结论方向**")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "metric": METRIC, "results": results,
            "caveats": [
                "配对键相同才成对，缺侧剔除不插补",
                "窗口之间不独立，p 值偏乐观（参考下界）",
                "不同产物不是独立样本，分别报告",
            ],
        }, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(f"\n结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
