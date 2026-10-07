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
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FACTORS = ["ret20", "vol20", "amihud20", "loga20", "maxret20"]
CONFIGS = ["raw_factor", "adj_factor"]

#: 方向（与冻结引擎一致）：ret20/vol20/loga20/maxret20 反向，amihud20 正向
DIRECTION = {"ret20": -1, "vol20": -1, "amihud20": 1, "loga20": -1, "maxret20": -1}

#: 事前设定的因子子集候选（不得事后增删；见 FACTOR_SUBSET_PREREG.md）
SUBSETS = {
    "S5_all": ["ret20", "vol20", "amihud20", "loga20", "maxret20"],
    "S4_no_amihud": ["ret20", "vol20", "loga20", "maxret20"],
    "S4_no_loga": ["ret20", "vol20", "amihud20", "maxret20"],
    "S3_core": ["ret20", "vol20", "maxret20"],
    "S2_vol_max": ["vol20", "maxret20"],
}


def _factors_at(closes: List[float], amounts: List[float], i: int,
                liq_min: Optional[float] = None, window: int = 80
                ) -> Optional[Dict[str, float]]:
    """以下标 i 为信号日计算五因子 —— 与 `five_factor.compute_factors` 逐字一致。

    ## ⚠️ 关键：`compute_factors` 的结果**依赖传入窗口长度**

    `amihud` 的候选集是「窗口内过滤后取最后 20 个」，
    所以**门槛判定**会随窗口长度变化：

    | 窗口长度 | amihud 候选数 | 通过条件 |
    |---|---|---|
    | 22 根 | 21 | 最多允许 **1** 个无效日 |
    | 80 根（生产 `screen.py`） | 79 | 最多允许 **59** 个无效日 |

    **但因子值本身不变** —— 「最后 20 个有效日」在窗口 ≥20 个有效日时恒定。
    即：窗口长度只影响**哪些股票通过门槛**，不影响通过者的因子值。

    这是生产代码里一个**未被写下来的隐含依赖**（2026-10-07 发现）。
    本函数以 `window=80` 对齐 `screen.py` 的 `read_day_tail(p, 80)`，
    这也是推荐系统的**实际生产口径**。

    ## 2026-10-07 修正（原实现有偏差，由对照测试锁死）

    | 项 | 原 IC 实现 | 生产 `compute_factors` |
    |---|---|---|
    | amihud 取值 | `sum(amihud)/len(amihud)`（分母随停牌数变） | `sum(amihud[-20:])/20.0`（**固定 20**） |
    | amihud 样本门槛 | `len < 15` | `len < 20` |
    | amihud 候选窗口 | 无限回溯 | 受 `window` 限制 |

    ## 关于 `liq_min`

    `None`（默认）= **不做**流动性过滤 —— 跨年代实验需要 P1/P2/P3 三口径
    并列，而 P2（截面中位数）依赖当期截面，无法在逐股计算时决定，
    故把门槛判断移出计算、由调用方按截面筛选。
    传入数值则与生产一致地过滤（默认 1e8 = `five_factor.LIQ_MIN`）。
    """
    if i < 21 or i + 1 > len(closes):
        return None
    if closes[i - 20] <= 0:
        return None
    # rets[-20:]：最近 20 个交易日的收益（等价于生产 rets[-20:]）
    recent = [closes[p] / closes[p - 1] - 1 for p in range(i - 19, i + 1)]
    liq20 = sum(amounts[i - 19:i + 1]) / 20.0
    if liq_min is not None and liq20 < liq_min:
        return None
    # amihud：复刻生产「窗口内过滤 → 取最后 20 个 → 除以固定 20」
    lo = max(1, i - (window - 2))
    valid = [p for p in range(lo, i + 1) if amounts[p] > 0]
    if len(valid) < 20:
        return None
    last20 = valid[-20:]
    return {
        "ret20": closes[i] / closes[i - 20] - 1,
        "vol20": statistics.pstdev(recent),
        "amihud20": sum(abs(closes[p] / closes[p - 1] - 1) / amounts[p]
                        for p in last20) / 20.0,
        "loga20": math.log1p(liq20),
        "maxret20": max(recent),
        "liq20": liq20,
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
    ap.add_argument("--end", default="",
                    help="区间结束日（含）；空=到日历末尾。2026-10-07 新增，"
                         "用于跨年代实验切窗口")
    ap.add_argument("--liq-modes", default="abs",
                    help="流动性口径，逗号分隔：abs,median,none。"
                         "默认 abs（= 1e8 绝对门槛），与 2026-10-07 改动前行为一致；"
                         "跨年代实验用 abs,median,none 三口径并列")
    ap.add_argument("--liq-abs", type=float, default=1e8,
                    help="abs 口径的绝对门槛（默认 1e8，与生产 five_factor.LIQ_MIN 一致）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    args.liq_modes = [m.strip() for m in args.liq_modes.split(",") if m.strip()]
    if not args.liq_modes:
        args.liq_modes = ["abs"]
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
    end = args.end or "99999999"
    rebal = [d for i, d in enumerate(master)
             if i % args.step == 0 and args.start <= d <= end]
    print(f"      主日历 {len(master)} 天，调仓日 {len(rebal)} 个（不重叠）"
          f"；区间 {args.start} ~ {args.end or '末尾'}", flush=True)

    # 列式桶：每期每因子一个 array('d')
    # 每期一个 dict：因子列是 array('d')，adj_factor 是 {因子: array}，
    # flag 是 array('b') —— 混合类型，故值标注为 Any
    buckets: Dict[str, Dict[str, Any]] = {}
    n_used = 0

    print("[2/4] 逐股计算因子（raw / adj 两套）...", flush=True)
    for n, (code, _market, path) in enumerate(stocks, 1):
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
                #: 2026-10-07 新增：保留 liq20 供三口径（P1/P2/P3）截面筛选。
                # 因子计算本身不做门槛过滤，门槛由调用方按口径施加。
                b["liq20"] = array("d")
                buckets[d] = b
            for f in FACTORS:
                b[f].append(fr[f])
                b["adj_factor"][f].append(fa[f])
            b["fwd"].append(fwd)
            b["liq20"].append(fr["liq20"])
            b["flag"].append(1 if any(
                abs(closes_r[k] / closes_r[k - 1] - 1) > lim
                for k in range(max(1, i - 21), i + 1)) else 0)
            n_used += 1

    print(f"[3/4] 样本 {n_used:,} 条，截面 {len(buckets)} 期；计算 IC ...", flush=True)

    def _gate_sel(liqs: List[float], mode: str) -> List[int]:
        """按流动性口径返回保留的样本索引（2026-10-07 新增）。

        口径只影响**样本选择**，不影响因子值本身——因子在填桶时
        已用 `liq_min=None`（不过滤）计算完毕。
        """
        n = len(liqs)
        if mode == "none":
            return list(range(n))
        if mode == "abs":
            th = args.liq_abs
        elif mode == "median":
            th = sorted(liqs)[n // 2]
        else:
            raise SystemExit(f"未知 liq-mode: {mode}")
        return [k for k in range(n) if liqs[k] >= th]

    def _run_gate(mode: str) -> Dict[str, Any]:
        """按某一流动性口径统计 IC。"""
        ser: Dict[str, Dict[str, List[float]]] = {
            cfg: {f: [] for f in FACTORS} for cfg in CONFIGS}
        ser["raw_flag_excluded"] = {f: [] for f in FACTORS}
        comp_s: Dict[str, List[float]] = {s: [] for s in SUBSETS}
        comp_s_ex: Dict[str, List[float]] = {s: [] for s in SUBSETS}
        flags: List[float] = []
        sizes: List[int] = []
        for d in sorted(buckets):
            b = buckets[d]
            sel = _gate_sel(list(b["liq20"]), mode)
            if len(sel) < args.min_cross_section:
                continue
            sizes.append(len(sel))
            n = len(sel)
            fwd = [b["fwd"][k] for k in sel]
            keep = [j for j, k in enumerate(sel) if b["flag"][k] == 0]
            flags.append(1 - len(keep) / n)
            for f in FACTORS:
                raw = [b[f][k] for k in sel]
                adj = [b["adj_factor"][f][k] for k in sel]
                ic = _spearman(raw, fwd)
                if ic is not None:
                    ser["raw_factor"][f].append(ic)
                ic2 = _spearman(adj, fwd)
                if ic2 is not None:
                    ser["adj_factor"][f].append(ic2)
                if len(keep) >= args.min_cross_section:
                    ic3 = _spearman([raw[j] for j in keep],
                                    [fwd[j] for j in keep])
                    if ic3 is not None:
                        ser["raw_flag_excluded"][f].append(ic3)
            # 子集合成分的 IC（方向化分位均值，复权价口径）
            for sname, keys in SUBSETS.items():
                rk = {k: _rank([b["adj_factor"][k][j] for j in sel])
                      for k in keys}
                comp = [sum((rk[k][idx] / n if DIRECTION[k] > 0
                             else 1.0 - rk[k][idx] / n)
                            for k in keys) / len(keys) for idx in range(n)]
                ic_c = _spearman(comp, fwd)
                if ic_c is not None:
                    comp_s[sname].append(ic_c)
                if len(keep) >= args.min_cross_section:
                    ic_ce = _spearman([comp[j] for j in keep],
                                      [fwd[j] for j in keep])
                    if ic_ce is not None:
                        comp_s_ex[sname].append(ic_ce)
        return {"ser": ser, "comp_s": comp_s, "comp_s_ex": comp_s_ex,
                "flags": flags, "sizes": sizes}

    def stat(v: List[float]) -> Dict:
        if len(v) < 2:
            return {"ic_mean": None, "t": None, "n": len(v)}
        m = sum(v) / len(v)
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
        t = m / (sd / math.sqrt(len(v))) if sd > 0 else 0.0
        return {"ic_mean": round(m, 6), "t": round(t, 2), "n": len(v)}

    #: 按口径逐个统计（口径只影响样本选择）
    by_gate: Dict[str, Any] = {}
    for mode in args.liq_modes:
        g = _run_gate(mode)
        s_ = g["ser"]
        by_gate[mode] = {
            "ic": {cfg: {f: stat(s_[cfg][f]) for f in FACTORS} for cfg in s_},
            "composite_ic": {x: stat(g["comp_s"][x]) for x in SUBSETS},
            "composite_ic_jump_excluded": {x: stat(g["comp_s_ex"][x])
                                           for x in SUBSETS},
            "cross_sections": len(g["sizes"]),
            "avg_cross_section": (round(sum(g["sizes"]) / len(g["sizes"]), 1)
                                  if g["sizes"] else None),
            "flagged_share_mean": (round(sum(g["flags"]) / len(g["flags"]), 4)
                                   if g["flags"] else None),
        }
        print(f"      [{mode:6s}] 期数 {by_gate[mode]['cross_sections']:3d}，"
              f"平均截面 {by_gate[mode]['avg_cross_section']}", flush=True)

    # 主输出 = abs 口径（与 2026-10-07 改动前行为一致，便于与历史结论对照）
    main_gate = "abs" if "abs" in by_gate else args.liq_modes[0]
    mg = by_gate[main_gate]
    res = mg["ic"]
    comp_res = mg["composite_ic"]
    comp_ex = mg["composite_ic_jump_excluded"]
    out = {
        "source": args.vipdoc, "stocks": len(stocks), "samples": n_used,
        "cross_sections": mg["cross_sections"],
        "flagged_share_mean": mg["flagged_share_mean"],
        "ic": res,
        "composite_ic": comp_res,
        "composite_ic_jump_excluded": comp_ex,
        "ic_by_gate": by_gate,
        "main_gate": main_gate,
        "liq_modes": args.liq_modes,
        "liq_abs": args.liq_abs,
        "range": {"start": args.start, "end": args.end or None},
        "runtime_sec": round(time.time() - t0, 1),
        "note": "标签统一用前复权价（收益必须先复权）；raw_factor=未复权价算因子；"
                "raw_flag_excluded=未复权且剔除窗口内含超涨跌停跳空的样本。"
                "主输出 ic 为 abs 口径；ic_by_gate 含全部口径。"
                "2026-10-07 起 _factors_at 与生产 compute_factors 逐字一致"
                "（原 amihud 分母固定 20 / 样本门槛 20 的偏差已修）。",
    }
    print("[4/4] 结果：")
    print(f"{'因子':14s} {'原始价 IC/t':>20s} {'复权价 IC/t':>20s} {'剔跳空 IC/t':>20s}")
    for f in FACTORS:
        r = res["raw_factor"][f]
        a = res["adj_factor"][f]
        x = res["raw_flag_excluded"][f]
        print(f"{f:14s} {r['ic_mean']:+.6f}/{r['t']:+.2f}  "
              f"{a['ic_mean']:+.6f}/{a['t']:+.2f}  {x['ic_mean']:+.6f}/{x['t']:+.2f}")
    print(f"\n{'子集（复权价）':18s} {'IC / t（全样本）':>24s} {'IC / t（剔跳空）':>24s}")
    for s in SUBSETS:
        a, x = comp_res[s], comp_ex[s]
        print(f"{s:18s} {a['ic_mean']:+.6f}/{a['t']:+.2f}      "
              f"{x['ic_mean']:+.6f}/{x['t']:+.2f}")
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
