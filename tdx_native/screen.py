# -*- coding: utf-8 -*-
"""五因子日度选股 · 原生 TDX 数据入口（零第三方依赖）。

用法::

    python -m tdx_native.screen --vipdoc D:/new_tdx/vipdoc --top 20
    python -m tdx_native.screen --vipdoc D:/new_tdx/vipdoc --top 20 \
        --names D:/names.csv --exclude-ret20-top 0.20 --out report.json

参数::

    --vipdoc            通达信 vipdoc 目录（含 sh/sz/bj/lday）
    --top               输出前 N 只（默认 20，即 C20）
    --exclude-ret20-top 可选 V1 尾部剔除：剔除当日 ret20 最高分位（如 0.20）
    --names             可选 code,name 的 CSV，用于显示名称 + 做 ST 剔除
    --out               可选，把结果写为 JSON
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Dict, List, Tuple

from . import adjust
from . import day_reader
from . import five_factor
from . import gbbq_reader


def run(vipdoc: str, top_n: int = 20, exclude_ret20_top: float = 0.0,
        names_csv: str = "", out: str = "", events_cache: str = "") -> Dict:
    t0 = time.time()
    names = day_reader.load_names(names_csv)
    events = gbbq_reader.load_events(events_cache) if events_cache else {}
    if events_cache:
        print(f"      已载入权息事件 {sum(len(v) for v in events.values())} 条"
              f"（覆盖 {len(events)} 只）→ 启用前复权", flush=True)

    stocks = day_reader.scan_stocks(vipdoc)
    print(f"[1/3] 扫描到真实 A 股股票 {len(stocks)} 只", flush=True)

    # 统一截止日：全池最新交易日；停牌过久（落后 >10 交易日）的剔除
    last_dates = [b[-1]["date"] for _, _, _, b in stocks]
    as_of = max(last_dates)
    fresh = []
    for code, market, path, bars in stocks:
        if bars[-1]["date"] < as_of and int(as_of) - int(bars[-1]["date"]) > 10:
            continue
        bars = [b for b in bars if b["date"] <= as_of]
        fresh.append((code, market, path, bars))
    print(f"      截止日 {as_of}；剔除停牌过久后 {len(fresh)} 只", flush=True)

    # ST 剔除（仅在有名称映射时可用）
    st_removed = 0
    candidates: List[Dict[str, float]] = []
    adjusted_cnt = 0
    for code, market, path, bars in fresh:
        nm = names.get(code, "")
        if nm and ("ST" in nm.upper()):
            st_removed += 1
            continue
        if events and events.get(code):
            # 只在窗口内有权息事件时才复权（无事件则原价即复权价）
            near = [e for e in events[code] if e[0] >= bars[0]["date"]]
            if near:
                bars = adjust.apply_qfq(bars, near)
                adjusted_cnt += 1
        f = five_factor.compute_factors(bars)
        if not f:
            continue
        f["code"] = code
        f["market"] = market
        f["name"] = nm
        candidates.append(f)
    print(f"      打分前 {len(candidates)} 只（ST 剔除 {st_removed} 只"
          f"{'，无名称映射未做 ST 剔除' if not names else ''}；"
          f"复权 {adjusted_cnt} 只）", flush=True)

    five_factor.composite_score(candidates)

    if exclude_ret20_top > 0:
        cut = 1.0 - exclude_ret20_top
        rr = five_factor.pct_rank([c["ret20"] for c in candidates])
        kept = [c for c, r in zip(candidates, rr) if r <= cut]
        print(f"      V1 尾部剔除（ret20 最高 {exclude_ret20_top:.0%}）: "
              f"{len(candidates)} -> {len(kept)}", flush=True)
        candidates = kept

    candidates.sort(key=lambda c: (-c["score"], c["code"]))
    top = candidates[:top_n]

    def _fmt(c: Dict[str, float]) -> Dict:
        return {
            "code": c["code"], "name": c.get("name", ""), "market": c["market"],
            "score": round(c["score"], 6),
            "ret20": round(c["ret20"], 6), "vol20": round(c["vol20"], 6),
            "amihud20": round(c["amihud20"], 10), "loga20": round(c["loga20"], 6),
            "maxret20": round(c["maxret20"], 6), "liq20": round(c["liq20"], 0),
        }

    result = {
        "as_of": as_of,
        "source": vipdoc,
        "universe": {"stocks_found": len(stocks), "scored": len(candidates),
                     "st_removed": st_removed, "top_n": top_n},
        "top": [_fmt(c) for c in top],
        "runtime_sec": round(time.time() - t0, 1),
        "disclaimer": ("五因子为统计特征，非收益承诺；"
                       + ("价格为前复权（基于通达信权息事件）" if events
                          else "TDX 原生价为不复权，ret20 含除权跳空污染，建议加 --events-cache")
                       + "；本输出仅供研究观察，不构成投资建议。"),
    }

    # 打印
    print(f"\n[2/3] 五因子 Top {top_n}（截止 {as_of}）：")
    for i, c in enumerate(top, 1):
        nm = f" {c['name']}" if c["name"] else ""
        print(f"  {i:2d}. {c['code']}{nm:8s}  得分 {c['score']:.4f}  "
              f"ret20 {c['ret20']:+.2%}  20日均额 {c['liq20']/1e8:.1f}亿")
    print("\n[3/3] 声明：", result["disclaimer"])

    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(f"已写入: {out}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="五因子日度选股 · 原生 TDX 数据")
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--exclude-ret20-top", type=float, default=0.0)
    ap.add_argument("--names", default="")
    ap.add_argument("--events-cache", default="",
                    help="gbbq 权息缓存 CSV（提供则启用前复权），"
                         "用 tdx_native.gbbq_reader --build 生成")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    run(args.vipdoc, top_n=args.top, exclude_ret20_top=args.exclude_ret20_top,
        names_csv=args.names, out=args.out, events_cache=args.events_cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
