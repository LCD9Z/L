# -*- coding: utf-8 -*-
"""幸存者偏差对因子研究的影响：把退市股并入数据集，对比因子 IC。

## 假设

退市股是**极端的"输家"**（长期负动量），而 `ret_20` 是**负 IC**
—— 即"过去跌得多的未来涨得多"，其 Q1（最大输家）是买入候选。

**因此：纳入退市股后 Q1 表现应变差 → 反转效应（|IC|）应减弱。**

## 设计

同一套因子、同一调仓规则，只改一件事：**是否包含退市股**。

- **基线**：仅存续股票（TDX 数据集现状）
- **修正**：并入 180 只窗口内退市股的日线

## 数据口径限制（必须知悉）

腾讯/新浪 K 线**不含成交额**。本脚本以 `volume × close` 近似，
因此 **`amihud_20` 与 `log_amount_20` 两个因子在"修正"组不可信**，
对比时应只看不依赖成交额的因子（`ret_*` / `vol_20` / `max_ret_20` /
`dist_high_20` / `price`）。

用法::

    python scripts/run_survivorship_study.py --dataset D:/tdx_dataset
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.factor_ic_lab import (  # noqa: E402
    FACTOR_LABELS,
    quintile_returns,
    run_ic_study,
)

#: K 线行格式：``[date, open, close, high, low, volume]``
_I_DATE, _I_OPEN, _I_CLOSE, _I_HIGH, _I_LOW, _I_VOL = 0, 1, 2, 3, 4, 5

#: 不依赖成交额的因子 —— 修正组与基线组可比
AMOUNT_FREE = ("ret_1", "ret_5", "ret_20", "vol_20", "max_ret_20",
               "dist_high_20", "price")


def klines_to_bars(rows: List[List[Any]]) -> List[Dict[str, Any]]:
    """把 K 线行转成因子引擎消费的 bar 字典。

    成交额用 ``volume × close`` 近似（源数据不含成交额）。
    """
    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            d = str(r[_I_DATE])
            o, c = float(r[_I_OPEN]), float(r[_I_CLOSE])
            h, low = float(r[_I_HIGH]), float(r[_I_LOW])
            v = float(r[_I_VOL])
        except (IndexError, TypeError, ValueError):
            continue
        if c <= 0 or h < low:
            continue
        out.append({"date": d, "open": o, "high": h, "low": low, "close": c,
                    "volume": v, "amount": v * c})
    out.sort(key=lambda b: b["date"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="幸存者偏差对因子研究的影响")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    print("=" * 100)
    print("幸存者偏差对因子研究的影响 · 基线（仅存续） vs 修正（含退市股）")
    print("=" * 100)
    t0 = time.time()

    from real_alpha_pipeline import load_certified_csv
    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if args.max_stocks > 0 and len(codes) > args.max_stocks:
        step = len(codes) / args.max_stocks
        codes = [codes[int(i * step)] for i in range(args.max_stocks)]

    print("\n[1/3] 加载存续股票 ...")
    base: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p, m = os.path.join(stock_dir, f"{c}.csv"), os.path.join(stock_dir, f"{c}.metadata.json")
        if os.path.exists(p) and os.path.exists(m):
            base[c] = load_certified_csv(p, m)
    print(f"      存续股票 {len(base):,} 只")

    print("\n[2/3] 并入退市股 ...")
    kpath = os.path.join(dataset, "delisted_klines.json")
    if not os.path.exists(kpath):
        print(f"      !! 缺少 {kpath}")
        return 2
    with open(kpath, encoding="utf-8") as f:
        raw: Dict[str, List[List[Any]]] = json.load(f)
    merged = dict(base)
    added = 0
    for code, rows in raw.items():
        if not rows:
            continue
        # 退市股代码形如 sh600070 -> 统一为 6 位数字键，避免与存续股冲突
        key = code[2:]
        if key in merged:
            continue
        bars = klines_to_bars(rows)
        if len(bars) >= 30:
            merged[key] = bars
            added += 1
    print(f"      并入 {added} 只退市股（有日线且历史 ≥30 根）")
    print(f"      修正组合计 {len(merged):,} 只")

    print("\n[3/3] 因子 IC 检验 ...")
    print("      基线组 ...")
    base_res = run_ic_study(base, horizon=args.horizon, step=args.step)
    print(f"        调仓期数 {base_res['n_rebalance_dates']}，"
          f"平均截面 {base_res['avg_cross_section']:.0f}  ({time.time()-t0:.0f}s)")
    print("      修正组 ...")
    fix_res = run_ic_study(merged, horizon=args.horizon, step=args.step)
    print(f"        调仓期数 {fix_res['n_rebalance_dates']}，"
          f"平均截面 {fix_res['avg_cross_section']:.0f}  ({time.time()-t0:.0f}s)")

    print("\n" + "=" * 100)
    print("对比：基线（仅存续） vs 修正（含退市股）")
    print("=" * 100)
    print(f"{'因子':18s} {'基线 IC':>10s} {'基线 t':>8s} {'修正 IC':>10s} {'修正 t':>8s} "
          f"{'IC 变化':>10s} {'|IC|变化':>10s}  可比")
    print("-" * 100)
    comp: Dict[str, Any] = {}
    for k in FACTOR_LABELS:
        b = base_res["factors"].get(k, {})
        f_ = fix_res["factors"].get(k, {})
        if "error" in b or "error" in f_:
            continue
        d = f_["ic_mean"] - b["ic_mean"]
        dabs = abs(f_["ic_mean"]) - abs(b["ic_mean"])
        note = "是" if k in AMOUNT_FREE else "否(缺成交额)"
        comp[k] = {"base_ic": b["ic_mean"], "base_t": b["t"],
                   "fix_ic": f_["ic_mean"], "fix_t": f_["t"],
                   "ic_delta": d, "abs_ic_delta": dabs,
                   "comparable": k in AMOUNT_FREE}
        print(f"{k:18s} {b['ic_mean']:>+10.4f} {b['t']:>8.2f} "
              f"{f_['ic_mean']:>+10.4f} {f_['t']:>8.2f} {d:>+10.4f} {dabs:>+10.4f}  {note}")

    print("\n" + "-" * 100)
    print("关键检验：反转类因子的 |IC| 是否减弱？（只看可比因子）")
    print("-" * 100)
    rev = ["ret_1", "ret_5", "ret_20"]
    for k in rev:
        entry = comp.get(k)
        if not entry:
            continue
        arrow = "减弱" if entry["abs_ic_delta"] < 0 else "增强"
        print(f"  {k:10s} |IC| {abs(entry['base_ic']):.4f} -> "
              f"{abs(entry['fix_ic']):.4f}  ({arrow} {abs(entry['abs_ic_delta']):.4f})")
    weaken = [k for k in rev if comp.get(k, {}).get("abs_ic_delta", 0) < 0]
    print()
    if len(weaken) == len(rev):
        print("  结论：三个反转因子 |IC| 全部减弱 -> 支持「退市股放大反转效应」的假设")
    elif len(weaken) > len(rev) / 2:
        print(f"  结论：{len(weaken)}/{len(rev)} 个反转因子减弱 -> 方向支持假设，但不完全")
    else:
        print("  结论：假设未获支持")

    print("\n" + "-" * 100)
    print("分位组对比（ret_20；Q1=最输家，Q5=最赢家；单位 %）")
    print("-" * 100)
    for label, dat in (("基线", base), ("修正", merged)):
        q = quintile_returns(dat, "ret_20", horizon=args.horizon, step=args.step)
        if q:
            g = [x * 100 for x in q["group_mean_returns"]]
            print(f"  {label:6s} Q1 {g[0]:>+7.3f}  Q2 {g[1]:>+7.3f}  Q3 {g[2]:>+7.3f}  "
                  f"Q4 {g[3]:>+7.3f}  Q5 {g[4]:>+7.3f}   Q5-Q1 {q['long_short_pct']:>+7.3f}")

    print()
    print("声明：本检验未调参数，只改「是否包含退市股」。")
    print("      退市股日线来自腾讯/新浪（第三方，需核实）；成交额为近似值。")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"comparison": comp, "added_stocks": added,
                       "base_factors": base_res["factors"],
                       "fixed_factors": fix_res["factors"],
                       "amount_free": list(AMOUNT_FREE), "args": vars(args)},
                      fh, ensure_ascii=False, indent=1, default=str)
        print(f"\n结果已写入: {args.out}")
    print(f"总耗时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
