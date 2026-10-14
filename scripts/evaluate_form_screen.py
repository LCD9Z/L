# -*- coding: utf-8 -*-
"""形态策略冗余度诊断：Sequoia-X 六策略是否值得进入预注册队列。

**这不是 alpha 检验。** 本脚本不计算任何前瞻收益、不构造多空组合、
不宣称有效性——它只回答一个问题：

    Sequoia-X 六个技术形态所提供的**横截面信息**，
    有多少已经包含在本项目已验证的五因子里？

只有先回答这个问题，才能判断「是否需要」把它们写成预注册文档
（低冗余 = 有增量信息维度 = 值得预注册；高冗余 = 不必消耗实验预算）。

被判定的形态（连续化代理）：
| 代理 | 对应策略 | 定义 |
|------|---------|------|
| break20 | TurtleTrade | close / max(high[i-20:i]) - 1 |
| ma_cross | MaVolume | MA5 / MA20 - 1 |
| vol_surge | MaVolume | vol[i] / mean(vol[i-20:i]) |
| flag_mom | HighTightFlag | max(high[i-39:i+1]) / min(low[i-39:i+1]) |
| flag_cons | HighTightFlag | max(high[i-9:i+1]) / min(low[i-9:i+1]) |
| rps120 | RpsBreakout | close[i] / close[i-120] - 1 |
| limitup_5d | LimitUpShakeout 家族 | 近 5 日涨幅 ≥ 涨停幅度-0.5% 的天数 |
| limitdown_5d | UptrendLimitDown | 近 5 日跌幅 ≤ -(涨停幅度-0.5%) 的天数 |
| yang_5d | TurtleTrade 过滤项 | 近 5 日阳线（close>open）占比 |

对照：五因子 ret20 / vol20 / amihud20 / loga20 / maxret20。

方法：以**上证指数日历**对齐截面（每 20 个交易日一个，不重叠），
逐截面算 Spearman 秩相关并取均值。判定门槛（事前设定）：
平均 |ρ| ≥ 0.7 高冗余；0.4~0.7 部分重叠；< 0.4 独立维度。
另统计原始 0/1 定义的触发率，评估池子容量与可跟踪性。

用法::

    python scripts/evaluate_form_screen.py --vipdoc D:/new_tdx/vipdoc \
        --events-cache data/gbbq_events.csv --sections 20
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tdx_native import adjust  # noqa: E402
from tdx_native import day_reader  # noqa: E402
from tdx_native import five_factor  # noqa: E402
from tdx_native import gbbq_reader  # noqa: E402

FACTORS = ["ret20", "vol20", "amihud20", "loga20", "maxret20"]
FORMS = ["break20", "ma_cross", "vol_surge", "flag_mom", "flag_cons",
         "rps120", "limitup_5d", "limitdown_5d", "yang_5d"]
TRIGGERS = ["turtle", "ma_volume", "flag", "shakeout", "limitdown", "rps_strong"]
TAIL_BARS = 800


def _ranks(xs: List[float]) -> List[float]:
    """平均秩。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 40:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((v - mx) ** 2 for v in rx))
    dy = math.sqrt(sum((v - my) ** 2 for v in ry))
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy)


def _sma(vals: List[float], k: int) -> Optional[float]:
    if len(vals) < k:
        return None
    return sum(vals[-k:]) / k


def form_values(bars: List[dict], i: int, lim: float) -> Optional[Dict[str, float]]:
    """在索引 i（含）处计算形态代理；数据不足返回 None。"""
    if i < 140:
        return None
    closes = [b["close"] for b in bars[:i + 1]]
    highs = [b["high"] for b in bars[:i + 1]]
    lows = [b["low"] for b in bars[:i + 1]]
    opens = [b["open"] for b in bars[:i + 1]]
    vols = [b["volume"] for b in bars[:i + 1]]

    h20 = max(highs[i - 20:i])
    if h20 <= 0:
        return None
    ma5, ma20 = _sma(closes, 5), _sma(closes, 20)
    vma20 = _sma(vols[:-1], 20)
    if not ma20 or not vma20:
        return None
    h40, l40 = max(highs[i - 39:i + 1]), min(lows[i - 39:i + 1])
    h10, l10 = max(highs[i - 9:i + 1]), min(lows[i - 9:i + 1])
    if l40 <= 0 or l10 <= 0:
        return None
    c120 = closes[i - 120]
    if c120 <= 0:
        return None

    thr = lim - 0.005
    rets5 = [closes[k] / closes[k - 1] - 1 for k in range(i - 4, i + 1)]
    return {
        "break20": closes[i] / h20 - 1,
        "ma_cross": (ma5 - ma20) / ma20,
        "vol_surge": vols[i] / vma20,
        "flag_mom": h40 / l40,
        "flag_cons": h10 / l10,
        "rps120": closes[i] / c120 - 1,
        "limitup_5d": float(sum(1 for r in rets5 if r >= thr)),
        "limitdown_5d": float(sum(1 for r in rets5 if r <= -thr)),
        "yang_5d": sum(1 for k in range(i - 4, i + 1)
                       if closes[k] > opens[k]) / 5.0,
    }


