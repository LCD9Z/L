# -*- coding: utf-8 -*-
"""H-XSRC：跨源验证 —— 在独立源（腾讯）上重算因子 IC，对比主干符号。

## 回答什么

**四个因子的 IC 方向，在独立数据源上是否一致？**
（详见 `XSOURCE_VALIDATION_PREREG.md`）

- 方向一致 → 结论**不依赖数据源**（可信度大幅提升）
- 方向翻转 → ⚠️ **20 项实验、65 个文档全部要重新审视**

## 口径（与主干严格一致）

- **因子定义**：**直接复用** `run_tdx_universe_ic._factors_at`
  （该函数与生产 `five_factor.compute_factors` 逐字一致）
- **IC 口径**：`step=5`、`horizon=5`、截面 Spearman、`min_cross_section=200`
- **窗口**：与 H-CD 相同的 W1~W5 + R
- **复权**：腾讯 `qfq`（前复权）—— 与主干一致
- **流动性门槛**：**不过滤**（H-CD 已证明门槛会干预 amihud/loga20）

## ⚠️ amount 是估算值

腾讯不返回成交额。本脚本用 `volume(股) × (H+L+C)/3` 估算
（与 `fetch_delisted_full.py` 一致）。**该字段是 amihud20 / loga20 的定义变量**，
故这两个因子的结论应视为**较弱证据**（在报告中标注）。

用法::

    python scripts/run_xsrc_ic.py --src D:/xs_tencent/klines \\
        --out reports/xsource/XSRC.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import json
import math
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FACTORS = ["ret20", "vol20", "amihud20", "loga20", "maxret20"]
DIRECTIONS = {"ret20": -1, "vol20": -1, "amihud20": 1, "loga20": -1,
              "maxret20": -1}
WINDOWS = [("W1", "20030101", "20071231"), ("W2", "20080101", "20121231"),
           ("W3", "20130101", "20171231"), ("W4", "20180101", "20221231"),
           ("W5", "20230101", "20260930"), ("R", "20210802", "20260930")]

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "ic_mod", os.path.join(_here, "scripts", "run_tdx_universe_ic.py"))
ic_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic_mod)


# --------------------------------------------------------------------------
# 统计工具（与 run_factor_orthogonality.py 同源，保持全项目零 numpy）
# --------------------------------------------------------------------------


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


def _pearson(x: List[float], y: List[float]) -> Optional[float]:
    n = len(x)
    if n < 10:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / math.sqrt(sxx * syy)


def _spearman(x: List[float], y: List[float]) -> Optional[float]:
    if len(x) < 10:
        return None
    return _pearson(_rank(x), _rank(y))


def _stat(v: List[float]) -> Dict:
    if len(v) < 2:
        return {"ic_mean": None, "t": None, "n": len(v)}
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
    t = m / (sd / math.sqrt(len(v))) if sd > 0 else 0.0
    return {"ic_mean": round(m, 6), "t": round(t, 2), "n": len(v)}


def load_series(path: str) -> Optional[Dict]:
    """读腾讯 CSV → 升序 date/closes/amounts。"""
    try:
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return None
    dates, closes, amounts = [], [], []
    for r in rows:
        try:
            d = str(r["date"]).replace("-", "").strip()
            c = float(r["close"])
            a = float(r.get("amount") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        if not d or c <= 0:
            continue
        if a <= 0:                                    # 估算 amount（与拉取端一致）
            try:
                h, lo = float(r["high"]), float(r["low"])
                v = float(r.get("volume") or 0)
                a = v * (h + lo + c) / 3.0
            except (ValueError, TypeError):
                continue
        dates.append(d)
        closes.append(c)
        amounts.append(a)
    if len(dates) < 40:
        return None
    order = sorted(range(len(dates)), key=lambda k: dates[k])
    return {"dates": [dates[k] for k in order],
            "closes": [closes[k] for k in order],
            "amounts": [amounts[k] for k in order]}


def main() -> int:
    ap = argparse.ArgumentParser(description="H-XSRC 跨源 IC 计算")
    ap.add_argument("--src", required=True, help="腾讯 CSV 目录")
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--min-cross-section", type=int, default=200)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.src, "*.csv")))
    if not files:
        print(f"{args.src} 下无 CSV")
        return 2
    print(f"[1/3] 载入 {len(files)} 只 ...", flush=True)

    series: Dict[str, Dict] = {}
    for f in files:
        s = load_series(f)
        if s:
            series[os.path.basename(f)[:-4]] = s
    print(f"      有效 {len(series)} 只", flush=True)

    # 逐日收集横截面
    buckets: Dict[str, Dict[str, Dict]] = {t: {} for t, _s, _e in WINDOWS}
    for s in series.values():
        dates, closes, amounts = s["dates"], s["closes"], s["amounts"]
        for tag, ws, we in WINDOWS:
            for i in range(0, len(dates), args.step):
                d = dates[i]
                if not (ws <= d <= we):
                    continue
                if i < 21 or i + args.horizon >= len(dates):
                    continue
                f = ic_mod._factors_at(closes, amounts, i, liq_min=None)
                if f is None:
                    continue
                c0, c1 = closes[i], closes[i + args.horizon]
                if c0 <= 0:
                    continue
                slot = buckets[tag].setdefault(
                    d, {"f": {k: [] for k in FACTORS}, "y": []})
                for k in FACTORS:
                    slot["f"][k].append(f[k])
                slot["y"].append(c1 / c0 - 1)

    print("[2/3] 逐期算 IC ...", flush=True)
    out: Dict = {"windows": {}, "n_stocks": len(series),
                 "amount_is_estimated": True,
                 "note": "amount 为 volume×(H+L+C)/3 估算值；"
                         "amihud20/loga20 结论应视为较弱证据"}
    for tag, _s, _e in WINDOWS:
        got = dict.fromkeys(FACTORS, [])
        n_cs = 0
        for _d, slot in buckets[tag].items():
            y = slot["y"]
            if len(y) < args.min_cross_section:
                continue
            n_cs += 1
            for k in FACTORS:
                ic = _spearman(slot["f"][k], y)
                if ic is not None:
                    got[k].append(ic)
        if not n_cs:
            continue
        out["windows"][tag] = {"cross_sections": n_cs,
                               "ic": {k: _stat(got[k]) for k in FACTORS}}

    print("[3/3] 对比主干符号 ...")
    mv_path = os.path.join(_here, "reports", "cross_decade", "VERDICT.json")
    out["main_verdict_ref"] = os.path.relpath(mv_path, _here) \
        if os.path.exists(mv_path) else "(不存在)"

    print(f"\n  {'因子':<10}{'冻结':>5}", end="")
    for tag, _s, _e in WINDOWS:
        print(f"{tag:>18}", end="")
    print()
    reg = ["W1", "W2", "W3", "W4", "W5"]
    consistent: Dict[str, int] = dict.fromkeys(FACTORS, 0)
    for k in FACTORS:
        print(f"  {k:<10}{DIRECTIONS[k]:>+5}", end="")
        for tag, _s, _e in WINDOWS:
            w = out["windows"].get(tag)
            if not w:
                print(f"{'—':>18}", end="")
                continue
            v = w["ic"][k]
            if v["ic_mean"] is None:
                print(f"{'n/a':>18}", end="")
                continue
            ok = (v["ic_mean"] > 0) == (DIRECTIONS[k] > 0)
            if ok and tag in reg:
                consistent[k] += 1
            print(f"{v['ic_mean']:+.4f}/{v['t']:+.2f}{'✓' if ok else '✗':>3}",
                  end="")
        print()
    out["consistent_windows"] = consistent

    n_ok = sum(1 for k in FACTORS if consistent[k] >= 4)
    out["verdict"] = {
        "factors_consistent_ge4": n_ok,
        "conclusion": ("跨源一致" if n_ok >= 4
                       else "部分一致" if n_ok == 3
                       else "⚠️ 整体存疑（须上报，启动全项目复审）")}
    print(f"\n  → 方向一致（≥4 窗口）的因子：{n_ok}/5 → "
          f"{out['verdict']['conclusion']}")

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print(f"已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
