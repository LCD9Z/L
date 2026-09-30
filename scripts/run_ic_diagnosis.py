# -*- coding: utf-8 -*-
"""IC 虚高诊断（H-ICX，登记见 `IC_DIAGNOSIS_PREREG.md`）。

2×2 设计：
  L0 = close[t+5]/close[t] − 1      （现状：现有 forward_return）
  L1 = close[t+5]/open[t+1] − 1     （可执行：T+1 开盘建仓、t+5 收盘平仓）
  M0 = 无屏蔽
  M1 = 可交易性屏蔽（t+1 涨停买不到 / 持有期跌停卖不掉 / 持有期停牌 / t+1 无行情）

因子计算直接复用 `factors.factor_ic_lab.compute_factors`，与既有结论严格可比。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FACTORS = ["ret_20", "vol_20", "amihud_20", "log_amount_20", "max_ret_20"]


def _limit_pct(code: str, is_st: bool) -> float:
    c = str(code).zfill(6)
    if c.startswith(("83", "87", "43", "92")):
        return 0.30
    if c.startswith(("300", "301", "688", "689")):
        return 0.20
    if is_st:
        return 0.05
    return 0.10


def _load_suspension(path: str) -> Dict[str, List[Tuple[str, str]]]:
    out: Dict[str, List[Tuple[str, str]]] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["code"], []).append((r["start"], r["end"]))
    return out


def _suspended(susp: Dict[str, List[Tuple[str, str]]], code: str,
               d0: str, d1: str) -> bool:
    """[d0, d1] 区间内是否存在停牌段。"""
    for s, e in susp.get(code, ()):  # noqa: E501
        if not (e < d0 or s > d1):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="IC 虚高诊断（L×M 2×2）")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v2")
    ap.add_argument("--max-stocks", type=int, default=800)
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--min-cross-section", type=int, default=50)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    t0 = time.time()

    from real_alpha_pipeline import load_certified_csv
    from factors.factor_ic_lab import compute_factors, spearman, forward_return

    stock_dir = os.path.join(args.dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if args.max_stocks > 0 and len(codes) > args.max_stocks:
        code_step = len(codes) / args.max_stocks
        codes = [codes[int(i * code_step)] for i in range(args.max_stocks)]
    data: Dict[str, List[dict]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if os.path.exists(p) and os.path.exists(m):
            bars = load_certified_csv(p, m)
            if len(bars) >= args.min_rows:
                data[c] = bars
    print(f"[1/3] 载入 {len(data)} 只", flush=True)

    susp = _load_suspension(os.path.join(args.dataset, "suspension_intervals.csv"))
    print(f"      停牌记录覆盖 {len(susp)} 只", flush=True)

    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    all_dates = sorted({str(b["date"]) for bars in data.values() for b in bars})
    signal_dates = set(all_dates)
    rebalance_dates = all_dates[:: args.step]

    combos = ["L0M0", "L0M1", "L1M0", "L1M1"]
    ic_series: Dict[str, Dict[str, List[float]]] = {
        k: {fac: [] for fac in FACTORS} for k in combos}
    masked_cnt = {k: 0 for k in combos}
    total_cnt = {k: 0 for k in combos}
    reasons = {"no_next": 0, "buy_limit": 0, "hold_down": 0, "susp": 0}

    print("[2/3] 逐截面计算 IC ...", flush=True)
    for date in rebalance_dates:
        pairs: Dict[str, Dict[str, List[Tuple[float, float]]]] = {
            k: {fac: [] for fac in FACTORS} for k in combos}
        for c, bars in data.items():
            i = idx_map[c].get(date)
            if i is None or i < 22 or i + args.horizon >= len(bars):
                continue
            f = compute_factors(bars, i)
            if not f:
                continue
            fwd0 = forward_return(bars, i, args.horizon)          # close -> close
            eb, xb = bars[i + 1], bars[i + args.horizon]
            o1 = float(eb["open"] or 0)
            x5 = float(xb["close"] or 0)
            fwd1 = (x5 / o1 - 1) if o1 > 0 and x5 > 0 else None   # open[t+1] -> close[t+5]

            # --- M1 可交易性屏蔽 ---
            is_st = str(bars[i].get("is_st", "0")) == "1"
            lim = _limit_pct(c, is_st) - 0.002
            pos = all_dates.index(date) if date in signal_dates else -1
            next_day_ok = (pos >= 0 and pos + 1 < len(all_dates)
                           and str(eb["date"]) == all_dates[pos + 1])
            # t+1 涨停（买不到）
            r1 = None
            pc0 = float(bars[i]["close"] or 0)
            if pc0 > 0:
                r1 = float(eb["close"]) / pc0 - 1
            buy_blocked = next_day_ok and r1 is not None and r1 >= lim
            # 持有期内跌停（卖不掉）
            hold_down = False
            for k in range(i + 2, i + args.horizon + 1):
                if k >= len(bars):
                    break
                pc = float(bars[k - 1]["close"] or 0)
                if pc > 0 and (float(bars[k]["close"]) / pc - 1) <= -lim:
                    hold_down = True
                    break
            susp_in_hold = _suspended(susp, c, date, str(xb["date"]))
            masked = (not next_day_ok) or buy_blocked or hold_down or susp_in_hold
            if masked:
                reasons["no_next"] += int(not next_day_ok)
                reasons["buy_limit"] += int(buy_blocked)
                reasons["hold_down"] += int(hold_down)
                reasons["susp"] += int(susp_in_hold)

            for combo in combos:
                use_l1 = combo[1] == "1"      # "L{x}M{y}" → 索引 1 是 L
                use_mask = combo[3] == "1"    # 索引 3 是 M
                if use_mask and masked:
                    masked_cnt[combo] += 1
                    continue
                y = fwd1 if use_l1 else fwd0
                if y is None:
                    continue
                total_cnt[combo] += 1
                for fac in FACTORS:
                    pairs[combo][fac].append((f[fac], y))
        for combo in combos:
            for fac in FACTORS:
                pr = pairs[combo][fac]
                if len(pr) < args.min_cross_section:
                    continue
                ic = spearman([x for x, _ in pr], [y for _, y in pr])
                if ic is not None:
                    ic_series[combo][fac].append(ic)

    print("[3/3] 汇总 ...", flush=True)

    def stat(v: List[float]) -> Dict[str, Any]:
        n = len(v)
        if n < 2:
            return {"ic_mean": None, "t": None, "n_periods": n}
        m = sum(v) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
        t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
        return {"ic_mean": round(m, 6), "ic_std": round(sd, 6),
                "t": round(t, 2), "n_periods": n}

    res: Dict[str, Any] = {c: {fac: stat(ic_series[c][fac]) for fac in FACTORS}
                           for c in combos}
    base = {fac: abs(res["L0M0"][fac]["ic_mean"] or 0) for fac in FACTORS}
    final = {fac: abs(res["L1M1"][fac]["ic_mean"] or 0) for fac in FACTORS}
    decay = {fac: (1 - final[fac] / base[fac]) if base[fac] else None for fac in FACTORS}
    dvals = sorted(v for v in decay.values() if v is not None)
    median_decay = dvals[len(dvals) // 2] if dvals else None
    t_break = sum(1 for fac in FACTORS
                  if (res["L1M1"][fac]["t"] is not None and abs(res["L1M1"][fac]["t"]) < 2))

    if median_decay is None:
        verdict = "无法判定"
    elif median_decay >= 0.30 or t_break >= 3:
        verdict = "IC 虚高成立"
    elif median_decay >= 0.15:
        verdict = "部分成立"
    else:
        verdict = "IC 虚高不成立（IC 稳健）"

    out = {
        "dataset": args.dataset, "stocks": len(data),
        "horizon": args.horizon, "step": args.step,
        "ic": res,
        "abs_ic_decay_L1M1_vs_L0M0": {k: (round(v, 4) if v is not None else None)
                                      for k, v in decay.items()},
        "median_decay": round(median_decay, 4) if median_decay is not None else None,
        "factors_t_below_2_in_L1M1": t_break,
        "sample_counts": {c: {"used": total_cnt[c], "masked": masked_cnt[c]}
                          for c in combos},
        "mask_share": {c: round(masked_cnt[c] / max(1, masked_cnt[c] + total_cnt[c]), 4)
                       for c in combos},
        "mask_reasons": reasons,
        "verdict": verdict,
        "runtime_sec": round(time.time() - t0, 1),
        "note": "公告窗口数据缺失未屏蔽，故测得衰减为下界；L1 = close[t+5]/open[t+1]-1。",
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
