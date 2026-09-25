# -*- coding: utf-8 -*-
r"""H-D4 检验：涨跌停结构（一字涨停占比）是否预示负面收益。

事前登记见 ``ALPHA_HYPOTHESIS_PREREG_HD4.md`` —— 口径在跑之前已固定。

## 本脚本的关键不是"跑出 IC"，而是**正交化**

「一字板多」与 `max_ret_20`（已测 |t| = 7.64，方向 −1）高度可能共线 ——
一字板本身就是一次大涨。因此登记的判定以**残差 IC** 为准：

    顺序残差化：log_amount_20 → vol_20 → max_ret_20 → one_way_rate_20
    （顺序事前固定，不得依据 IC 结果调整）

若原始 IC 显著而残差 IC 不显著，结论必须是
「该效应完全由 `max_ret_20` 解释」→ **不成立**，不得因原始 IC 显著就宣称成立。

## 用法

::

    python scripts/run_limit_structure_study.py --dataset D:/tdx_dataset_v3 \
        --out reports/hd4_limit_structure.json
"""
from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_artifacts import write_final  # noqa: E402
from factors.factor_ic_lab import (  # noqa: E402
    build_panel,
    compute_factors,
    forward_return,
    orthogonalize_panel,
    spearman,
)

MIN_HISTORY = 60
SUBWINDOWS = [("2016-08-01", "2021-06-30"), ("2021-07-01", "2026-09-30")]
FACTOR = "one_way_rate_20"
# 事前固定的正交化顺序（登记 §4.1）—— 不得依据结果调整
ORTHO_ORDER = ["log_amount_20", "vol_20", "max_ret_20", FACTOR]
LOOKBACK = 20
# 因子在横截面上的「非零占比」中位数低于此值即判**退化**（见退化诊断）
DEGENERACY_FLOOR = 0.05


