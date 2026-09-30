# -*- coding: utf-8 -*-
"""全市场五因子 IC 研究（原生 TDX 数据，原始价 vs 前复权对照）。

要回答两个问题：

1. **样本稳健性**：v2 研究的 1500 只样本是否代表全市场？现在用**全部 A 股**
   （~5600 只）重跑同一套五因子 IC。
2. **除权污染的量化**：用原始价算因子（ret20/vol20/maxret20 会被除权跳空污染）
   与用前复权价算因子，IC 差多少？—— v2 研究用的是前复权数据，
   本实验直接量化"不复权会带来多大偏差"。

口径（与 `reports/v2_factor_study.json` 对齐）：5 日前瞻、每 5 交易日调仓、无重叠、
截面 Spearman 秩 IC、min_cross_section 50；标签统一用**复权价**（收益本身必须先复权）。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from array import array
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FACTORS = ["ret20", "vol20", "amihud20", "loga20", "maxret20"]
CONFIGS = ["raw_factor", "adj_factor"]


def _factors_at(closes: List[float], amounts: List[float], i: int
                ) -> Optional[Dict[str, float]]:
    """以下标 i 为信号日计算五因子（需 i>=21）。"""
    if i < 21 or i + 1 >= len(closes):
        return None
    c = closes[i]
    if c <= 0 or closes[i - 21] <= 0:
        return None
    rets = [closes[k] / closes[k - 1] - 1 for k in range(i - 19, i + 1)]
    liq20 = sum(amounts[i - 19:i + 1]) / 20.0
    if liq20 < 1e8:
        return None
    amihud = []
    for k in range(i - 19, i + 1):
        if amounts[k] > 0 and closes[k - 1] > 0:
            amihud.append(abs(closes[k] / closes[k - 1] - 1) / amounts[k])
    if len(amihud) < 15:
        return None
    return {
        "ret20": c / closes[i - 21] - 1,
        "vol20": statistics.pstdev(rets),
        "amihud20": sum(amihud) / len(amihud),
        "loga20": math.log1p(liq20),
        "maxret20": max(rets),
    }


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
    n = len(x)
    if n < 5:
        return None
    rx, ry = _rank(x), _rank(y)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[k] - mx) * (ry[k] - my) for k in range(n))
    dx = math.sqrt(sum((v - mx) ** 2 for v in rx))
    dy = math.sqrt(sum((v - my) ** 2 for v in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def main() -> int:
    ap = argparse.ArgumentParser(description="全市场五因子 IC（原始 vs 复权）")
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--events-cache", default="data/gbbq_events.csv")
    ap.add_argument("--max-stocks", type=int, default=0, help="0=全部")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--min-cross-section", type=int, default=200)
    ap.add_argument("--start", default="20160101",
                    help="样本起点（与 v2 研究可比；早期年份仅少数股票在交易）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    t0 = time.time()

    from tdx_native import adjust, day_reader, gbbq_reader
    events = gbbq_reader.load_events(args.events_cache) if args.events_cache else {}
    print(f"[1/4] 权息事件 {sum(len(v) for v in events.values())} 条 / "
          f"{len(events)} 只", flush=True)

    stocks = day_reader.scan_paths(args.vipdoc)
    if args.max_stocks and len(stocks) > args.max_stocks:
        step = len(stocks) / args.max_stocks
        stocks = [stocks[int(i * step)] for i in range(args.max_stocks)]
    print(f"      股票 {len(stocks)} 只", flush=True)

    # 统一交易日历（用上证指数 sh000001.day 作主日历）→ 每 5 个交易日一个调仓日，
    # 保证截面之间不重叠（否则 5 日前瞻重叠会高估 t 值）。
    cal_path = os.path.join(args.vipdoc, "sh", "lday", "sh000001.day")
    cal = day_reader.read_day_all(cal_path)
    master = [b["date"] for b in cal]
    rebal = [d for i, d in enumerate(master) if i % args.step == 0 and d >= args.start]
    print(f"      主日历 {len(master)} 天，调仓日 {len(rebal)} 个（不重叠）", flush=True)
    rebal_set = set(rebal)

    # 列式桶：每期每因子一个 array('d')
    buckets: Dict[str, Dict[str, array]] = {}
    n_used = 0

    print("[2/4] 逐股计算因子（raw / adj 两套）...", flush=True)
    for n, (code, market, path) in enumerate(stocks, 1):
        if n % 500 == 0:
            print(f"      {n}/{len(stocks)}  ({time.time()-t0:.0f}s)", flush=True)
        bars = day_reader.read_day_all(path)
        if len(bars) < 40:
            continue
        ev = events.get(code) or []
        adj_bars = adjust.apply_qfq(bars, ev) if ev else bars
        dates = [b["date"] for b in bars]
        didx = {d: k for k, d in enumerate(dates)}
        closes_r = [b["close"] for b in bars]
        closes_a = [b["close"] for b in adj_bars]
        amounts = [b["amount"] for b in bars]
        lim = day_reader.limit_pct(code)
        for d in rebal:
            i = didx.get(d)
            if i is None or i < 21 or i + args.horizon >= len(bars):
                continue
            fr = _factors_at(closes_r, amounts, i)
            if fr is None:
                continue
            fa = _factors_at(closes_a, amounts, i)
            if fa is None:
                continue
            c0, c1 = closes_a[i], closes_a[i + args.horizon]
            if c0 <= 0:
                continue
            fwd = c1 / c0 - 1
            b = buckets.get(d)
            if b is None:
                b = {f: array("d") for f in FACTORS}
                b["adj_factor"] = {f: array("d") for f in FACTORS}
                b["fwd"] = array("d")
                b["flag"] = array("b")
                buckets[d] = b
            for f in FACTORS:
                b[f].append(fr[f])
                b["adj_factor"][f].append(fa[f])
            b["fwd"].append(fwd)
            b["flag"].append(1 if any(
                abs(closes_r[k] / closes_r[k - 1] - 1) > lim
                for k in range(max(1, i - 21), i + 1)) else 0)
            n_used += 1

    print(f"[3/4] 样本 {n_used:,} 条，截面 {len(buckets)} 期；计算 IC ...", flush=True)
    series: Dict[str, Dict[str, List[float]]] = {
        cfg: {f: [] for f in FACTORS} for cfg in CONFIGS}
    series["raw_flag_excluded"] = {f: [] for f in FACTORS}
    flagged_share = []

    for d in sorted(buckets):
        b = buckets[d]
        n = len(b["fwd"])
        if n < args.min_cross_section:
            continue
        fwd = list(b["fwd"])
        keep = [k for k in range(n) if b["flag"][k] == 0]
        flagged_share.append(1 - len(keep) / n)
        for f in FACTORS:
            raw = list(b[f])
            adj = list(b["adj_factor"][f])
            ic = _spearman(raw, fwd)
            if ic is not None:
                series["raw_factor"][f].append(ic)
            ic2 = _spearman(adj, fwd)
            if ic2 is not None:
                series["adj_factor"][f].append(ic2)
            if len(keep) >= args.min_cross_section:
                ic3 = _spearman([raw[k] for k in keep], [fwd[k] for k in keep])
                if ic3 is not None:
                    series["raw_flag_excluded"][f].append(ic3)

    def stat(v: List[float]) -> Dict:
        if len(v) < 2:
            return {"ic_mean": None, "t": None, "n": len(v)}
        m = sum(v) / len(v)
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
        t = m / (sd / math.sqrt(len(v))) if sd > 0 else 0.0
        return {"ic_mean": round(m, 6), "t": round(t, 2), "n": len(v)}

    res = {cfg: {f: stat(series[cfg][f]) for f in FACTORS} for cfg in series}
    out = {
        "source": args.vipdoc, "stocks": len(stocks), "samples": n_used,
        "cross_sections": len(buckets),
        "flagged_share_mean": round(sum(flagged_share) / len(flagged_share), 4)
        if flagged_share else None,
        "ic": res,
        "runtime_sec": round(time.time() - t0, 1),
        "note": "标签统一用前复权价（收益必须先复权）；raw_factor=未复权价算因子；"
                "raw_flag_excluded=未复权且剔除窗口内含超涨跌停跳空的样本。",
    }
    print("[4/4] 结果：")
    print(f"{'因子':14s} {'原始价 IC/t':>20s} {'复权价 IC/t':>20s} {'剔跳空 IC/t':>20s}")
    for f in FACTORS:
        r = res["raw_factor"][f]
        a = res["adj_factor"][f]
        x = res["raw_flag_excluded"][f]
        print(f"{f:14s} {r['ic_mean']:+.6f}/{r['t']:+.2f}  "
              f"{a['ic_mean']:+.6f}/{a['t']:+.2f}  {x['ic_mean']:+.6f}/{x['t']:+.2f}")
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