def trigger_flags(bars: List[dict], i: int, lim: float, liq: float) -> Dict[str, bool]:
    """Sequoia-X 六策略的原始 0/1 触发（rps 的分位条件在截面层判定）。"""
    out = dict.fromkeys(TRIGGERS, False)
    if i < 140:
        return out
    closes = [b["close"] for b in bars[:i + 1]]
    highs = [b["high"] for b in bars[:i + 1]]
    lows = [b["low"] for b in bars[:i + 1]]
    opens = [b["open"] for b in bars[:i + 1]]
    vols = [b["volume"] for b in bars[:i + 1]]

    h20 = max(highs[i - 20:i])
    ma5, ma20 = _sma(closes, 5), _sma(closes, 20)
    ma5p, ma20p = _sma(closes[:-1], 5), _sma(closes[:-1], 20)
    vma20, vma20p = _sma(vols[:-1], 20), _sma(vols[:-2], 20)

    out["turtle"] = (closes[i] > h20 and liq > 1e8
                     and closes[i] > opens[i] and closes[i] > closes[i - 1])
    if ma5 and ma20 and ma5p and ma20p and vma20:
        out["ma_volume"] = (ma5p < ma20p and ma5 > ma20
                            and vols[i] > vma20 * 1.5)
    h40, l40 = max(highs[i - 39:i + 1]), min(lows[i - 39:i + 1])
    h10, l10 = max(highs[i - 9:i + 1]), min(lows[i - 9:i + 1])
    if l40 > 0 and l10 > 0 and vma20p:
        out["flag"] = (h40 / l40 > 1.6 and h10 / l10 < 1.15
                       and l10 >= h40 * 0.8 and vols[i] < vma20p * 0.6)
    if closes[i - 2] > 0:
        lu_y = closes[i - 1] >= closes[i - 2] * (1 + lim - 0.005)
        out["shakeout"] = (lu_y and closes[i] < opens[i]
                           and vols[i] > vols[i - 1] * 2.0
                           and lows[i] >= closes[i - 1])
    ma60p = _sma(closes[:-1], 60)
    if ma20p and ma60p and vma20 and closes[i - 1] > 0:
        out["limitdown"] = (ma20p > ma60p
                            and closes[i] <= closes[i - 1] * (1 - lim + 0.005)
                            and vols[i] > vma20 * 2.0)
    return out


