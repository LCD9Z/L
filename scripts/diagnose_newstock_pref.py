# -*- coding: utf-8 -*-
"""H-N1 替代诊断：五因子是否系统性偏好次新股。

背景（见 CANDIDATE_FILTERS_PREREG.md §六/§七）：v2 数据集（1,500 只、
`min_rows=504`）中上市不满 365 天的标的为 **0 只**，H-N1 无法在该数据集上检验。
故改用 `tdx_native` 原生全量数据（5,613 只，含 158 只次新股）做定向诊断。

诊断回答两个问题：
1. 五因子打分 + V1 尾部剔除后，Top-20 里次新股占多少？（基准：池中占比 ~2.8%）
2. 加上 V2 跳空过滤后，次新股在 Top-20 里还剩多少？
   —— 若 V2 已把次新股清掉，则 N1 相对 V2 是**冗余**的。

同时统计次新股组与老股组的 T+20 收益（T+1 开盘 → T+20 收盘），
判断次新股进入组合是"贡献"还是"拖累"。

**这是诊断，不是 alpha 检验**：不构造完整组合、不宣称收益改进。

用法::

    python scripts/diagnose_newstock_pref.py --vipdoc D:/new_tdx/vipdoc \
        --names data/names.csv --sections 20
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import struct
import sys
from datetime import date
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tdx_native import adjust  # noqa: E402
from tdx_native import day_reader  # noqa: E402
from tdx_native import five_factor  # noqa: E402
from tdx_native import gbbq_reader  # noqa: E402

TAIL = 320
NEW_DAYS = 365


def _first_bar_date(path: str) -> Optional[int]:
    try:
        with open(path, "rb") as fh:
            b = fh.read(32)
        if len(b) < 32:
            return None
        return int(struct.unpack("<I", b[:4])[0])
    except Exception:
        return None


def _as_date(x: int) -> date:
    return date(x // 10000, x // 100 % 100, x % 100)


def _has_jump(bars: List[dict], i: int, code: str) -> bool:
    """V2：信号日前 21 根内含超涨跌停跳空。"""
    seg = bars[max(0, i - 20):i + 1]
    lim = day_reader.limit_pct(code) - 0.002
    for k in range(1, len(seg)):
        p0 = float(seg[k - 1].get("close") or 0)
        p1 = float(seg[k].get("close") or 0)
        if p0 > 0 and p1 > 0 and abs(p1 / p0 - 1) > lim:
            return True
    return False


def run(vipdoc: str, names_csv: str, events_cache: str,
        n_sections: int, top_n: int) -> Dict:
    names = day_reader.load_names(names_csv) if names_csv else {}
    events = gbbq_reader.load_events(events_cache) if events_cache else {}

    cache = []
    for code, mkt, path in day_reader.scan_paths(vipdoc):
        bars = day_reader.read_day_tail(path, TAIL)
        if len(bars) < 200:
            continue
        if events:
            near = [e for e in events.get(code, []) if e[0] >= bars[0]["date"]]
            if near:
                bars = adjust.apply_qfq(bars, near)
        cache.append({"code": code, "bars": bars,
                      "dates": [b["date"] for b in bars],
                      "first": _first_bar_date(path),
                      "st": "ST" in (names.get(code, "").upper())})
    print(f"可用标的 {len(cache)} 只（≥200 根）", flush=True)
    by_code = {c["code"]: c for c in cache}

    idx = os.path.join(vipdoc, "sh", "lday", "sh000001.day")
    cal = [b["date"] for b in day_reader.read_day_all(idx)]
    step = 8
    section_dates = [cal[-1 - k * step] for k in range(n_sections)
                     if k * step < len(cal)]

    stats = {"pool_new": [], "top_new": [], "top_new_v2": [],
             "top_ret_new": [], "top_ret_old": [], "top_ret_all": [],
             "pool_n": []}
    for D in section_dates:
        cands = []
        d_obj = _as_date(int(D))
        for c in cache:
            if c["st"]:
                continue
            i = bisect.bisect_right(c["dates"], D) - 1
            if i < 130 or i + 20 >= len(c["bars"]):
                continue
            f = five_factor.compute_factors(c["bars"][:i + 1])
            if not f:
                continue
            f["code"] = c["code"]
            f["_i"] = i
            f["_new"] = (c["first"] is not None
                         and (d_obj - _as_date(c["first"])).days < NEW_DAYS)
            cands.append(f)
        if len(cands) < 200:
            continue
        five_factor.composite_score(cands)
        # V1：剔除 ret20 最高 20%
        rr = five_factor.pct_rank([c["ret20"] for c in cands])
        v1 = [c for c, r in zip(cands, rr, strict=True) if r <= 0.8]
        if len(v1) < 50:
            continue
        stats["pool_n"].append(len(v1))
        stats["pool_new"].append(sum(1 for c in v1 if c["_new"]) / len(v1))

        v1.sort(key=lambda c: (-c["score"], c["code"]))
        top = v1[:top_n]
        v2 = [c for c in v1
              if not _has_jump(by_code[c["code"]]["bars"], c["_i"],
                               c["code"])][:top_n]
        stats["top_new"].append(sum(1 for c in top if c["_new"]) / len(top))
        stats["top_new_v2"].append(sum(1 for c in v2 if c["_new"]) / max(1, len(v2)))

        for c in top:
            bars = by_code[c["code"]]["bars"]
            i = c["_i"]
            o = float(bars[i + 1]["open"] or 0)
            cl = float(bars[i + 20]["close"] or 0)
            if o > 0 and cl > 0:
                r = cl / o - 1
                stats["top_ret_all"].append(r)
                (stats["top_ret_new"] if c["_new"]
                 else stats["top_ret_old"]).append(r)

    def _mean(v):
        return (sum(v) / len(v), len(v)) if v else (None, 0)

    out = {"n_sections": len(stats["pool_n"]),
           "sections": [section_dates[0], section_dates[-1]],
           "pool_n_avg": (sum(stats["pool_n"]) / len(stats["pool_n"])
                          if stats["pool_n"] else 0)}
    for k, label in (("pool_new", "池中次新占比"),
                     ("top_new", "Top20 次新占比(无V2)"),
                     ("top_new_v2", "Top20 次新占比(含V2)")):
        m, n = _mean(stats[k])
        out[k] = {"mean": m, "n_sections": n}
        print(f"{label:<24} {m:.2%}" if m is not None else f"{label}: n/a")
    for k, label in (("top_ret_all", "Top20 T+20 收益(全部)"),
                     ("top_ret_new", "Top20 T+20 收益(次新组)"),
                     ("top_ret_old", "Top20 T+20 收益(老股组)")):
        m, n = _mean(stats[k])
        out[k] = {"mean": m, "n": n}
        print(f"{label:<24} {m:+.2%}  (n={n})" if m is not None
              else f"{label}: n/a")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="H-N1 替代诊断：因子是否偏好次新股")
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--names", default="data/names.csv")
    ap.add_argument("--events-cache", default="data/gbbq_events.csv")
    ap.add_argument("--sections", type=int, default=20)
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--out", default="reports/newstock_pref_diag.json")
    args = ap.parse_args()

    # run() 内部自建 code→bars 索引
    res = run(args.vipdoc, args.names, args.events_cache,
              args.sections, args.top_n)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"\n写出 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
