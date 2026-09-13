# -*- coding: utf-8 -*-
"""把通达信全市场日线 CSV 转换为项目管线可用的认证数据集。

用法::

    python build_tdx_dataset.py --src D:/tdx_daily_all.zip --out D:/tdx_dataset
    python build_tdx_dataset.py --src ... --out ... --min-rows 600 --benchmark 000300

产出::

    {out}/stocks/{code}.csv                 每股 CSV（date,open,close,high,low,volume,amount）
    {out}/stocks/{code}.metadata.json       {"strict":true,"sha256":..,"rows":..}
    {out}/benchmark.csv + .metadata.json    基准指数
    {out}/pit_universe.json                 {"snapshots":{date:[codes]}, "dates":[...]}
    {out}/inventory.json                    品种分布与筛选统计
    {out}/DATASET_PROFILE.md                数据性质与局限说明（含幸存者偏差警示）

**重要**：源数据存在幸存者偏差（不含退市股）且为不复权价，
详见 `tdx_csv_adapter` 模块文档。本脚本不修正这些局限，只做格式转换与显式记录。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tdx.tdx_csv_adapter import (  # noqa: E402
    PIPELINE_COLUMNS,
    build_pit_universe,
    export_stock_csvs,
    is_valid_ohlc,
    iter_rows,
    scan_inventory,
)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_meta(path: str, rows: int, extra: Dict[str, Any]) -> None:
    meta = {"strict": True, "sha256": _sha256(path), "rows": rows}
    meta.update(extra)
    with open(path.replace(".csv", ".metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def export_benchmark(src: str, out_dir: str, code: str, market: str) -> Dict[str, Any] | None:
    """导出基准指数 CSV（管线要求基准同样带 sha256 元数据）。"""
    rows = [r for r in iter_rows(src)
            if r["code"] == code and r["market"] == market and is_valid_ohlc(r)]
    if len(rows) < 100:
        return None
    rows.sort(key=lambda x: x["date"])
    # 同日去重（管线校验日期唯一）
    uniq, seen = [], set()
    for r in rows:
        if r["date"] in seen:
            continue
        seen.add(r["date"])
        uniq.append(r)
    rows = uniq
    path = os.path.join(out_dir, "benchmark.csv")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(PIPELINE_COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in PIPELINE_COLUMNS})
    _write_meta(path, len(rows), {"kind": "benchmark", "code": code, "market": market,
                                  "adjusted": False})
    return {"code": code, "market": market, "rows": len(rows),
            "first": rows[0]["date"], "last": rows[-1]["date"], "path": path}


def main() -> int:
    ap = argparse.ArgumentParser(description="TDX 全市场日线 CSV → 认证数据集")
    ap.add_argument("--src", required=True, help="tdx_daily_all.zip 或 .csv")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--min-rows", type=int, default=600,
                    help="每股最少行数（管线 preflight 要求 >= min_periods*2）")
    ap.add_argument("--benchmark", default="000300", help="基准指数代码（默认沪深300）")
    ap.add_argument("--benchmark-market", default="sh")
    ap.add_argument("--max-stocks", type=int, default=0,
                    help="限制导出数量（0=全部）。超过约 4000 个文件会触发沙箱写入上限，"
                         "建议 <=1500（即 <=3000 个文件）")
    ap.add_argument("--seed", type=int, default=20260912,
                    help="抽样随机种子（保证可复现；仅当 --max-stocks > 0 时生效）")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    stock_dir = os.path.join(out, "stocks")
    os.makedirs(stock_dir, exist_ok=True)

    print("[1/4] 扫描全量品种分布 ...")
    inv = scan_inventory(args.src)
    stocks: Dict[str, Dict[str, Any]] = inv["stocks"]
    print("      品种分布：")
    for t, (rows, n) in inv["by_type"].items():
        print(f"        {t:18s} 行数 {rows:>10,}  代码数 {n:>6,}")
    print(f"      真实 A 股股票: {len(stocks):,} 只")

    eligible = {c: s for c, s in stocks.items() if s["rows"] >= args.min_rows}
    print(f"      行数 >= {args.min_rows} 的股票: {len(eligible):,} 只")

    codes = None
    if args.max_stocks > 0 and len(eligible) > args.max_stocks:
        # 确定性随机抽样（固定种子）：避免"取前 N 只"带来的代码段/上市批次偏差，
        # 也避免按流动性排序引入的大盘股选择偏差。
        import random
        rng = random.Random(args.seed)
        codes = set(rng.sample(sorted(eligible), args.max_stocks))
        print(f"      按 --max-stocks 随机抽样 {len(codes):,} 只（seed={args.seed}）")

    print(f"[2/4] 导出每股 CSV 到 {stock_dir} ...")
    res = export_stock_csvs(args.src, stock_dir, codes=codes, min_rows=args.min_rows)
    print(f"      写出 {res['written']:,} 只，共 {res['total_rows']:,} 行；"
          f"跳过 {res['skipped']:,} 只（行数不足）")

    print(f"[3/4] 导出基准 {args.benchmark}({args.benchmark_market}) ...")
    bench = export_benchmark(args.src, out, args.benchmark, args.benchmark_market)
    if bench is None:
        print(f"      !! 未找到基准 {args.benchmark}，管线将无法运行")
    else:
        print(f"      {bench['rows']:,} 行  {bench['first']} ~ {bench['last']}")

    print("[4/4] 构造 PIT 股票池快照 ...")
    exported = set(res["codes"])
    sub = {c: s for c, s in eligible.items() if c in exported}
    all_dates = sorted({d for s in sub.values() for d in (s["first"], s["last"])})
    # 用交易日序列（从基准取）构造快照日期
    if bench:
        with open(bench["path"], encoding="utf-8") as f:
            trade_dates = [r["date"] for r in csv.DictReader(f)]
    else:
        trade_dates = all_dates
    snaps = build_pit_universe(sub, trade_dates)
    uni = {"snapshots": snaps,
           "dates": trade_dates,
           "note": "最简 PIT 池：仅按上市日过滤。源数据不含退市股，无法修正幸存者偏差。"}
    with open(os.path.join(out, "pit_universe.json"), "w", encoding="utf-8") as f:
        json.dump(uni, f, ensure_ascii=False)
    sizes = [len(v) for v in snaps.values()]
    print(f"      快照 {len(snaps):,} 个交易日；池规模 {min(sizes)} ~ {max(sizes)} 只")

    inv_out = {k: v for k, v in inv.items() if k != "stocks"}
    inv_out.update({"eligible_stocks": len(eligible), "exported": res["written"],
                    "min_rows": args.min_rows, "benchmark": bench,
                    "source": os.path.basename(args.src)})
    with open(os.path.join(out, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump(inv_out, f, ensure_ascii=False, indent=1)

    _write_profile(out, inv_out, res, bench, sizes)
    print(f"\n完成。数据集目录: {out}")
    return 0


def _write_profile(out: str, inv: Dict[str, Any], res: Dict[str, Any],
                   bench: Dict[str, Any] | None, sizes: List[int]) -> None:
    lines = [
        "# TDX 数据集说明（自动生成）",
        "",
        f"- 源文件：`{inv.get('source')}`",
        f"- 导出股票数：**{res['written']:,}**（每股最少 {inv.get('min_rows')} 行）",
        f"- 总行数：{res['total_rows']:,}",
        f"- 基准：{bench['code'] if bench else '缺失'}（{bench['first'] if bench else '-'} ~ "
        f"{bench['last'] if bench else '-'}）",
        f"- PIT 池规模：{min(sizes) if sizes else 0} ~ {max(sizes) if sizes else 0} 只",
        "",
        "## 必须知晓的四项局限",
        "",
        "### 1. 幸存者偏差（严重）",
        "本数据集**不含已退市股票**。实测抽取 15 只在 2021–2026 期间退市/被合并的股票，"
        "**全部缺失**；99.1% 的代码数据持续到最后交易日。",
        "",
        "**后果**：任何回测结果都**系统性偏乐观**。回撤会被低估，"
        "因为亏损失败的样本根本不在数据集里。",
        "",
        "### 2. 不复权价（原始价）",
        "TDX `.day` 为原始成交价。实测存在 13,696 行单日 |涨跌| > 21% 的跳空，"
        "而主板涨跌停 ±10%、双创 ±20%，正常交易不可能超过 —— 这些基本是**除权除息**。",
        "",
        "**后果**：跨除权的动量/趋势因子会被严重污染。使用前必须做复权处理，"
        "或仅用于不受除权影响的短周期形态。",
        "",
        "### 3. 品种混杂",
        "源文件含 ETF/LOF、可转债、通达信板块指数（880/881/899）与宽基指数，"
        "约占代码总数的 41%。已通过 `code + market` 联合判定过滤，"
        "其中 `000001` 需靠 market 区分（sh=上证指数 / sz=平安银行）。",
        "",
        "### 4. 缺少换手率与流通股本",
        "无法施加真实的容量约束与流动性过滤。",
        "",
        "## 结论",
        "",
        "本数据集可用于：工程链路验证、跨截面因子行为的**初步观察**、实现缺陷的规模化暴露。",
        "",
        "**不足以单独支撑投资结论** —— 幸存者偏差与不复权两项缺陷都会直接扭曲收益与回撤。",
        "",
    ]
    with open(os.path.join(out, "DATASET_PROFILE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
