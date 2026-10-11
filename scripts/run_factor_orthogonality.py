# -*- coding: utf-8 -*-
"""因子正交化后的方向稳健性（H-ORTH）

按 `FACTOR_ORTHOGONALITY_PREREG.md` 执行。回答：
**剔除共同成分后，还剩哪些因子是独立稳健的？**

## 设计（预注册 §二，全事前固定）

对每个调仓日的横截面：
1. 取秩（Spearman 口径，与主实验一致）
2. 一元线性回归取残差
3. `IC_orth = Spearman(resid, forward_return)`

**两种正交化基准并列全报**（预注册 §二.1，禁止择一）：
- **O1**：对 `loga20` 取残差（外生代理：规模/流动性）
- **O2**：对 **PC1** 取残差（内生：由 5 因子相关矩阵第一主成分决定）

**不过滤流动性**（预注册 §四）：H-CD 已证明门槛会干预因子
（`loga20`/`amihud20` 的定义变量就是成交额），再按成交额筛会重蹈覆辙。

## 口径

`step=5`、`horizon=5`、无重叠、`max_stocks=2000`、`min_cross_section=200`、
前瞻用**前复权价**、因子用**前复权价**、复用 `_factors_at` 保证因子值一致。

用法：
    python scripts/run_factor_orthogonality.py --out reports/cross_decade/ORTH.json
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


# ---------------------------------------------------------------------------
# 统计工具（纯 Python，不引 numpy —— 本项目其余脚本同样零 numpy）
# ---------------------------------------------------------------------------


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
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    return sxy / math.sqrt(sxx * syy)


def _spearman(x: List[float], y: List[float]) -> Optional[float]:
    if len(x) < 10:
        return None
    return _pearson(_rank(x), _rank(y))


def _resid(ry: List[float], rx: List[float]) -> List[float]:
    """ry 对 rx 的一元线性回归残差（两者都已取秩）。"""
    n = len(ry)
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((a - mx) ** 2 for a in rx)
    if sxx <= 0:
        return [0.0] * n
    sxy = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    beta = sxy / sxx
    return [ry[i] - (my + beta * (rx[i] - mx)) for i in range(n)]


def _first_pc(cols: Dict[str, List[float]]) -> Optional[List[float]]:
    """5 因子相关矩阵的第一主成分得分（幂迭代，20 次）。

    返回各样本在 PC1 上的投影（已标准化）。列先取秩再标准化。
    """
    n = len(cols[FACTORS[0]])
    if n < 30:
        return None
    # 秩标准化
    Z: Dict[str, List[float]] = {}
    for f in FACTORS:
        r = _rank(cols[f])
        m = sum(r) / n
        sd = math.sqrt(sum((a - m) ** 2 for a in r) / n)
        Z[f] = [(a - m) / sd for a in r] if sd > 0 else [0.0] * n
    # 相关矩阵（5×5）
    p = len(FACTORS)
    C = [[0.0] * p for _ in range(p)]
    for a in range(p):
        for b in range(a, p):
            c = sum(Z[FACTORS[a]][i] * Z[FACTORS[b]][i] for i in range(n)) / n
            C[a][b] = C[b][a] = c
    # 幂迭代
    v = [1.0 / math.sqrt(p)] * p
    for _ in range(20):
        w = [sum(C[a][b] * v[b] for b in range(p)) for a in range(p)]
        nw = math.sqrt(sum(x * x for x in w))
        if nw <= 0:
            return None
        v = [x / nw for x in w]
    # 投影
    return [sum(v[a] * Z[FACTORS[a]][i] for a in range(p)) for i in range(n)]


def _stat(v: List[float]) -> Dict:
    if len(v) < 2:
        return {"ic_mean": None, "t": None, "n": len(v)}
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
    t = m / (sd / math.sqrt(len(v))) if sd > 0 else 0.0
    return {"ic_mean": round(m, 6), "t": round(t, 2), "n": len(v)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--events-cache", default="data/gbbq_events.csv")
    ap.add_argument("--max-stocks", type=int, default=2000)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--min-cross-section", type=int, default=200)
    ap.add_argument("--windows", default="",
                    help="逗号分隔的窗口子集（如 W5）；空=全部 6 个")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    t0 = time.time()
    if args.windows:
        want = {x.strip() for x in args.windows.split(",") if x.strip()}
        global WINDOWS
        WINDOWS = [w for w in WINDOWS if w[0] in want]
        if not WINDOWS:
            raise SystemExit("--windows 未匹配到任何窗口")

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

    win_days: Dict[str, set] = {}
    for tag, s, e in WINDOWS:
        win_days[tag] = {d for i, d in enumerate(master)
                         if i % args.step == 0 and s <= d <= e}

    # buckets[tag][date] = {"f": {factor: [...]}, "y": [前瞻收益], "fwd_end": [...]}
    buckets: Dict[str, Dict[str, Dict]] = {t: {} for t, _s, _e in WINDOWS}

    print(f"[1/3] 逐股计算因子与前瞻（{len(stocks)} 只）...", flush=True)
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
                if i is None or i < 21 or i + args.horizon >= len(bars):
                    continue
                f = ic_mod._factors_at(closes_a, amounts, i, liq_min=None)
                if f is None:
                    continue
                c0, c1 = closes_a[i], closes_a[i + args.horizon]
                if c0 <= 0:
                    continue
                slot = buckets[tag].setdefault(d, {"f": {k: [] for k in FACTORS},
                                                   "y": []})
                for k in FACTORS:
                    slot["f"][k].append(f[k])
                slot["y"].append(c1 / c0 - 1)

    print("[2/3] 逐期计算三列 IC（未正交化 / O1@loga20 / O2@PC1）...",
          flush=True)
    series: Dict[str, Dict[str, Dict[str, List[float]]]] = {
        t: {"plain": {f: [] for f in FACTORS},
            "o1": {f: [] for f in FACTORS},
            "o2": {f: [] for f in FACTORS}} for t, _s, _e in WINDOWS}
    pc1_var: Dict[str, List[float]] = {t: [] for t, _s, _e in WINDOWS}
    n_cs: Dict[str, int] = {}

    for tag, _s, _e in WINDOWS:
        for _d, slot in buckets[tag].items():
            y = slot["y"]
            if len(y) < args.min_cross_section:
                continue
            cols = slot["f"]
            ry = _rank(y)
            n_cs[tag] = n_cs.get(tag, 0) + 1
            # 未正交化
            for f in FACTORS:
                ic = _spearman(cols[f], y)
                if ic is not None:
                    series[tag]["plain"][f].append(ic)
            # O1：对 loga20 取残差
            r_s = _rank(cols["loga20"])
            for f in FACTORS:
                if f == "loga20":
                    continue
                res = _resid(_rank(cols[f]), r_s)
                ic = _pearson(res, ry)
                if ic is not None:
                    series[tag]["o1"][f].append(ic)
            # O2：对 PC1 取残差
            pc = _first_pc(cols)
            if pc is not None:
                r_pc = _rank(pc)
                # PC1 的方差解释率（用相关矩阵最大特征值 / p 近似：由投影方差估计）
                var_pc = sum(x * x for x in pc) / len(pc)
                pc1_var[tag].append(var_pc / len(FACTORS))
                for f in FACTORS:
                    res = _resid(_rank(cols[f]), r_pc)
                    ic = _pearson(res, ry)
                    if ic is not None:
                        series[tag]["o2"][f].append(ic)

    out: Dict = {"windows": {}, "bad_files_n": len(bad),
                 "max_stocks": args.max_stocks,
                 "method": "逐调仓日横截面；残差用秩回归；IC 与前瞻收益的秩相关",
                 "horizon": args.horizon, "step": args.step}
    for tag, _s, _e in WINDOWS:
        if not n_cs.get(tag):
            continue
        out["windows"][tag] = {
            "cross_sections": n_cs[tag],
            "pc1_var_share_est": (round(sum(pc1_var[tag]) / len(pc1_var[tag]), 4)
                                  if pc1_var[tag] else None),
            "plain": {f: _stat(series[tag]["plain"][f]) for f in FACTORS},
            "o1_vs_loga": {f: _stat(series[tag]["o1"][f]) for f in FACTORS},
            "o2_vs_pc1": {f: _stat(series[tag]["o2"][f]) for f in FACTORS},
        }

    # ---- 报表 ----
    print("\n[3/3] 各窗口 IC（plain / O1@loga20 / O2@PC1）")
    for tag, _s, _e in WINDOWS:
        w = out["windows"].get(tag)
        if not w:
            print(f"\n  === {tag} 无合格截面，跳过 ===")
            continue
        print(f"\n  === {tag}（{w['cross_sections']} 截面，"
              f"PC1 方差占比≈{w['pc1_var_share_est']}）===")
        print(f"  {'因子':<10}{'冻结':>5}{'plain':>18}{'O1@loga':>18}{'O2@PC1':>18}")
        for f in FACTORS:
            cells = []
            for key in ("plain", "o1_vs_loga", "o2_vs_pc1"):
                v = w[key][f]
                if v["ic_mean"] is None:
                    cells.append(f"{'n/a':>18}")
                else:
                    ok = "✓" if (v["ic_mean"] > 0) == (DIRECTIONS[f] > 0) else "✗"
                    cells.append(f"{v['ic_mean']:+.4f}/{v['t']:+.2f}{ok:>3}")
            print(f"  {f:<10}{DIRECTIONS[f]:>+5}" + "".join(f"{c:>18}" for c in cells))

    # ---- 预注册 §三 判定 ----
    print("\n  === 判定（预注册 §三，只在登记的 W1-W5 上计）===")
    reg = [t for t, _s, _e in WINDOWS if t.startswith("W")]
    verdict = {}
    for f in FACTORS:
        n_p = n_o1 = n_o2 = 0
        for tag in reg:
            w = out["windows"].get(tag)
            if not w:
                continue
            for key in ("plain", "o1_vs_loga", "o2_vs_pc1"):

                v = w[key][f]["ic_mean"]
                if v is None:
                    continue
                if (v > 0) == (DIRECTIONS[f] > 0):
                    if key == "plain":
                        n_p += 1
                    elif key == "o1_vs_loga":
                        n_o1 += 1
                    else:
                        n_o2 += 1
        if n_o1 >= 4 and n_o2 >= 4 and n_p >= 4:
            v = "independent_robust"
        elif n_o1 <= 2 or n_o2 <= 2:
            v = "proxy_factor"
        else:
            v = "INCONCLUSIVE"
        verdict[f] = {"plain_consistent": n_p, "o1_consistent": n_o1,
                      "o2_consistent": n_o2, "verdict": v, "n_windows": len(reg)}
        print(f"  {f:<10} plain {n_p}/{len(reg)} | O1 {n_o1}/{len(reg)} | "
              f"O2 {n_o2}/{len(reg)}  →  {v}")
    out["verdict"] = verdict

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print(f"\n已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
