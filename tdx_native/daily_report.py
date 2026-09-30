# -*- coding: utf-8 -*-
"""日度选股推荐报告（推荐系统定位下的产出件）。

定位（重要）：**这不是 alpha 策略信号，也不是投资建议**。五因子只是统计特征，
本项目已验证其在 2021-08~2026-09 无法产生可实现的超额收益。本报告的输出格式为
「透明、可解释、可跟踪校准」的候选清单：列出得分、因子明细与风险标签，
并落盘跟踪记录，供后续用真实行情做校准（L3 闭环）。

用法::

    python -m tdx_native.daily_report --vipdoc D:/new_tdx/vipdoc \
        --events-cache data/gbbq_events.csv --top 20 --exclude-ret20-top 0.20 \
        --out-dir reports/daily
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from typing import Dict, List

from . import day_reader
from . import screen


def _risk_flags(code: str, market: str, liq20: float, bars: List[dict]) -> List[str]:
    flags: List[str] = []
    lim = day_reader.limit_pct(code) - 0.002
    seg = bars[-21:]
    for k in range(1, len(seg)):
        p0 = float(seg[k - 1].get("close") or 0)
        p1 = float(seg[k].get("close") or 0)
        if p0 > 0 and p1 > 0 and abs(p1 / p0 - 1) > lim:
            flags.append("近期含涨跌停跳空")
            break
    if liq20 < 2e8:
        flags.append("流动性偏低(<2亿)")
    board = day_reader.board_of(code)
    if board == "bse":
        flags.append("北交所(30%涨跌停)")
    elif board in ("star", "chinext"):
        flags.append("双创(20%涨跌停)")
    return flags


def build_report(vipdoc: str, events_cache: str = "", names_csv: str = "",
                 top_n: int = 20, exclude_ret20_top: float = 0.0,
                 jump_filter: bool = False, out_dir: str = "reports/daily") -> Dict:
    res = screen.run(vipdoc, top_n=top_n, exclude_ret20_top=exclude_ret20_top,
                     names_csv=names_csv, events_cache=events_cache)
    as_of = res["as_of"]

    # 为入选标的补风险标签（只读这 N 只的尾部，成本极低）
    paths = {c: p for c, m, p in day_reader.scan_paths(vipdoc)}
    for item in res["top"]:
        p = paths.get(item["code"])
        bars = day_reader.read_day_tail(p, 40) if p else []
        if jump_filter and bars:
            lim = day_reader.limit_pct(item["code"]) - 0.002
            seg = bars[-21:]
            bad = any(
                float(seg[k - 1]["close"]) > 0
                and abs(float(seg[k]["close"]) / float(seg[k - 1]["close"]) - 1) > lim
                for k in range(1, len(seg)))
            if bad:
                item["excluded_by_jump"] = True
        item["risk_flags"] = _risk_flags(item["code"], item["market"],
                                         item["liq20"], bars)

    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"recommend_{as_of}.md")
    json_path = os.path.join(out_dir, f"recommend_{as_of}.json")
    track_path = os.path.join(out_dir, "tracking.csv")

    lines = [
        f"# 五因子选股候选清单 · {as_of}",
        "",
        "> **不构成投资建议。** 五因子为统计特征，本项目已验证其在 2021-08~2026-09",
        "> 不产生可实现的超额收益（详见 `STEP1_3_EXECUTION_REPORT.md`）。",
        "> 本清单仅作**可解释的候选与跟踪校准**用途。",
        "",
        f"- 股票池：{res['universe']['stocks_found']} 只 A 股，打分 {res['universe']['scored']} 只",
        f"- 剔除：ST {res['universe']['st_removed']} 只"
        + (f"，V1 尾部剔除 {exclude_ret20_top:.0%}" if exclude_ret20_top else ""),
        f"- 数据源：通达信原生 `.day`"
        + ("（前复权）" if events_cache else "（原始价）"),
        "",
        "| # | 代码 | 名称 | 得分 | ret20 | vol20 | maxret20 | 20日均额 | 风险标签 |",
        "|---|------|------|------|-------|-------|----------|---------|---------|",
    ]
    for i, t in enumerate(res["top"], 1):
        from .run_daily import _xueqiu_code  # 延迟导入避免循环
        xq = _xueqiu_code(t["code"])
        lines.append(
            f"| {i} | [{t['code']}](https://xueqiu.com/S/{xq}) | "
            f"{t.get('name') or '-'} | {t['score']:.4f} | "
            f"{t['ret20']:+.2%} | {t['vol20']:.4f} | {t['maxret20']:+.2%} | "
            f"{t['liq20'] / 1e8:.2f}亿 | {'；'.join(t.get('risk_flags') or ['-'])} |")
    lines += ["", "## 跟踪校准", "",
              "本清单已写入 `tracking.csv`。建议在 T+5 / T+20 用真实收盘价回填，",
              "统计分档胜率与收益分布，作为推荐质量的唯一度量。", ""]
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    payload = dict(res)
    payload["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    payload["jump_filter"] = jump_filter
    payload["md_path"] = md_path
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # 幂等登记：同一 as_of 的已登记代码不重复写入（重复运行只补新增）
    existing = set()
    if os.path.exists(track_path):
        with open(track_path, encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                if row and str(row[0]) == str(as_of):
                    existing.add(str(row[1]))
    new_rows = [t for t in res["top"] if t["code"] not in existing]
    new_file = not os.path.exists(track_path)
    with open(track_path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["as_of", "code", "name", "score", "liq20",
                        "ret20", "vol20", "maxret20", "risk_flags"])
        for t in new_rows:
            w.writerow([as_of, t["code"], t.get("name", ""), t["score"],
                        t["liq20"], t["ret20"], t["vol20"], t["maxret20"],
                        "|".join(t.get("risk_flags") or [])])
    skipped = len(res["top"]) - len(new_rows)
    if skipped:
        print(f"跟踪登记：{as_of} 已有 {skipped} 条，新增 {len(new_rows)} 条（幂等）")

    print(f"\n报告：{md_path}\n跟踪：{track_path}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="日度选股推荐报告")
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--events-cache", default="data/gbbq_events.csv")
    ap.add_argument("--names", default="")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--exclude-ret20-top", type=float, default=0.20)
    ap.add_argument("--jump-filter", action="store_true")
    ap.add_argument("--out-dir", default="reports/daily")
    args = ap.parse_args()
    build_report(args.vipdoc, events_cache=args.events_cache, names_csv=args.names,
                 top_n=args.top, exclude_ret20_top=args.exclude_ret20_top,
                 jump_filter=args.jump_filter, out_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
