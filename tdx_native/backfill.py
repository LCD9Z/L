# -*- coding: utf-8 -*-
"""跟踪记录回填（L3 校准闭环）：用真实 .day 收盘价回填 tracking.csv 的 T+5/T+20。

口径（与冻结回测完全一致，见 STEP1_3_EXECUTION_REPORT.md 默认执行配置）：
- 建仓：推荐日（as_of）次一交易日开盘价（T+1 open，信号日收盘后下单）
- T+5 / T+20：as_of 之后第 5 / 20 个交易日的收盘价（as_of 当日为第 0 日）
- 交易日历：上证指数 sh000001 的 .day（与全市场 IC 研究同源）
- 停牌处理：个股目标日无 bar 时取**不晚于**目标日的最后一根收盘；
  建仓日无 bar 时顺延至下一有 bar 日；建仓后再无 bar 则记 suspended
- 基准：**全市场等权**同期（T+1 open → T+k close）收益，作为主参照。
  另附上证指数作附加参照。**必须用等权而非指数**——指数由大市值权重股主导，
  而本选股池系统性偏中小盘（`loga20` 方向 −1），口径不同可能得出相反结论。

  ⚠️ **该修正的实证证据不足，结论待重验**（2026-10-02 审计发现）：
  当时记录的「指数口径 −2.13% vs 等权口径 +3.06%，结论直接相反」来自
  ``reports/daily/_smoke_filled.csv`` 的**3 行冒烟夹具**（浦发/平安/宁德，
  score 为手写 0.9/0.88/0.87），不是真实选股输出；而 ``_ew_ret()`` 要求
  有效样本 ≥100 只才返回值，这 3 行不满足门槛。
  真实 ``tracking_filled.csv`` 至今**未产生过一个等权基准数字**。
  → 在真实 filled 样本 ≥20 个之前，**禁止引用 −2.13% / +3.06%**。
  → 届时的正确对比：推荐池收益 vs 等权基准 vs 上证指数，三者同列。
- 幂等：tracking.csv 只追加不修改（append-only 纪律）；本脚本每次
  **全量重算**产出独立的 tracking_filled.csv，源数据只增不减，
  重跑即得最新状态，无状态污染。

用法::

    python -m tdx_native.backfill --vipdoc D:/new_tdx/vipdoc \
        --tracking reports/daily/tracking.csv \
        --out reports/daily/tracking_filled.csv
"""
from __future__ import annotations

import argparse
import csv
import os
from typing import Any, Dict, List, Optional, Tuple

from . import day_reader

INDEX_CODE = "sh000001"


def _load_calendar(vipdoc: str) -> List[str]:
    idx_path = os.path.join(vipdoc, "sh", "lday", f"{INDEX_CODE}.day")
    bars = day_reader.read_day_all(idx_path)
    return [b["date"] for b in bars]


def _price_at(bars_by_date: Dict[str, dict], date: str,
              field: str = "close") -> Optional[float]:
    b = bars_by_date.get(date)
    return float(b[field]) if b and b.get(field) else None


def _last_close_before(bars_by_date: Dict[str, dict], date: str, after: str = "",
                       with_date: bool = False):
    """不晚于 date（且晚于 after）的最后一根收盘。

    ``with_date=True`` 时返回 ``(date, close)``，供顺延场景回写真实成交日
    （否则调用方拿不到日期，会让到期卖出提示漏报，见 ``_ret_at``）。
    """
    best = None
    for d, b in bars_by_date.items():
        if d <= date and float(b.get("close") or 0) > 0:
            if after and d <= after:
                continue
            if best is None or d > best[0]:
                best = (d, float(b["close"]))
    if best is None:
        return None
    return (best[0], best[1]) if with_date else best[1]


def _ret_at(cal: List[str], bars: Dict[str, Dict[str, Any]], i: int, k: int,
            entry_date: str, entry_open: float
            ) -> Optional[Tuple[Optional[str], Optional[float],
                                Optional[float], Optional[int]]]:
    """信号日 ``i`` 起第 ``k`` 个交易日的 ``(date, close, ret, k)``。

    三态返回：

    - ``None`` —— 尚未到期（主日历长度不足 ``i + k``）
    - ``("pending", None, None, None)`` —— 已到期，但个股在目标日无 bar，
      且回溯不到任何有效收盘（通常为长期停牌）
    - ``(date, close, ret, k)`` —— 正常；``k`` 为 ``None`` 表示目标是「用不晚于
      目标日的最后一根收盘」**顺延**（目标日停牌），此时 ``date`` 回传**实际使用
      的那一根**的日期（不得为 ``None``：否则 ``tracking_filled.csv`` 的
      ``t20_date`` 落空，``run_daily._due_exits`` 会静默跳过，持仓永不提示卖出）

    提取为模块级函数（原为循环内闭包）：显式接收全部依赖，消除闭包捕获
    循环变量的 B023 隐患，并使其可被单元测试直接覆盖。
    """
    if i + k >= len(cal):
        return None
    dk = cal[i + k]
    c = _price_at(bars, dk, "close")
    if c is None:
        got = _last_close_before(bars, dk, after=entry_date, with_date=True)
        if got is None:
            return ("pending", None, None, None)
        used_date, c = got
        return (used_date, c, c / entry_open - 1, None)
    return (dk, c, c / entry_open - 1, k)


