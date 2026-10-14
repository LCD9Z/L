# -*- coding: utf-8 -*-
"""跨年代因子相关矩阵（H-CD 补充检验）

## 为什么需要

H-CD 判定「4 个因子在 ≥4 窗口方向一致」。但若这 4 个因子彼此高度相关，
那「4 个因子一致」可能只是「**1 个共同因子**（小市值/高波动）一致」——
判定会**高估独立性**。

项目已测（v2 数据集）：amihud↔loga = −0.89、maxret↔vol = +0.85，
但**没有 ret20 与其他的相关**，也没跨年代看。

本脚本补：**每个窗口的 5×5 横截面秩相关矩阵**
（按调仓日分组，逐期计算后取平均 —— 这才是横截面相关，不是 pooled）。

## 口径

- 与 `run_tdx_universe_ic.py` 完全一致：step=5、截面秩相关、
  复用同一个 `_factors_at`（保证因子值一致）、`liq_min=None`
- 样本量 2000（与主实验一致）
- **一次读入，6 个窗口复用**；按日期分组以避免 pooled 偏误

## 未做的部分（如实声明）

**正交化后的符号一致性检验未做**：它需要「因子对 loga20 取残差后的 IC」，
而 IC 需要前瞻收益 —— 那要重跑一遍完整的 IC 管线（每个窗口 15 分钟）。
本脚本只产出**相关矩阵**（描述性），正交化检验列为待办（需专门实验）。

用法：
    python scripts/factor_corr_by_window.py --out reports/cross_decade/CORR.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FACTORS = ["ret20", "vol20", "amihud20", "loga20", "maxret20"]
WINDOWS = [("W1", "20030101", "20071231"), ("W2", "20080101", "20121231"),
           ("W3", "20130101", "20171231"), ("W4", "20180101", "20221231"),
           ("W5", "20230101", "20260930"), ("R", "20210802", "20260930")]
PAIRS = [(FACTORS[i], FACTORS[j])
         for i in range(len(FACTORS)) for j in range(i + 1, len(FACTORS))]

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "ic_mod", os.path.join(_here, "scripts", "run_tdx_universe_ic.py"))
assert _spec is not None and _spec.loader is not None
ic_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic_mod)


def _rank(v: List[float]) -> List[float]:
    order = sorted(range(len(v)), key=lambda k: v[k])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _spearman(x: List[float], y: List[float]) -> Optional[float]:
    """秩相关（并列取平均秩）。n < 30 返回 None（横截面太小的期不要）。"""
    n = len(x)
    if n < 30:
        return None
    rx, ry = _rank(x), _rank(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    return sxy / math.sqrt(sxx * syy)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--events-cache", default="data/gbbq_events.csv")
    ap.add_argument("--max-stocks", type=int, default=2000)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--min-cross-section", type=int, default=200)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    t0 = time.time()

    from tdx_native import adjust, day_reader, gbbq_reader

    events = (gbbq_reader.load_events(args.events_cache)
              if args.events_cache else {})
    stocks = day_reader.scan_paths(args.vipdoc)
    if args.max_stocks and len(stocks) > args.max_stocks:
        stp = len(stocks) / args.max_stocks
        stocks = [stocks[int(i * stp)] for i in range(args.max_stocks)]
    cal = day_reader.read_day_all(
        os.path.join(args.vipdoc, "sh", "lday", "sh000001.day"))
    master = [b["date"] for b in cal]

    # 每窗口的调仓日集合（用于快速判断某日是否属于某窗口）
    win_days: Dict[str, set] = {}
    for tag, s, e in WINDOWS:
        win_days[tag] = {d for i, d in enumerate(master)
                         if i % args.step == 0 and s <= d <= e}
        print(f"  {tag}: {len(win_days[tag])} 个调仓日", flush=True)

    # buckets[tag][date] = {factor: [值...]}
    buckets: Dict[str, Dict[str, Dict[str, List[float]]]] = {
        t: {} for t, _s, _e in WINDOWS}

    print(f"[1/3] 逐股计算因子（{len(stocks)} 只）...", flush=True)
    bad: List[str] = []
    for n, (code, _m, path) in enumerate(stocks, 1):
        if n % 500 == 0:
            print(f"      {n}/{len(stocks)}  ({time.time()-t0:.0f}s)", flush=True)
        try:
            bars = day_reader.read_day_all(path)
        except Exception:                            # noqa: BLE001
            bad.append(code)
            continue
        if len(bars) < 40:
            continue
        ev = events.get(code) or []
        adj_bars = adjust.apply_qfq(bars, ev) if ev else bars
        didx = {b["date"]: k for k, b in enumerate(bars)}
        closes_a = [b["close"] for b in adj_bars]
        amounts = [b["amount"] for b in bars]
        for tag, _s, _e in WINDOWS:
            for d in win_days[tag]:
                i = didx.get(d)
                if i is None or i < 21:
                    continue
                f = ic_mod._factors_at(closes_a, amounts, i, liq_min=None)
                if f is None:
                    continue
                slot = buckets[tag].setdefault(d, {k: [] for k in FACTORS})
                for k in FACTORS:
                    slot[k].append(f[k])

    print("[2/3] 逐窗口逐期计算横截面秩相关 ...", flush=True)
    out: Dict = {"windows": {}, "pairs": [f"{a}|{b}" for a, b in PAIRS],
                 "method": "逐调仓日横截面 Spearman，再取平均（非 pooled）",
                 "max_stocks": args.max_stocks,
                 "bad_files_n": len(bad)}
    for tag, _s, _e in WINDOWS:
        per_pair: Dict[str, List[float]] = {f"{a}|{b}": [] for a, b in PAIRS}
        n_cs = 0
        for _d, cols in buckets[tag].items():
            if len(cols[FACTORS[0]]) < args.min_cross_section:
                continue
            n_cs += 1
            for a, b in PAIRS:
                c = _spearman(cols[a], cols[b])
                if c is not None:
                    per_pair[f"{a}|{b}"].append(c)
        if n_cs == 0:
            print(f"  {tag}: 0 个合格截面，跳过", flush=True)
            continue
        mat = {k: (round(sum(v) / len(v), 4) if v else None)
               for k, v in per_pair.items()}
        out["windows"][tag] = {"corr": mat, "cross_sections": n_cs}
        print(f"  {tag}: {n_cs} 个截面", flush=True)

    # 跨窗口平均
    print("\n[3/3] 各窗口 5×5 横截面秩相关矩阵：")
    for tag in out["windows"]:
        mat = out["windows"][tag]["corr"]
        print(f"\n  === {tag}（{out['windows'][tag]['cross_sections']} 截面）===")
        print("  " + "".join(f"{f[:7]:>10}" for f in FACTORS))
        for a in FACTORS:
            row = f"  {a[:7]:<8}"
            for b in FACTORS:
                if a == b:
                    row += f"{1.0:>10.4f}"
                else:
                    key = f"{a}|{b}" if (a, b) in PAIRS else f"{b}|{a}"
                    v = mat.get(key)
                    row += f"{v:>10.4f}" if v is not None else f"{'n/a':>10}"
            print(row)

    # 判定相关：4 个"一致"因子之间的相关
    print("\n  === 「4 个方向一致」因子之间的相关（跨窗口平均）===")
    consistent = ["ret20", "vol20", "loga20", "maxret20"]
    print("  " + "".join(f"{f[:7]:>10}" for f in consistent))
    avg_mat = {}
    for a, b in PAIRS:
        vs = [out["windows"][t]["corr"].get(f"{a}|{b}")
              for t in out["windows"]]
        vs = [v for v in vs if v is not None]
        avg_mat[(a, b)] = round(sum(vs) / len(vs), 4) if vs else None
    for a in consistent:
        row = f"  {a[:7]:<8}"
        for b in consistent:
            if a == b:
                row += f"{1.0:>10.4f}"
            else:
                key = (a, b) if (a, b) in avg_mat else (b, a)
                v = avg_mat.get(key)
                row += f"{v:>10.4f}" if v is not None else f"{'n/a':>10}"
        print(row)

    if args.out:
        out["avg_corr_pairs"] = {f"{a}|{b}": v for (a, b), v in avg_mat.items()}
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print(f"\n已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
