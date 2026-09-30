# -*- coding: utf-8 -*-
"""五因子截面相关性与组合增量检验（v2 数据源，零第三方依赖）。

要回答的问题：单因子 IC 强不等于组合有效。vol_20 / max_ret_20 / log_amount_20
可能属于同一个"低波动/低关注"家族，等权打分=重复计票。

输出三件事：
1. 五因子的**平均截面 Spearman 相关矩阵**（冗余度诊断）
2. 各单因子的前瞻 5 日 IC（与 run_factor_study 同口径：每 5 日调仓、无重叠）
3. **等权组合分的 IC** 与最佳单因子 IC 对比——组合是否带来增量

口径全部事前设定：方向与冻结引擎一致（ret20/vol20/loga20/maxret20 反向，
amihud20 正向）；组合权重等权（1/5）；不做任何权重搜索。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIRECTIONS = {"ret20": -1, "vol20": -1, "amihud20": 1, "loga20": -1, "maxret20": -1}
FACTORS = list(DIRECTIONS)
REBAL = 5
HORIZON = 5

#: 家族配权（方案 B，事前设定）：相关矩阵显示五因子实际只有约 3 个独立信号——
#  流动性族(amihud20,loga20,r=-0.89)、波动族(vol20,maxret20,r=+0.85)、
#  反转族(ret20)。方案 A 等权等于给前两族各投两票；方案 B 按族配权（每族 1/3，
#  族内等权），用于检验「去冗余是否带来增量」。两方案同时报告，不做事后挑选。
FAMILY_WEIGHTS = {
    "amihud20": 1 / 6, "loga20": 1 / 6,     # 流动性族共 1/3
    "vol20": 1 / 6, "maxret20": 1 / 6,      # 波动族共 1/3
    "ret20": 1 / 3,                         # 反转族 1/3
}


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """秩相关（Pearson of ranks），并列用平均秩。"""
    n = len(xs)
    if n < 3:
        return float("nan")
    rx = _ranks(xs)
    ry = _ranks(ys)
    return _pearson(rx, ry)


def _ranks(v: Sequence[float]) -> List[float]:
    n = len(v)
    order = sorted(range(n), key=lambda i: v[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    if da == 0 or db == 0:
        return float("nan")
    return num / (da * db)


def main() -> int:
    ap = argparse.ArgumentParser(description="五因子相关性与组合增量检验")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v2")
    ap.add_argument("--max-stocks", type=int, default=500)
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    t0 = time.time()

    from real_alpha_pipeline import load_certified_csv
    stock_dir = os.path.join(args.dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if args.max_stocks > 0 and len(codes) > args.max_stocks:
        step = len(codes) / args.max_stocks
        codes = [codes[int(i * step)] for i in range(args.max_stocks)]
    data: Dict[str, List[dict]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        bars = load_certified_csv(p, m)
        if len(bars) >= args.min_rows:
            data[c] = bars
    print(f"[1/3] 载入 {len(data)} 只 ...", flush=True)

    # 交易日历 = 全部日期并集
    all_dates = sorted({b["date"] for bars in data.values() for b in bars})
    by_code = {c: {b["date"]: b for b in bars} for c, bars in data.items()}
    print(f"[2/3] 交易日 {len(all_dates)} 天，计算因子 ...", flush=True)

    panels: Dict[str, Dict[str, Dict[str, float]]] = {}   # date -> factor -> {code: value}
    fwd: Dict[str, Dict[str, float]] = {}                 # date -> {code: forward 5d return}
    for k in range(0, len(all_dates) - HORIZON, REBAL):
        d = all_dates[k]
        fwd_d = all_dates[k + HORIZON]
        panel: Dict[str, Dict[str, float]] = {}
        ret_map: Dict[str, float] = {}
        # `bars` 在上一段推导式里是 list，这里若复用同名会让类型推断崩塌
        for c, code_bars in by_code.items():
            b = code_bars.get(d)
            prev = code_bars.get(all_dates[k - 1]) if k > 0 else None
            if b is None:
                continue
            # 分两步：seq 若被重复赋值，mypy 会沿用首次（含 None）的推断
            seq_raw = [code_bars.get(x) for x in all_dates[max(0, k - 21): k + 1]]
            seq = [x for x in seq_raw if x is not None]
            if len(seq) < 22 or prev is None:
                continue
            closes = [float(x["close"]) for x in seq]
            amounts = [float(x["amount"] or 0) for x in seq]
            rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
            amt_raw = [(abs(rets[i - 1]) / amounts[i] if amounts[i] > 0 else None)
                       for i in range(1, len(closes))]
            amt_vals = [v for v in amt_raw[-20:] if v is not None]
            bf = code_bars.get(fwd_d)
            if closes[-22] <= 0 or not amt_vals or bf is None:
                continue
            panel[c] = {
                "ret20": closes[-1] / closes[-22] - 1,
                "vol20": math.sqrt(sum((r - sum(rets[-20:]) / 20) ** 2
                                       for r in rets[-20:]) / 20),
                "amihud20": sum(amt_vals) / len(amt_vals),
                "loga20": math.log1p(sum(amounts[-20:]) / 20),
                "maxret20": max(rets[-20:]),
            }
            ret_map[c] = float(bf["close"]) / float(b["close"]) - 1
        if len(panel) >= 50:
            panels[d] = panel
            fwd[d] = ret_map

    print(f"[3/3] 相关性与 IC（{len(panels)} 个截面）...", flush=True)
    corr_acc: Dict[Tuple[str, str], List[float]] = {}
    ic_acc: Dict[str, List[float]] = {f: [] for f in FACTORS}
    ic_comp: List[float] = []
    ic_fam: List[float] = []
    # 变量名不与上面逐股循环里的 `panel` / `b`（dict|None）复用
    for d, panel_d in panels.items():
        codes_d = sorted(panel_d)
        vals = {f: [panel_d[c][f] for c in codes_d] for f in FACTORS}
        ranks = {f: _ranks(vals[f]) for f in FACTORS}
        for i, a in enumerate(FACTORS):
            for b_fac in FACTORS[i + 1:]:
                r = _spearman(vals[a], vals[b_fac])
                if r == r:  # 非 NaN
                    corr_acc.setdefault((a, b_fac), []).append(r)
        fwd_r = _ranks([fwd[d][c] for c in codes_d])
        for f in FACTORS:
            r = _pearson(ranks[f], fwd_r)
            if r == r:
                ic_acc[f].append(r)
        comp = [sum(ranks[f][i] * DIRECTIONS[f] for f in FACTORS) / len(FACTORS)
                for i in range(len(codes_d))]
        r = _pearson(comp, fwd_r)
        if r == r:
            ic_comp.append(r)
        fam = [sum(ranks[f][i] * DIRECTIONS[f] * FAMILY_WEIGHTS[f] for f in FACTORS)
               for i in range(len(codes_d))]
        r2 = _pearson(fam, fwd_r)
        if r2 == r2:
            ic_fam.append(r2)

    def stat(v: List[float]) -> Dict[str, Any]:
        n = len(v)
        m = sum(v) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / max(1, n - 1))
        t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
        return {"ic_mean": round(m, 6), "ic_std": round(sd, 6),
                "icir": round(m / sd, 4) if sd else None,
                "t": round(t, 2), "n_periods": n}

    matrix = {f"{a}|{b}": round(sum(v) / len(v), 4)
              for (a, b), v in corr_acc.items()}
    ics = {f: stat(v) for f, v in ic_acc.items()}
    best = max(ics.items(), key=lambda kv: abs(kv[1]["ic_mean"]))
    out: Dict[str, Any] = {
        "dataset": args.dataset, "stocks": len(data),
        "cross_sections": len(panels),
        "avg_cross_sectional_spearman": matrix,
        "factor_ic": ics,
        "composite_equal_weight_ic": stat(ic_comp),
        "composite_family_weighted_ic": stat(ic_fam),
        "best_single_factor": {"factor": best[0], **best[1]},
        "incremental_vs_best": round(
            abs(stat(ic_comp)["ic_mean"]) - abs(best[1]["ic_mean"]), 6),
        "runtime_sec": round(time.time() - t0, 1),
        "note": "方向/权重事前设定（等权 1/5）；前瞻 5 日、每 5 日调仓无重叠；"
                "相关为截面 Spearman 的时间平均。",
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    print(text)
    if args.out:
        # 变量名不与上面 `for f, v in ic_acc.items()` 的 f 复用
        with open(args.out, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(text)
        print(f"已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