def _ew_ret(cal: List[str], cal_pos: Dict[str, int], as_of: str, k: int,
            path_map: Dict[str, str],
            cache: Dict[str, Dict[str, dict]]) -> Optional[float]:
    """**全市场等权**基准收益（as_of 后 T+1 开盘 → T+k 收盘）。

    为什么不用指数：指数（如上证）由大市值权重股主导，而本选股池系统性
    偏中小盘（``loga20`` 规模因子方向为 −1）。用指数衡量会**系统性错估超额**，
    而跟踪校准正是要拿它来判断推荐质量，口径错了整个闭环就偏了。

    停牌/缺数据的标的自动跳过（等权即"每个可交易标的同权"）；
    有效样本 < 100 只时返回 None（不足以免偏）。
    """
    i = cal_pos.get(as_of)
    if i is None or i + k >= len(cal) or i + 1 >= len(cal):
        return None
    d1, dk = cal[i + 1], cal[i + k]
    rets: List[float] = []
    for code, p in path_map.items():
        bars = cache.get(code)
        if bars is None:
            bars = {b["date"]: b for b in day_reader.read_day_tail(p, 260)}
            cache[code] = bars
        o = _price_at(bars, d1, "open")
        c = _price_at(bars, dk, "close")
        if o and c and o > 0:
            rets.append(c / o - 1)
    if len(rets) < 100:
        return None
    return sum(rets) / len(rets)


