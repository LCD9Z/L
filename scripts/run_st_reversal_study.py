# -*- coding: utf-8 -*-
r"""H-D3 检验：ST 困境反转（ST 组未来收益是否高于非 ST 组）。

事前登记见 ``ALPHA_HYPOTHESIS_PREREG_HD3.md`` —— 口径在跑之前已固定。

## 本脚本的核心不是"跑出 Δ"，而是**可实现性检查**

ST 股票的"超额"极可能不可实现（机构禁买、流动性差、涨跌停受限）。
故登记要求：主检验显著**且** §5.3 三项可实现性检查**全部通过**，才可称「存在 Alpha」；
否则结论只能是「**存在定价偏离，但不可实现**」。

三项检查：
* **A 流动性**：ST 组成交额中位数 ≥ 非 ST 组的 10%
* **B 剔除不可成交**：剔除「T+1 开盘即涨停」的观测后，Δ 仍 > 0
* **C 涨跌停约束**：数据已应用 v3 的 `limit_ratio`（含 ST 的 5% 档）

## 用法

::

    python scripts/run_st_reversal_study.py --dataset D:/tdx_dataset_v3 \
        --out reports/hd3_st_reversal.json
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_artifacts import write_final  # noqa: E402
from factors.factor_ic_lab import build_panel, forward_return, spearman  # noqa: E402
from exchange_rules import is_st_flag  # noqa: E402

MIN_HISTORY = 60
SUBWINDOWS = [("2016-08-01", "2021-06-30"), ("2021-07-01", "2026-09-30")]
MIN_ST_CROSS = 10          # ST 子样本判「样本不足」的阈值（登记 §5.2）
LIQUIDITY_FLOOR = 0.10     # ST 组成交额须达非 ST 组的比例（登记 §5.3 A）


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
    import math
    return math.erfc(abs(t) / (2 ** 0.5))


def decide_verdict(mean_delta: Optional[float], t: Optional[float],
                   sub: List[Dict[str, Any]], realizable: bool) -> str:
    r"""按**事前登记**判定（``ALPHA_HYPOTHESIS_PREREG_HD3.md`` §5.1）。

    * **强支持**：Δ > 0 且 t ≥ 2，且两子窗口同号（均 > 0）且至少一个 t ≥ 2，
      且**通过可实现性检查**；
    * **不成立**：Δ ≤ 0，或两子窗口 Δ 符号相反；
    * **弱支持**：其余（Δ > 0 且 t ≥ 2，但子窗口不一致**或**未通过可实现性检查）。
    """
    if mean_delta is None:
        return "不成立"
    opposite = (len(sub) == 2 and sub[0]["delta"] * sub[1]["delta"] < 0)
    if mean_delta <= 0 or opposite:
        return "不成立"
    if t is None or t < 2:
        return "弱支持"
    same_sign = len(sub) == 2 and all(s["delta"] > 0 for s in sub)
    any_sig = any(s["t"] is not None and s["t"] >= 2 for s in sub)
    if same_sign and any_sig and realizable:
        return "强支持"
    return "弱支持"


def _limit_up_price(prev_close: float, ratio: float) -> float:
    """涨停价（四舍五入到分，与交易所一致）。"""
    return round(prev_close * (1.0 + ratio), 2)


def main() -> int:
    ap = argparse.ArgumentParser(description="H-D3 ST 困境反转检验（事前登记）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--pool", default="")
    ap.add_argument("--fundamentals", default="D:/tdx_dataset_v3/fundamentals.jsonl")
    ap.add_argument("--disclosures", default="D:/tdx_dataset_v3/disclosure_dates.jsonl")
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--min-cross-section", type=int, default=100)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    print("=" * 100)
    print("H-D3 检验 · ST 困境反转（事前登记，方向为正；含可实现性检查）")
    print("=" * 100)
    print(f"口径：前瞻 {args.horizon} 日 / 每 {args.step} 日调仓 / 对照=非 ST 组\n")

    t0 = time.time()
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(args.dataset, "stocks")
    codes: List[str] = []
    pool_path = args.pool or os.path.join(args.dataset, "pool_v2.csv")
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

    # 财务（供 H-D3b 交互项）
    from pit.pit_fundamentals import PitFundamentals, load_disclosures, load_records
    pf: Optional[PitFundamentals] = None
    if os.path.exists(args.fundamentals):
        recs = load_records(args.fundamentals)
        pf = PitFundamentals(recs, load_disclosures(args.disclosures))
        print(f"财务：{len(pf):,} 条", flush=True)

    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    panel = build_panel(data)
    rebal = panel[MIN_HISTORY::args.step]
    print(f"调仓日 {len(rebal)} 个（{rebal[0]} ~ {rebal[-1]}）\n", flush=True)

    deltas: List[Tuple[str, float]] = []          # (day, Δ)
    deltas_excl: List[Tuple[str, float]] = []     # 剔除不可成交后的 Δ
    st_amounts: List[float] = []
    nonst_amounts: List[float] = []
    st_sizes: List[int] = []
    cyb_st = 0
    st_total = 0
    b_series: List[Tuple[str, float]] = []        # H-D3b：ST 内 IC
    excluded_unbuyable = 0
    used_limit_ratio = 0

    for i, day in enumerate(rebal, 1):
        st_r: List[float] = []
        non_r: List[float] = []
        st_r_ok: List[float] = []                 # 剔除不可成交后
        non_r_ok: List[float] = []
        b_vals: List[float] = []
        b_fwd: List[float] = []
        for code, bars in data.items():
            bar_i = idx_map[code].get(day)
            if bar_i is None:
                continue
            fr = forward_return(bars, bar_i, args.horizon)
            if fr is None:
                continue
            bar = bars[bar_i]
            is_st = is_st_flag(bar.get("is_st"))
            amt = bar.get("amount")
            try:
                amt_v = float(amt) if amt is not None else 0.0
            except (TypeError, ValueError):
                amt_v = 0.0
            if is_st:
                st_total += 1
                if code.startswith("300"):
                    cyb_st += 1
                st_r.append(fr)
                if amt_v > 0:
                    st_amounts.append(amt_v)
            else:
                non_r.append(fr)
                if amt_v > 0:
                    nonst_amounts.append(amt_v)

            # 可实现性 B：T+1 开盘是否即涨停（涨停则买不进）
            entry_i = bar_i + 1
            unbuyable = False
            if entry_i < len(bars):
                try:
                    lr = float(bars[entry_i].get("limit_ratio") or 0.0)
                except (TypeError, ValueError):
                    lr = 0.0
                if lr > 0:
                    used_limit_ratio += 1
                    prev_close = float(bar["close"])
                    op = float(bars[entry_i].get("open") or 0.0)
                    if op >= _limit_up_price(prev_close, lr):
                        unbuyable = True
            if unbuyable:
                excluded_unbuyable += 1
            else:
                (st_r_ok if is_st else non_r_ok).append(fr)

            # H-D3b：ST 子样本内，业绩同比增速 vs 前瞻收益
            if is_st and pf is not None:
                f = pf.factors_as_of(code, day, price=float(bar["close"]))
                g = (f or {}).get("net_profit_growth")
                if g is not None:
                    b_vals.append(float(g))
                    b_fwd.append(fr)

        if len(st_r) + len(non_r) < args.min_cross_section:
            continue
        st_sizes.append(len(st_r))
        if st_r and non_r:
            deltas.append((day, statistics.mean(st_r) - statistics.mean(non_r)))
        if st_r_ok and non_r_ok:
            deltas_excl.append(
                (day, statistics.mean(st_r_ok) - statistics.mean(non_r_ok)))
        if len(b_vals) >= MIN_ST_CROSS:
            ic = spearman(b_vals, b_fwd)
            if ic is not None:
                b_series.append((day, ic))

        if i % 200 == 0:
            print(f"  ... {i}/{len(rebal)}  有效 Δ {len(deltas)} 期", flush=True)

    if len(deltas) < 10:
        print(f"有效期数不足（{len(deltas)} < 10），无法检验。", flush=True)
        return 2

    d = [v for _, v in deltas]
    mean_delta = statistics.mean(d)
    t = _tstat(d)
    pv = _p(t)

    print("\n" + "=" * 100)
    print("主检验 H-D3a：ST 组 − 非 ST 组（前瞻 5 日收益差）")
    print("=" * 100)
    print(f"  有效调仓期数        : {len(d)}")
    print(f"  Δ 均值              : {mean_delta:+.4%}")
    print(f"  Δ 标准差            : {statistics.stdev(d):.4%}")
    print(f"  t（H0: Δ=0）        : {t:+.2f}" if t is not None else "  t: —")
    print(f"  p（双尾）           : {pv:.4f}" if pv is not None else "  p: —")
    print(f"  ST 组截面数（中位/最小）: {statistics.median(st_sizes):.0f} / {min(st_sizes)}")

    print("\n" + "=" * 100)
    print("独立子窗口（事前划分，不重叠）")
    print("=" * 100)
    sub: List[Dict[str, Any]] = []
    for lo, hi in SUBWINDOWS:
        seg = [v for dd, v in deltas if lo <= dd <= hi]
        if len(seg) < 10:
            print(f"  {lo} ~ {hi}: 期数不足（{len(seg)}）")
            continue
        mt = _tstat(seg)
        print(f"  {lo} ~ {hi}: n={len(seg):>4}  Δ={statistics.mean(seg):+.4%}  "
              f"t={mt:+.2f}  p={_p(mt):.4f}" if mt is not None else
              f"  {lo} ~ {hi}: n={len(seg)}  Δ={statistics.mean(seg):+.4%}  t=—")
        sub.append({"start": lo, "end": hi, "n": len(seg),
                    "delta": statistics.mean(seg), "t": mt, "p": _p(mt)})

    # ---- 可实现性检查（登记 §5.3）----
    print("\n" + "=" * 100)
    print("⚠️ 可实现性检查（登记 §5.3 —— 未通过则不得称「存在 Alpha」）")
    print("=" * 100)
    med_st = statistics.median(st_amounts) if st_amounts else 0.0
    med_non = statistics.median(nonst_amounts) if nonst_amounts else 0.0
    ratio = (med_st / med_non) if med_non else 0.0
    check_a = ratio >= LIQUIDITY_FLOOR
    print(f"  A 流动性：ST 组成交额中位 {med_st:,.0f} / 非 ST 组 {med_non:,.0f}"
          f" = {ratio:.1%}（要求 ≥ {LIQUIDITY_FLOOR:.0%}）→ "
          f"{'✅ 通过' if check_a else '❌ 未通过'}")

    de = [v for _, v in deltas_excl]
    mean_excl = statistics.mean(de) if de else None
    te = _tstat(de)
    check_b = mean_excl is not None and mean_excl > 0
    print(f"  B 剔除不可成交：剔除 {excluded_unbuyable:,} 个「T+1 开盘即涨停」观测后，"
          f"Δ = {mean_excl:+.4%}（t = {te:+.2f}）→ "
          f"{'✅ 通过' if check_b else '❌ 未通过'}" if mean_excl is not None
          else "  B 剔除不可成交：无有效样本")
    print(f"  C 涨跌停约束：{used_limit_ratio:,} 个观测带有效 limit_ratio"
          f"（含 ST 的 5% 档）→ {'✅ 通过' if used_limit_ratio > 0 else '❌ 未通过'}")
    realizable = check_a and check_b and used_limit_ratio > 0
    print(f"\n  三项合计：{'✅ **通过**' if realizable else '❌ **未通过**'}")

    # ---- 次检验 H-D3b ----
    print("\n" + "=" * 100)
    print("次检验 H-D3b：ST 子样本内「业绩同比增速」的 IC")
    print("=" * 100)
    b_ic: List[float] = [v for _, v in b_series]
    b_sub: List[Dict[str, Any]] = []
    if len(b_ic) >= 10:
        bt = _tstat(b_ic)
        print(f"  有效期数 {len(b_ic)} | IC 均值 {statistics.mean(b_ic):+.4f} | "
              f"t = {bt:+.2f} | p = {_p(bt):.4f}")
        for lo, hi in SUBWINDOWS:
            seg = [v for dd, v in b_series if lo <= dd <= hi]
            if len(seg) < 10:
                continue
            st_ = _tstat(seg)
            b_sub.append({"start": lo, "end": hi, "n": len(seg),
                          "ic": statistics.mean(seg), "t": st_})
        if statistics.median(st_sizes) < MIN_ST_CROSS:
            print(f"  ⚠️ ST 截面中位 {statistics.median(st_sizes):.0f} < {MIN_ST_CROSS}"
                  " → 按登记 §5.2 判「样本不足」，**不得出结论**")
            b_verdict = "样本不足"
        else:
            opp_b = len(b_sub) == 2 and b_sub[0]["ic"] * b_sub[1]["ic"] < 0
            b_verdict = ("不成立" if (statistics.mean(b_ic) <= 0 or opp_b) else
                         ("强支持" if (bt is not None and bt >= 2) else "弱支持"))
        print(f"  判定：**{b_verdict}**")
    else:
        print(f"  有效期数不足（{len(b_ic)} < 10）")
        b_verdict = "样本不足"

    # ---- 判定 ----
    print("\n" + "=" * 100)
    print("判定（事前登记口径，方向为正）")
    print("=" * 100)
    verdict = decide_verdict(mean_delta, t, sub, realizable)
    print(f"  Δ 均值 {mean_delta:+.4%}（假设方向为**正**）")
    print(f"  可实现性：{'通过' if realizable else '未通过'}")
    print(f"  判定：**{verdict}**")
    if verdict == "弱支持" and mean_delta > 0 and not realizable:
        print("\n  ⚠️ 主检验方向为正但**未通过可实现性检查** → 结论应表述为：")
        print("     「**存在定价偏离，但不可实现**」")
        print("     **不得**表述为「存在 Alpha」。")
    if mean_delta < 0:
        print("\n  ⚠️ Δ 为负 —— 与假设方向相反。按登记，结论为「不成立」，")
        print("     且**不得**改述为「反向有效」。")

    print("\n" + "=" * 100)
    print("已知缺陷声明（登记 §6）")
    print("=" * 100)
    cyb_share = cyb_st / st_total if st_total else 0.0
    print(f"  · ST 观测 {st_total:,} 个，其中创业板占 {cyb_share:.1%}")
    print("  · ⚠️ 创业板 ST 标记**仅 2020 年起有值**（2016~2019 全为 0），"
          "故创业板部分样本不完整")
    print("  · st_basis 含「官方(深交所)」与「推断(±5%涨跌幅限制)」两类；"
          "推断法对改革前创业板(±10%)失效")
    print("  · 未覆盖：新股前 5 日与退市整理期不设涨跌幅限制")
    print("  · 未扣除交易成本；结论不构成投资建议")

    write_final(args.out, {
        "hypothesis": "H-D3",
        "delta_mean": mean_delta, "delta_std": statistics.stdev(d),
        "t": t, "p": pv, "n_periods": len(d),
        "subwindows": sub,
        "realizability": {
            "liquidity_ratio": ratio, "liquidity_pass": check_a,
            "delta_after_excluding_unbuyable": mean_excl,
            "t_after_excluding": te, "excluded_unbuyable": excluded_unbuyable,
            "limit_ratio_obs": used_limit_ratio,
            "all_pass": realizable,
        },
        "hd3b_ic_mean": (statistics.mean(b_ic) if b_ic else None),
        "hd3b_t": (_tstat(b_ic) if b_ic else None),
        # ⚠️ 登记的 H-D3b 判定条件含「两子窗口同号」，故**必须**落盘子窗口
        "hd3b_subwindows": b_sub,
        "hd3b_verdict": b_verdict,
        "st_median_cross_section": statistics.median(st_sizes),
        "cyb_share_of_st": cyb_share,
        "verdict": verdict,
        "args": vars(args),
        "elapsed_sec": round(time.time() - t0, 1),
    })
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
