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
import time
from typing import Any, Dict, List

from . import adjust
from . import day_reader
from . import five_factor
from . import gbbq_reader


# A 股当前约 5,600 只；低于此值几乎必然意味着 .day 下载不完整
MIN_UNIVERSE_STOCKS = 4800
# 至少这么多比例的标的数据要更新到最新交易日（停牌股自然落后，日常 <1%）
MIN_FRESH_RATIO = 0.85


def preflight(vipdoc: str) -> Dict[str, Any]:
    """数据完整性预检（**不写任何文件**）。

    为什么需要：若某日通达信只下载了部分 ``.day``，系统会**静默地**用残缺池
    选股，产出一份看起来完全正常的报告与跟踪记录——这正是本项目最警惕的
    「静默失效」。因此在写入任何产物之前先过这道闸门。

    检查两项：
    1. 股票池规模不得异常缩水（``MIN_UNIVERSE_STOCKS``）；
    2. 至少 ``MIN_FRESH_RATIO`` 比例的标的数据已更新到全池最新交易日
       （反映"下载是否跑完"，比只看文件数量可靠）。

    返回 ``{stocks_found, as_of, at_as_of, fresh_ratio, problems}``；
    ``problems`` 为空列表表示通过。
    """
    stocks = day_reader.scan_stocks(vipdoc)
    n = len(stocks)
    if n == 0:
        return {"stocks_found": 0, "as_of": "", "at_as_of": 0,
                "fresh_ratio": 0.0,
                "problems": ["未扫描到任何 A 股 .day 文件（路径是否正确？）"]}
    last_dates = [b[-1]["date"] for _, _, _, b in stocks]
    as_of = max(last_dates)
    at_as_of = sum(1 for d in last_dates if d == as_of)
    fresh = at_as_of / n
    problems: List[str] = []
    if n < MIN_UNIVERSE_STOCKS:
        problems.append(f"股票池仅 {n} 只（阈值 {MIN_UNIVERSE_STOCKS}）")
    if fresh < MIN_FRESH_RATIO:
        problems.append(
            f"仅 {fresh:.0%} 的标的数据更新到 {as_of}"
            f"（阈值 {MIN_FRESH_RATIO:.0%}，疑似下载未完成）")
    return {"stocks_found": n, "as_of": as_of, "at_as_of": at_as_of,
            "fresh_ratio": fresh, "problems": problems}


def run(vipdoc: str, top_n: int = 20, exclude_ret20_top: float = 0.0,
        names_csv: str = "", out: str = "", events_cache: str = "") -> Dict:
    t0 = time.time()
    names = day_reader.load_names(names_csv)
    events = gbbq_reader.load_events(events_cache) if events_cache else {}
    # 复权状态必须按**实际加载到的数据**判定，不能按路径字符串：
    # load_events 对缺失/空文件返回 {}，若用 `if events_cache` 会在权息缓存
    # 丢失时仍宣称"启用前复权"，而 ret20 实为含除权跳空的原始价，
    # 污染 tracking 校准基线（2026-10-02 审计）。
    if events_cache and not events:
        print(f"      ⚠️ 权息缓存未取到数据（{events_cache}）——实际按**原始价**计算，"
              f"ret20 含除权跳空污染，勿与历史前复权结果直接比较", flush=True)
    if events:
        print(f"      已载入权息事件 {sum(len(v) for v in events.values())} 条"
              f"（覆盖 {len(events)} 只）→ 启用前复权", flush=True)

    stocks = day_reader.scan_stocks(vipdoc)
    print(f"[1/3] 扫描到真实 A 股股票 {len(stocks)} 只", flush=True)

    # 统一截止日：全池最新交易日；停牌过久（落后 >10 **交易日**）的剔除。
    # 注意：必须用交易日计数，不能用 int(YYYYMMDD) 相减——那是日历日，
    # 跨月边界会把 7 个交易日的停牌算成 79 天（20261009-20260930），静默误杀。
    last_dates = [b[-1]["date"] for _, _, _, b in stocks]
    as_of = max(last_dates)
    # 全体出现过的交易日集合（升序），用于把"落后几个交易日"算准
    all_dates = sorted({bar["date"] for _, _, _, bars_ in stocks for bar in bars_})
    fresh = []
    stale = 0
    for code, market, path, bars in stocks:
        if bars[-1]["date"] < as_of:
            gap = len([d for d in all_dates if d > bars[-1]["date"]])
            if gap > 10:
                stale += 1
                continue
        bars = [b for b in bars if b["date"] <= as_of]
        fresh.append((code, market, path, bars))
    print(f"      截止日 {as_of}；剔除停牌超 10 个交易日后 {len(fresh)} 只"
          f"（剔除 {stale}）", flush=True)

    # ST 剔除（仅在有名称映射时可用）
    st_removed = 0
    names_missing = 0
    candidates: List[Dict[str, float]] = []
    adjusted_cnt = 0
    for code, market, _path, bars in fresh:
        nm = names.get(code, "")
        if not nm:
            # 无名称 → ST 判断短路，剔除失效。必须计数披露，不能静默
            names_missing += 1
        elif "ST" in nm.upper():
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
    print(f"      打分前 {len(candidates)} 只（ST 剔除 {st_removed} 只；"
          f"复权 {adjusted_cnt} 只）", flush=True)
    if names and names_missing:
        # 名称表覆盖不全 → 这部分标的的 ST 剔除静默失效，须显式告警
        miss_pct = names_missing / max(1, len(fresh))
        if miss_pct > 0.05:
            print(f"      ⚠️ 名称表缺 {names_missing} 只（{miss_pct:.1%}）——"
                  f"这些标的**未做 ST 剔除**（名称表 {names_csv or '未提供'}）",
                  flush=True)

    five_factor.composite_score(candidates)

    if exclude_ret20_top > 0:
        cut = 1.0 - exclude_ret20_top
        rr = five_factor.pct_rank([c["ret20"] for c in candidates])
        kept = [c for c, r in zip(candidates, rr, strict=True) if r <= cut]
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
        "qfq_applied": adjusted_cnt > 0,   # 实际复权过的标的数 > 0（下游据此判定）
        "universe": {"stocks_found": len(stocks), "scored": len(candidates),
                     "st_removed": st_removed, "top_n": top_n,
                     "qfq_adjusted": adjusted_cnt, "stale_removed": stale,
                     "names_missing": names_missing},
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
        # 变量名不与上面的因子 dict `f` 复用（复用会让类型推断崩塌）
        with open(out, "w", encoding="utf-8", newline="\n") as fp:
            json.dump(result, fp, ensure_ascii=False, indent=1)
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