def run(vipdoc: str, events_cache: str, n_sections: int) -> Dict:
    events = gbbq_reader.load_events(events_cache) if events_cache else {}
    paths = sorted(day_reader.scan_paths(vipdoc), key=lambda t: t[0])
    print(f"股票池 {len(paths)} 只；复权事件覆盖 {len(events)} 只")

    cache: List[dict] = []
    for code, _market, path in paths:
        bars = day_reader.read_day_tail(path, TAIL_BARS)
        if len(bars) < 200:
            continue
        if events:
            near = [e for e in events.get(code, []) if e[0] >= bars[0]["date"]]
            if near:
                bars = adjust.apply_qfq(bars, near)
        cache.append({"code": code, "bars": bars,
                      "dates": [b["date"] for b in bars],
                      "lim": day_reader.limit_pct(code)})
    print(f"可用 {len(cache)} 只（≥200 根）")

    # 以指数日历对齐截面（关键：同一交易日，避免"各自最后 N 根"错位）
    idx_path = os.path.join(vipdoc, "sh", "lday", "sh000001.day")
    cal = [b["date"] for b in day_reader.read_day_all(idx_path)]
    step = 20
    section_dates = [cal[-1 - k * step] for k in range(n_sections)
                     if k * step < len(cal)]
    print(f"截面日期 {len(section_dates)} 个：{section_dates[0]} … {section_dates[-1]}")

    corr_acc = {f: {g: [] for g in FACTORS} for f in FORMS}
    trig_acc = {k: [] for k in TRIGGERS}
    n_used = 0
    n_stock_used = []

    for D in section_dates:
        cols = {f: [] for f in FACTORS}
        fcols = {f: [] for f in FORMS}
        pair = []          # (f_index, rps120, close_ge_flag)
        trig = dict.fromkeys(TRIGGERS, 0)
        for c in cache:
            i = bisect.bisect_right(c["dates"], D) - 1
            if i < 140:
                continue
            f = five_factor.compute_factors(c["bars"][:i + 1])
            if not f:
                continue
            fv = form_values(c["bars"], i, c["lim"])
            if fv is None:
                continue
            for k in FACTORS:
                cols[k].append(f[k])
            for k in FORMS:
                fcols[k].append(fv[k])
            f_idx = len(cols["ret20"]) - 1
            bars = c["bars"]
            h140 = max(b["high"] for b in bars[i - 139:i + 1])
            pair.append((f_idx, fv["rps120"],
                         bars[i]["close"] >= h140 * 0.9))
            fi = trigger_flags(bars, i, c["lim"], f["liq20"])
            for k in ("turtle", "ma_volume", "flag", "shakeout", "limitdown"):
                trig[k] += 1 if fi[k] else 0
        if len(cols["ret20"]) < 200:
            continue
        n_used += 1
        n_stock_used.append(len(cols["ret20"]))
        # rps_strong：120 日涨幅分位 ≥90 且 close ≥140 日高 ×0.9
        rps_sorted = sorted(p[1] for p in pair)
        thr90 = rps_sorted[int(len(rps_sorted) * 0.9)] if rps_sorted else None
        if thr90 is not None:
            trig["rps_strong"] = sum(1 for _, r, g in pair
                                     if r >= thr90 and g)
        for fname in FORMS:
            for g in FACTORS:
                rho = spearman(fcols[fname], cols[g])
                if rho is not None:
                    corr_acc[fname][g].append(rho)
        for k in TRIGGERS:
            trig_acc[k].append(trig[k] / len(cols["ret20"]))

    result = {"n_sections_used": n_used,
              "n_stocks_per_section_avg":
                  (sum(n_stock_used) / len(n_stock_used)) if n_stock_used else 0,
              "section_dates": [section_dates[0], section_dates[-1]],
              "corr": {}, "trigger_rate": {}}
    for fname in FORMS:
        result["corr"][fname] = {}
        for g in FACTORS:
            v = corr_acc[fname][g]
            if v:
                result["corr"][fname][g] = {
                    "mean": sum(v) / len(v),
                    "max_abs": max(abs(x) for x in v),
                    "n": len(v)}
    for k, v in trig_acc.items():
        if v:
            result["trigger_rate"][k] = {
                "mean": sum(v) / len(v), "max": max(v), "n": len(v)}
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="形态冗余度诊断")
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--events-cache", default="data/gbbq_events.csv")
    ap.add_argument("--sections", type=int, default=20)
    ap.add_argument("--out", default="reports/form_screen_eval.json")
    args = ap.parse_args()

    res = run(args.vipdoc, args.events_cache, args.sections)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    print(f"\n截面数 {res['n_sections_used']}（"
          f"{res['section_dates'][0]}~{res['section_dates'][1]}，"
          f"每截面均 {res['n_stocks_per_section_avg']:.0f} 只）")
    head = f"{'形态':<14}" + "".join(f"{g:>10}" for g in FACTORS)
    print(head)
    for fname in FORMS:
        row = f"{fname:<14}"
        for g in FACTORS:
            v = res["corr"][fname].get(g)
            row += f"{(v['mean'] if v else float('nan')):>10.3f}"
        print(row)
    print("\n触发率（原始 0/1 定义，截面均值）：")
    for k, v in res["trigger_rate"].items():
        print(f"  {k:<14} {v['mean']:.4%}（最大 {v['max']:.2%}）")
    print(f"\n写出 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
