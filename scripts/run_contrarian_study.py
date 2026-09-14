# -*- coding: utf-8 -*-
"""复合「反转 + 低波 + 小规模 + 非流动性」打分假设检验。

**假设、方向、方法、判定标准均已在 `ALPHA_HYPOTHESIS_PREREG.md` 事前登记**，
本文件只是其实现，不得在看到结果后调整任何参数。

用法::

    python run_contrarian_study.py --dataset D:/tdx_dataset
    python run_contrarian_study.py --dataset D:/tdx_dataset --max-stocks 800 --out out.json

判定（事前设定）：
    强支持 = 全样本 IC>0 且 t>=2，且两子窗口同号且至少一个 t>=2，且 Q5-Q1>0
    不成立 = IC<=0 或两子窗口符号相反
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.factor_ic_lab import (  # noqa: E402
    MIN_HISTORY,
    _t_pvalue,
    build_panel,
    compute_factors,
    forward_return,
    spearman,
)

# ---------------------------------------------------------------------------
# 事前登记：因子方向（+1 = 该因子越高越好；-1 = 越低越好）
# ---------------------------------------------------------------------------
SIGNS: Dict[str, int] = {
    "ret_20": -1,
    "ret_5": -1,
    "vol_20": -1,
    "log_amount_20": -1,
    "max_ret_20": -1,
    "vol_ratio": -1,
    "amihud_20": +1,
}

SUBPERIODS = [
    ("2021-08 ~ 2023-12", "2021-08-01", "2023-12-31"),
    ("2024-01 ~ 2026-09", "2024-01-01", "2026-09-30"),
]


def _load(dataset: str, max_stocks: int, min_rows: int = 200) -> Dict[str, Any]:
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    data: Dict[str, Any] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        bars = load_certified_csv(p, m)
        if len(bars) >= min_rows:
            data[c] = bars
    return data


def _pct_rank(values: Sequence[float]) -> List[float]:
    """截面秩标准化到 [0,1]（对离群值稳健，事前登记的方法）。"""
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    for pos, i in enumerate(order):
        out[i] = pos / (n - 1)
    return out


def _ic_stats(ics: Sequence[float]) -> Optional[Dict[str, Any]]:
    n = len(ics)
    if n < 3:
        return None
    mean = sum(ics) / n
    var = sum((x - mean) ** 2 for x in ics) / (n - 1)
    std = var ** 0.5
    t = mean / (std / (n ** 0.5)) if std > 0 else 0.0
    return {
        "ic_mean": mean,
        "ic_std": std,
        "icir": (mean / std) if std > 0 else 0.0,
        "t": t,
        "p": _t_pvalue(t, n - 1),
        "n_periods": n,
        "hit_rate": sum(1 for x in ics if x > 0) / n,
    }


def run_study(
    data: Dict[str, Any],
    horizon: int = 5,
    step: int = 5,
    start: Optional[str] = None,
    end: Optional[str] = None,
    min_cross_section: int = 50,
) -> Dict[str, Any]:
    idx_map = {
        code: {str(b["date"]): k for k, b in enumerate(bars)}
        for code, bars in data.items()
    }
    panel = build_panel(data)
    if start:
        panel = [d for d in panel if d >= start]
    if end:
        panel = [d for d in panel if d <= end]
    rebal = panel[MIN_HISTORY::step]

    ic_series: List[float] = []
    sizes: List[int] = []
    q_sum = [0.0] * 5
    q_cnt = [0] * 5
    all_fwd: List[float] = []

    for day in rebal:
        rows = []
        for code, bars in data.items():
            i = idx_map[code].get(day)
            if i is None:
                continue
            fac = compute_factors(bars, i)
            if fac is None:
                continue
            fr = forward_return(bars, i, horizon)
            if fr is None:
                continue
            rows.append((fac, fr))
        if len(rows) < min_cross_section:
            continue

        usable = [
            k for k in SIGNS
            if all(r[0].get(k) is not None for r in rows)
        ]
        if not usable:
            continue

        comp = [0.0] * len(rows)
        for k in usable:
            pr = _pct_rank([float(r[0][k]) for r in rows])
            s = SIGNS[k]
            for idx, v in enumerate(pr):
                comp[idx] += s * v

        fwds = [r[1] for r in rows]
        ic = spearman(comp, fwds)
        if ic is None:
            continue
        ic_series.append(ic)
        all_fwd.extend(fwds)
        sizes.append(len(rows))

        # 分位组：期内按 composite 分组（Q1 最低 → Q5 最高）
        order = sorted(range(len(rows)), key=lambda i: comp[i])
        m = len(order)
        for g in range(5):
            lo = int(g * m / 5)
            hi = int((g + 1) * m / 5)
            for j in order[lo:hi]:
                q_sum[g] += fwds[j]
                q_cnt[g] += 1

    out: Dict[str, Any] = {
        "stats": _ic_stats(ic_series),
        "avg_cross_section": (sum(sizes) / len(sizes)) if sizes else 0,
        "mean_universe_forward_return": (sum(all_fwd) / len(all_fwd)) if all_fwd else 0.0,
    }
    if any(q_cnt):
        grp = [(q_sum[g] / q_cnt[g]) if q_cnt[g] else 0.0 for g in range(5)]
        out["quintiles"] = {
            "group_mean_returns": grp,
            "long_short_pct": (grp[4] - grp[0]) * 100,
        }
    return out


def _verdict(st: Optional[Dict[str, Any]], subs: Dict[str, Any],
             q: Optional[Dict[str, Any]]) -> str:
    if not st:
        return "证据不足"
    ic, t = st["ic_mean"], st["t"]
    if ic <= 0:
        return "**不成立（IC ≤ 0）**"
    sub_ics = [v["stats"]["ic_mean"] for v in subs.values() if v.get("stats")]
    sub_ts = [v["stats"]["t"] for v in subs.values() if v.get("stats")]
    same_sign = len(sub_ics) == 2 and (sub_ics[0] > 0) == (sub_ics[1] > 0)
    if not same_sign:
        return "**不成立（子窗口符号相反）**"
    if t >= 2 and max(abs(x) for x in sub_ts) >= 2 and q and q["long_short_pct"] > 0:
        return "**强支持**"
    return "弱支持"


def main() -> int:
    ap = argparse.ArgumentParser(description="复合反转打分假设检验（事前登记）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    print("=" * 88)
    print("复合【反转 + 低波 + 小规模 + 非流动性】打分 · 假设检验（事前登记 H-C1）")
    print("=" * 88)
    print("方向：" + "  ".join(f"{k}{'+' if v > 0 else '-'}" for k, v in SIGNS.items()))

    t0 = time.time()
    print("[1/3] 加载数据 ...")
    data = _load(args.dataset, args.max_stocks)
    n_rows = sum(len(v) for v in data.values())
    print(f"      股票 {len(data):,} 只 / {n_rows:,} 行  ({time.time()-t0:.0f}s)")

    print("[2/3] 全样本 IC 检验 ...")
    full = run_study(data, args.horizon, args.step)
    st = full["stats"]
    if st:
        print(f"      期数 {st['n_periods']}  平均截面 {full['avg_cross_section']:.0f} 只  "
              f"全池前瞻收益 {full['mean_universe_forward_return']*100:+.2f}%")
        print(f"      IC {st['ic_mean']:+.4f}  ICIR {st['icir']:+.3f}  "
              f"t {st['t']:+.2f}  p {st['p']:.4f}  正IC占比 {st['hit_rate']:.1%}")
    else:
        print("      证据不足（有效期数过少）")

    print("[3/3] 子窗口稳定性 ...")
    subs = {}
    for label, s, e in SUBPERIODS:
        r = run_study(data, args.horizon, args.step, start=s, end=e)
        subs[label] = r
        stx = r["stats"]
        if stx:
            print(f"      【{label}】期数 {stx['n_periods']:>3}  IC {stx['ic_mean']:+.4f}  "
                  f"t {stx['t']:+.2f}")
        else:
            print(f"      【{label}】证据不足")

    q = full.get("quintiles")
    if q:
        g = [x * 100 for x in q["group_mean_returns"]]
        print("\n分位组平均前瞻收益（%）：Q1→Q5")
        print("      " + "  ".join(f"{x:+.3f}" for x in g))
        print(f"      Q5-Q1 = {q['long_short_pct']:+.3f}%")

    v = _verdict(st, subs, q)
    print("\n" + "=" * 88)
    print(f"判定：{v}")
    print("=" * 88)
    print(f"总耗时 {time.time()-t0:.0f}s")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"full": full, "subperiods": subs, "verdict": v,
                       "signs": SIGNS, "args": vars(args)}, fh,
                      ensure_ascii=False, indent=1, default=str)
        print(f"结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
