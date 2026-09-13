# -*- coding: utf-8 -*-
"""在 TDX 数据集上检验经济逻辑驱动的因子假设。

用法::

    python run_factor_study.py --dataset D:/tdx_dataset
    python run_factor_study.py --dataset D:/tdx_dataset --max-stocks 1500

## 方法

横截面 Spearman 秩 IC：每 5 个交易日调仓、前瞻 5 个交易日（**无重叠**）。
秩相关只看排序，因此：

1. **对幸存者偏差不敏感** —— 偏差影响收益水平，不影响横截面排序
2. **抗除权跳空** —— 不复权价的离群值不影响秩

## 假设与判定

对每个因子报告 IC 均值、ICIR、t、p。判定标准（事前设定，不事后调整）：

- **支持**：IC 符号与先验一致，且 |t| >= 2
- **方向一致但证据弱**：符号一致，|t| < 2
- **与先验相反**：符号与先验相反
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factor_ic_lab import (  # noqa: E402
    quintile_returns,
    run_ic_study,
)


def _load(dataset: str, max_stocks: int, min_rows: int = 200):
    from real_alpha_pipeline import load_certified_csv
    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    data = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        bars = load_certified_csv(p, m)
        if len(bars) >= min_rows:
            data[c] = bars
    return data


def _verdict(f: Dict[str, Any]) -> str:
    if "error" in f:
        return "证据不足"
    ic, t, prior = f["ic_mean"], f["t"], f["prior_sign"]
    if prior == 0:
        return "方向待定"
    consistent = (ic > 0) if prior > 0 else (ic < 0)
    if not consistent:
        return "**与先验相反**"
    return "支持（强）" if abs(t) >= 2 else "方向一致（弱）"


def _print_table(facs: Dict[str, Any], title: str) -> None:
    print(f"\n{title}")
    print("-" * 104)
    print(f"{'因子':22s} {'IC均值':>9s} {'IC标准差':>9s} {'ICIR':>7s} "
          f"{'t':>7s} {'p':>8s} {'期数':>5s} {'先验':>5s}  判定")
    print("-" * 104)
    order = sorted(facs.items(), key=lambda kv: -abs(kv[1].get("t", 0)))
    for k, f in order:
        if "error" in f:
            print(f"{k:22s} {'—':>9s} {'—':>9s} {'—':>7s} {'—':>7s} "
                  f"{'—':>8s} {f.get('n_periods', 0):>5} {'—':>5s}  {_verdict(f)}")
            continue
        prior = "IC>0" if f["prior_sign"] > 0 else ("IC<0" if f["prior_sign"] < 0 else "—")
        print(f"{k:22s} {f['ic_mean']:>+9.4f} {f['ic_std']:>9.4f} {f['icir']:>7.3f} "
              f"{f['t']:>7.2f} {f['p']:>8.4f} {f['n_periods']:>5} {prior:>5s}  {_verdict(f)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="TDX 数据集上的因子假设检验")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = os.path.abspath(args.dataset)
    print("=" * 104)
    print("横截面因子假设检验 · 经济逻辑驱动（每 5 日调仓 / 前瞻 5 日 / 无重叠）")
    print("=" * 104)

    t0 = time.time()
    print("[1/3] 加载数据 ...")
    data = _load(dataset, args.max_stocks)
    n_rows = sum(len(v) for v in data.values())
    print(f"      股票 {len(data):,} 只，共 {n_rows:,} 行  ({time.time()-t0:.0f}s)")

    print("[2/3] 全样本 IC 检验 ...")
    res = run_ic_study(data, horizon=args.horizon, step=args.step)
    print(f"      调仓期数 {res['n_rebalance_dates']}，"
          f"平均截面 {res['avg_cross_section']:.0f} 只，"
          f"全池平均前瞻收益 {res['mean_universe_forward_return']*100:+.2f}%  "
          f"({time.time()-t0:.0f}s)")
    _print_table(res["factors"], "全样本（2021-08 ~ 2026-09）")

    print("\n[3/3] 分位组检验（Q1=因子最低，Q5=因子最高）...")
    qres = {}
    for k in ["ret_5", "ret_20", "vol_20", "vol_ratio", "max_ret_20",
              "amihud_20", "log_amount_20"]:
        q = quintile_returns(data, k, horizon=args.horizon, step=args.step)
        if q:
            qres[k] = q
    print("-" * 104)
    print(f"{'因子':22s} {'Q1':>9s} {'Q2':>9s} {'Q3':>9s} {'Q4':>9s} {'Q5':>9s} "
          f"{'Q5-Q1':>9s}  单调")
    print("-" * 104)
    for k, q in qres.items():
        g = [x * 100 for x in q["group_mean_returns"]]
        print(f"{k:22s} {g[0]:>+9.3f} {g[1]:>+9.3f} {g[2]:>+9.3f} {g[3]:>+9.3f} "
              f"{g[4]:>+9.3f} {q['long_short_pct']:>+9.3f}  "
              f"{'是' if q['monotonic'] else '否'}")

    # ---- 子期间稳定性 ----
    print("\n子期间稳定性检验 ...")
    sub = {}
    for label, s, e in [("2021-08 ~ 2023-12", "2021-08-01", "2023-12-31"),
                        ("2024-01 ~ 2026-09", "2024-01-01", "2026-09-30")]:
        r = run_ic_study(data, horizon=args.horizon, step=args.step, start=s, end=e)
        sub[label] = r["factors"]
        print(f"\n  【{label}】调仓期数 {r['n_rebalance_dates']}，"
              f"全池平均前瞻收益 {r['mean_universe_forward_return']*100:+.2f}%")
        print(f"    {'因子':22s} {'IC均值':>9s} {'t':>7s}  判定")
        for k in ["ret_5", "ret_20", "vol_20", "vol_ratio", "max_ret_20", "amihud_20"]:
            f = r["factors"].get(k, {})
            if "error" in f:
                print(f"    {k:22s} {'—':>9s} {'—':>7s}  证据不足")
            else:
                print(f"    {k:22s} {f['ic_mean']:>+9.4f} {f['t']:>7.2f}  {_verdict(f)}")

    print(f"\n总耗时 {time.time()-t0:.0f}s")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"full": res, "quintiles": qres, "subperiods": sub,
                       "args": vars(args)}, fh, ensure_ascii=False,
                      indent=1, default=str)
        print(f"结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