def _tstat(xs: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    sd = statistics.stdev(xs)
    if sd == 0:
        return None
    return statistics.mean(xs) / (sd / (len(xs) ** 0.5))


def _p(t: Optional[float]) -> Optional[float]:
    if t is None:
        return None
    return math.erfc(abs(t) / (2 ** 0.5))


def decide_verdict(resid_ic: Optional[float], t: Optional[float],
                   sub: List[Dict[str, Any]]) -> str:
    r"""按**事前登记**判定（``ALPHA_HYPOTHESIS_PREREG_HD4.md`` §5），**以残差 IC 为准**。

    * **强支持**：残差 IC < 0 且 t ≤ −2，且两子窗口残差 IC 同号（均 < 0）
      且至少一个 t ≤ −2；
    * **不成立**：残差 IC ≥ 0，**或两子窗口残差 IC 符号相反**；
    * **弱支持**：其余。

    原始 IC **不参与**本判定 —— 这是登记的核心约束：若效应完全由
    `max_ret_20` 解释，则本假设不成立，不得因原始 IC 显著而宣称成立。
    """
    if resid_ic is None:
        return "不成立"
    opposite = (len(sub) == 2 and sub[0]["resid_ic"] * sub[1]["resid_ic"] < 0)
    if resid_ic >= 0 or opposite:
        return "不成立"
    same_sign = len(sub) == 2 and all(s["resid_ic"] < 0 for s in sub)
    any_sig = any(s["t"] is not None and s["t"] <= -2 for s in sub)
    if t is not None and t <= -2 and same_sign and any_sig:
        return "强支持"
    return "弱支持"


def _limit_up(prev_close: float, ratio: float) -> float:
    """涨停价（四舍五入到分，与交易所口径一致；登记 §6.2 声明为近似）。"""
    return round(prev_close * (1.0 + ratio), 2)


def _one_way_rate(bars: List[Dict[str, Any]], i: int, lookback: int) -> Optional[float]:
    """近 ``lookback`` 日中「一字涨停」占比。样本不足或无有效 limit_ratio → ``None``。"""
    lo = max(1, i - lookback + 1)
    if i - lo + 1 < lookback:
        return None
    n = 0
    valid = 0
    for k in range(lo, i + 1):
        bar = bars[k]
        try:
            lr = float(bar.get("limit_ratio") or 0.0)
        except (TypeError, ValueError):
            continue
        if lr <= 0:
            continue
        try:
            prev_close = float(bars[k - 1]["close"])
            low = float(bar["low"])
        except (KeyError, TypeError, ValueError):
            continue
        valid += 1
        if abs(low - _limit_up(prev_close, lr)) < 0.005:
            n += 1
    if valid < lookback // 2:
        return None
    return n / lookback


def main() -> int:
    ap = argparse.ArgumentParser(description="H-D4 涨跌停结构检验（事前登记，含正交化）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--pool", default="")
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--min-cross-section", type=int, default=100)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    print("=" * 100)
    print("H-D4 检验 · 一字涨停占比 → 未来收益（事前登记，方向为负）")
    print("=" * 100)
    print(f"口径：前瞻 {args.horizon} 日 / 每 {args.step} 日调仓 / 回看 {LOOKBACK} 日")
    print("⚠️ 判定以**残差 IC** 为准（正交化顺序事前固定，不得调整）\n")

    t0 = time.time()
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(args.dataset, "stocks")
    pool_path = args.pool or os.path.join(args.dataset, "pool_v2.csv")
    codes: List[str] = []
    if os.path.exists(pool_path):
        import csv as _csv
        with open(pool_path, encoding="utf-8-sig", newline="") as fh:
            codes = [r["code"].zfill(6) for r in _csv.DictReader(fh)]
    if args.max_stocks > 0 and len(codes) > args.max_stocks:
        step = len(codes) / args.max_stocks
        codes = [codes[int(i * step)] for i in range(args.max_stocks)]

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
        if len(bars) >= args.min_rows:
            data[c] = bars
    print(f"行情：{len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)

    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    panel_days = build_panel(data)
    rebal = panel_days[MIN_HISTORY::args.step]
    print(f"调仓日 {len(rebal)} 个（{rebal[0]} ~ {rebal[-1]}）\n", flush=True)

    periods: List[Dict[str, Any]] = []
    corr_diag: List[float] = []
    sizes: List[int] = []
    nonzero_frac: List[float] = []
    skipped_no_limit = 0

    for i, day in enumerate(rebal, 1):
        f_vals: List[float] = []
        fwd: List[float] = []
        ctrl: Dict[str, List[float]] = {k: [] for k in ORTHO_ORDER[:-1]}
        maxret: List[float] = []
        for code, bars in data.items():
            bar_i = idx_map[code].get(day)
            if bar_i is None:
                continue
            fr = forward_return(bars, bar_i, args.horizon)
            if fr is None:
                continue
            rate = _one_way_rate(bars, bar_i, LOOKBACK)
            if rate is None:
                skipped_no_limit += 1
                continue
            pf = compute_factors(bars, bar_i)
            if pf is None:
                continue
            # 逐个取值并显式判 None —— 列表推导式里的 None 无法被 mypy 收窄
            cv: List[float] = []
            ok = True
            for k in ORTHO_ORDER[:-1]:
                v = pf.get(k)
                if v is None:
                    ok = False
                    break
                cv.append(float(v))
            if not ok:
                continue
            f_vals.append(rate)
            fwd.append(fr)
            for k, v in zip(ORTHO_ORDER[:-1], cv, strict=True):
                ctrl[k].append(v)
            maxret.append(float(pf["max_ret_20"]))
        if len(f_vals) < args.min_cross_section:
            continue
        sizes.append(len(f_vals))
        nonzero_frac.append(sum(1 for v in f_vals if v > 0) / len(f_vals))
        periods.append({
            "date": day,
            "factors": {**ctrl, FACTOR: f_vals},
            "forward": fwd,
        })
        rho = spearman(f_vals, maxret)
        if rho is not None:
            corr_diag.append(rho)
        if i % 200 == 0:
            print(f"  ... {i}/{len(rebal)}  有效期 {len(periods)}", flush=True)

    if len(periods) < 10:
        print(f"有效期数不足（{len(periods)} < 10），无法检验。", flush=True)
        return 2

    # ---- 原始 IC（仅报告，不参与判定）----
    raw_ic = [v for v in (spearman(p["factors"][FACTOR], p["forward"])
                          for p in periods) if v is not None]
    raw_mean = statistics.mean(raw_ic)
    raw_t = _tstat(raw_ic)
    print("\n" + "=" * 100)
    print("原始 IC（**仅报告，不参与判定** —— 登记 §5.1）")
    print("=" * 100)
    print(f"  有效期数 {len(raw_ic)} | IC 均值 {raw_mean:+.4f} | t = {raw_t:+.2f} | "
          f"p = {_p(raw_t):.4f}" if raw_t is not None else
          f"  有效期数 {len(raw_ic)} | IC 均值 {raw_mean:+.4f} | t = —")

    # ---- 正交化 ----
    print("\n" + "=" * 100)
    print("顺序残差化（顺序事前固定：" + " → ".join(ORTHO_ORDER) + "）")
    print("=" * 100)
    orth = orthogonalize_panel(
        {"periods": periods, "panel_len": len(periods),
         "factor_names": list(ORTHO_ORDER), "horizon": args.horizon,
         "step": args.step},
        method="sequential", factors=list(ORTHO_ORDER), order=list(ORTHO_ORDER),
        min_cross_section=args.min_cross_section)
    n_orth = sum(1 for p in orth["periods"] if p.get("orthogonalized"))
    print(f"  成功正交化的期数：{n_orth} / {len(periods)}")

    resid: List[Tuple[str, float]] = []
    for p in orth["periods"]:
        if not p.get("orthogonalized"):
            continue
        ic_r = spearman(p["factors"][FACTOR], p["forward"])
        if ic_r is not None:
            resid.append((str(p["date"]), ic_r))

    if len(resid) < 10:
        print(f"  残差 IC 有效期数不足（{len(resid)} < 10），无法判定。", flush=True)
        return 2

    r_ic = [v for _, v in resid]
    r_mean = statistics.mean(r_ic)
    r_t = _tstat(r_ic)
    print(f"  **残差 IC 均值** {r_mean:+.4f} | t = {r_t:+.2f} | p = {_p(r_t):.4f}")

    print("\n" + "=" * 100)
    print("独立子窗口（事前划分，不重叠；以**残差 IC** 为准）")
    print("=" * 100)
    sub: List[Dict[str, Any]] = []
    for lo, hi in SUBWINDOWS:
        seg = [v for dd, v in resid if lo <= dd <= hi]
        if len(seg) < 10:
            print(f"  {lo} ~ {hi}: 期数不足（{len(seg)}）")
            continue
        st = _tstat(seg)
        print(f"  {lo} ~ {hi}: n={len(seg):>4}  残差 IC={statistics.mean(seg):+.4f}  "
              f"t={st:+.2f}  p={_p(st):.4f}" if st is not None else
              f"  {lo} ~ {hi}: n={len(seg)}  残差 IC={statistics.mean(seg):+.4f}  t=—")
        sub.append({"start": lo, "end": hi, "n": len(seg),
                    "resid_ic": statistics.mean(seg), "t": st, "p": _p(st)})

    # ---- 退化诊断（**登记未预设该情形，2026-09-25 实测暴露**）----
    # `one_way_rate_20` 在绝大多数观测上等于 0（实测 97.8%），
    # 此时截面秩 IC 主要由极少数非零观测驱动，且 Gram-Schmidt 在近乎退化的
    # 变量上做残差会产出**不稳定的数值 artifact**（符号反转即其表现）。
    med_nonzero = statistics.median(nonzero_frac) if nonzero_frac else 0.0
    degenerate = med_nonzero < DEGENERACY_FLOOR

    # ---- 诊断：不含 max_ret_20 的对照正交化（**不影响判定**）----
    # 目的：判断符号反转是"max_ret_20 特有"还是"正交化本身的普遍现象"。
    # 若只控 log_amount_20 + vol_20 时残差 IC 仍为正，则说明反转**不是** max_ret_20 造成的。
    diag_order = ["log_amount_20", "vol_20", FACTOR]
    orth2 = orthogonalize_panel(
        {"periods": periods, "panel_len": len(periods),
         "factor_names": diag_order, "horizon": args.horizon, "step": args.step},
        method="sequential", factors=diag_order, order=diag_order,
        min_cross_section=args.min_cross_section)
    diag_ic: List[float] = []
    for p2 in orth2["periods"]:
        if not p2.get("orthogonalized"):
            continue
        ic2 = spearman(p2["factors"][FACTOR], p2["forward"])
        if ic2 is not None:
            diag_ic.append(ic2)
    diag_mean = statistics.mean(diag_ic) if diag_ic else None
    diag_t = _tstat(diag_ic) if diag_ic else None

    # ---- 共线诊断 ----
    print("\n" + "=" * 100)
    print("共线诊断（登记 §4.1 要求）")
    print("=" * 100)
    if corr_diag:
        print(f"  `{FACTOR}` 与 `max_ret_20` 的平均截面秩相关 = "
              f"{statistics.mean(corr_diag):+.4f}（{len(corr_diag)} 期）")
        print("  → 相关性越高，原始 IC 越可能只是 `max_ret_20` 的重述")
    if diag_mean is not None:
        print(f"\n  对照：只控 `log_amount_20`+`vol_20`（**不含** `max_ret_20`）时，"
              f"残差 IC = {diag_mean:+.4f}（t = {diag_t:+.2f}，n = {len(diag_ic)}）")
        print("  → 若该值仍为正，说明符号反转**不是** `max_ret_20` 单独造成的，")
        print("     而是**顺序残差化本身的普遍现象**，应作为方法论警示而非因子结论。")

    # ---- 退化诊断输出 ----
    print("\n" + "=" * 100)
    print("⚠️ 因子退化诊断（**登记未预设该情形**）")
    print("=" * 100)
    print(f"  `{FACTOR}` 每期非零占比：中位 {med_nonzero:.2%} · "
          f"最小 {min(nonzero_frac):.2%} · 最大 {max(nonzero_frac):.2%}")
    print(f"  判据：非零占比中位 < {DEGENERACY_FLOOR:.0%} → 判**退化**")
    print(f"  结论：{'⚠️ **因子退化**' if degenerate else '未退化'}")
    if degenerate:
        print("  → 截面秩 IC 主要由极少数非零观测驱动；Gram-Schmidt 在近乎退化的")
        print("     变量上做残差会产出**不稳定的数值 artifact**（符号反转即其表现）。")
        print("  → **本假设在本数据集上不可靠地检验**。按登记的机械判定仍为「不成立」")
        print("     （残差 IC ≥ 0），但该判定**不应被赋予实质意义**。")

    # ---- 判定 ----
    print("\n" + "=" * 100)
    print("判定（事前登记口径，**以残差 IC 为准**）")
    print("=" * 100)
    verdict = decide_verdict(r_mean, r_t, sub)
    print(f"  原始 IC = {raw_mean:+.4f}（t = {raw_t:+.2f}）— 仅报告")
    print(f"  残差 IC = {r_mean:+.4f}（t = {r_t:+.2f}）— **判定依据**")
    print(f"  判定：**{verdict}**")
    # ⚠️ 两种不同的失败原因必须分开陈述（2026-09-25 试跑时曾把二者混为一谈）：
    #   ① 残差 IC 显著但**方向为正** → 效应被 max_ret_20 解释后**反转**；
    #   ② 残差 IC 不显著 → 无增量信息。
    # 两者都判「不成立」，但解释完全不同，不能都写成"不显著"。
    if raw_t is not None and raw_t <= -2:
        if r_t is not None and r_t >= 2:
            print("\n  ⚠️ 原始 IC 显著为负，但**残差 IC 显著为正**（t = "
                  f"{r_t:+.2f}）→ 按登记 §5.1：")
            print("     扣掉 `max_ret_20` 后效应**方向反转** —— 原始负 IC 完全由")
            print("     `max_ret_20` 解释；`one_way_rate_20` 的独立成分与假设方向**相反**。")
            print("     → 结论为**不成立**（方向不符），**不得**改述为「反向有效」。")
        elif r_t is None or abs(r_t) < 2:
            print("\n  ⚠️ 原始 IC 显著而**残差 IC 不显著** → 按登记 §5.1：")
            print("     「该效应**完全由 `max_ret_20` 解释**，`one_way_rate_20` 无增量信息」")
            print("     → 结论为**不成立**，不得因原始 IC 显著就宣称假设成立。")

    print("\n" + "=" * 100)
    print("已知缺陷声明（登记 §6）")
    print("=" * 100)
    print(f"  · 因无有效 limit_ratio 而跳过的观测：{skipped_no_limit:,} 个")
    print("    （含新股上市前 5 日与退市整理期 —— 这两类不设涨跌幅限制）")
    print("  · 涨停价用 round(prev_close×(1+ratio), 2) 近似，极低价股可能有特殊处理")
    print("  · limit_ratio 的 PIT 修正仅覆盖创业板改革前与主板 ST 两处")
    print("  · ⚠️ 一字板当日**事实上不可买入**（这正是其定义）→ 信号的可交易性天然受限")
    print("  · 未扣除交易成本；结论不构成投资建议")

    write_final(args.out, {
        "hypothesis": "H-D4",
        "factor": FACTOR,
        "direction": "negative",
        "raw_ic_mean": raw_mean, "raw_t": raw_t, "raw_n": len(raw_ic),
        "resid_ic_mean": r_mean, "resid_t": r_t, "resid_n": len(resid),
        "subwindows": sub,
        "ortho_order": ORTHO_ORDER,
        "ortho_success_periods": n_orth,
        "corr_with_max_ret_20": (statistics.mean(corr_diag) if corr_diag else None),
        "diag_resid_ic_without_max_ret_20": diag_mean,
        "diag_resid_t_without_max_ret_20": diag_t,
        "verdict": verdict,
        "nonzero_frac_median": med_nonzero,
        "degenerate": degenerate,
        "degeneracy_floor": DEGENERACY_FLOOR,
        "skipped_no_limit_ratio": skipped_no_limit,
        "args": vars(args),
        "elapsed_sec": round(time.time() - t0, 1),
    })
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