def run(vipdoc: str, tracking_csv: str, out_csv: str) -> Dict:
    cal = _load_calendar(vipdoc)
    cal_pos = {d: i for i, d in enumerate(cal)}
    idx_path = os.path.join(vipdoc, "sh", "lday", f"{INDEX_CODE}.day")
    idx_bars = {b["date"]: b for b in day_reader.read_day_all(idx_path)}

    with open(tracking_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"读入跟踪记录 {len(rows)} 行（{tracking_csv}）")

    # 个股路径映射（一次扫描）
    paths = {c: p for c, m, p in day_reader.scan_paths(vipdoc)}

    # 指数同期收益（按 as_of）
    def idx_ret(as_of: str, k: int) -> Optional[float]:
        i = cal_pos.get(as_of)
        if i is None or i + k >= len(cal) or i + 1 >= len(cal):
            return None
        d1, dk = cal[i + 1], cal[i + k]
        o = _price_at(idx_bars, d1, "open")
        c = _price_at(idx_bars, dk, "close")
        if not o or not c:
            return None
        return c / o - 1

    out_rows: List[Dict[str, Any]] = []
    stats = {"pending": 0, "suspended": 0, "filled_t20": 0, "filled_t5": 0,
             "skipped": 0}
    cache: Dict[str, Dict[str, dict]] = {}

    for r in rows:
        as_of = str(r["as_of"]).strip()
        code = str(r["code"]).strip()
        i = cal_pos.get(as_of)
        if i is None:
            stats["skipped"] += 1
            out_rows.append({**r, "status": "as_of_not_in_calendar"})
            continue

        if code not in cache:
            p = paths.get(code)
            # 全量读取：历史 tracking 行的目标日可能远在最近 120 根之外
            tail = day_reader.read_day_all(p) if p else []
            cache[code] = {b["date"]: b for b in tail}
        bars = cache[code]

        # 建仓：T+1 开盘，停牌则顺延（最多 5 个交易日）
        # 日历尚未更新到建仓日（as_of 即日历最后一根）→ 整行 pending
        entry_date: Optional[str] = None
        entry_open: Optional[float] = None
        if i + 1 >= len(cal):
            stats["pending"] += 1
            out_rows.append({**r, "status": "pending",
                             "t5_status": "not_due", "t20_status": "not_due"})
            continue
        for j in range(i + 1, min(i + 6, len(cal))):
            op = _price_at(bars, cal[j], "open")
            if op:
                entry_date, entry_open = cal[j], op
                break
        if entry_open is None or entry_date is None:
            stats["suspended"] += 1
            out_rows.append({**r, "status": "suspended"})
            continue

        # 上面已收窄为 (str, float)；显式绑定后传入模块级函数，
        # 既消除循环内闭包的 B023 隐患，也让该逻辑可被单元测试直接覆盖。
        t5 = _ret_at(cal, bars, i, 5, entry_date, entry_open)
        t20 = _ret_at(cal, bars, i, 20, entry_date, entry_open)

        row = {**r,
               "t1_date": entry_date, "t1_open": f"{entry_open:.4f}"}
        # T+5
        if t5 is None:
            row.update({"t5_status": "not_due"})
        elif t5[0] == "pending":
            row.update({"t5_status": "pending_no_bar"})
        else:
            row.update({"t5_date": t5[0], "t5_close": f"{t5[1]:.4f}",
                        "t5_ret": f"{t5[2]:.6f}",
                        "t5_status": "filled"})
            stats["filled_t5"] += 1
        # T+20
        if t20 is None:
            row.update({"t20_status": "not_due", "status": "pending"})
            stats["pending"] += 1
        elif t20[0] == "pending":
            row.update({"t20_status": "pending_no_bar", "status": "pending"})
            stats["pending"] += 1
        else:
            row.update({"t20_date": t20[0], "t20_close": f"{t20[1]:.4f}",
                        "t20_ret": f"{t20[2]:.6f}",
                        "t20_status": "filled", "status": "filled"})
            stats["filled_t20"] += 1
        out_rows.append(row)

    # 汇总统计
    def _summarize(key: str):
        rets = [float(o[key]) for o in out_rows if o.get(key)]
        if not rets:
            return None
        rets.sort()
        n = len(rets)
        # 偶数样本取中位数须取中间两数均值（曾误写 rets[n // 2]，
        # n=4 时返回 3.0 而非 2.5；小样本阶段偏差最大）
        median = (rets[(n - 1) // 2] + rets[n // 2]) / 2
        return {"n": n, "mean": sum(rets) / n,
                "median": median,
                "win": sum(1 for x in rets if x > 0) / n}

    t5s, t20s = _summarize("t5_ret"), _summarize("t20_ret")
    summary = {"records": len(rows), **stats,
               "t5": t5s, "t20": t20s}

    # 参照基准（按已 filled 的 as_of 去重）
    # 主参照 = 全市场等权（与选股池的中小盘倾向同口径）；
    # 附加参照 = 上证指数（便于与公开行情对照）
    filled_asofs = sorted({o["as_of"] for o in out_rows
                           if o.get("t20_ret") and o["as_of"] in cal_pos})
    if filled_asofs:
        # 一次性读入覆盖最老 as_of 所需的尾部长度，多个 as_of 复用
        oldest = min(cal_pos[a] for a in filled_asofs)
        need = max(60, min(len(cal) - oldest + 25, 1500))
        ew_cache: Dict[str, Dict[str, dict]] = {}
        for code, p in paths.items():
            b = day_reader.read_day_tail(p, need)
            if b:
                ew_cache[code] = {y["date"]: y for y in b}
        ew_ref: Dict[str, float] = {}
        for a in filled_asofs:
            v = _ew_ret(cal, cal_pos, a, 20, paths, ew_cache)
            if v is not None:
                ew_ref[a] = v
        if ew_ref:
            summary["ew_t20_mean"] = sum(ew_ref.values()) / len(ew_ref)

    idx_ref: Dict[str, float] = {}
    for orow in out_rows:
        if orow.get("t20_ret"):
            ir = idx_ret(orow["as_of"], 20)
            if ir is not None:
                idx_ref.setdefault(orow["as_of"], ir)
    if idx_ref:
        summary["index_t20_mean"] = sum(idx_ref.values()) / len(idx_ref)

    # 写出
    fieldnames: List[str] = []
    for orow in out_rows:
        for k in orow:
            if k not in fieldnames:
                fieldnames.append(k)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    print(f"写出 {out_csv}")
    print(f"状态：filled_t20={stats['filled_t20']} "
          f"filled_t5={stats['filled_t5']} pending={stats['pending']} "
          f"suspended={stats['suspended']} skipped={stats['skipped']}")
    for key, tag in (("t5", "T+5"), ("t20", "T+20")):
        s = summary.get(key)
        if s:
            print(f"{tag}: n={s['n']} 均值={s['mean']:+.2%} "
                  f"中位={s['median']:+.2%} 胜率={s['win']:.0%}")
    if "ew_t20_mean" in summary:
        print(f"全市场等权同期 T+20 均值：{summary['ew_t20_mean']:+.2%}（主参照）")
        if summary.get("t20"):
            print(f"  推荐池 − 等权基准 = "
                  f"{summary['t20']['mean'] - summary['ew_t20_mean']:+.2%}"
                  "  ← 跟踪校准的核心指标")
    if "index_t20_mean" in summary:
        print(f"上证指数同期 T+20 均值：{summary['index_t20_mean']:+.2%}（附加参照）")
    if "ew_t20_mean" not in summary and "index_t20_mean" not in summary:
        print("暂无到期样本——推荐记录会随每日运行积累，到期后自动回填。")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="跟踪回填（L3 校准）")
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--tracking", default="reports/daily/tracking.csv")
    ap.add_argument("--out", default="reports/daily/tracking_filled.csv")
    args = ap.parse_args()
    run(args.vipdoc, args.tracking, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
