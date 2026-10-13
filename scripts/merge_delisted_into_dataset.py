# -*- coding: utf-8 -*-
"""把窗口内退市股并入 TDX 认证数据集。

## 为什么

TDX 数据集完全缺失 180 只窗口内（2021-08 ~ 2026-09）退市的股票 →
幸存者偏差。已量化的影响：`ret_20` 的 |IC| 高估 27%，
反转策略的 Q1 买入区收益高估 86%。

本脚本把它们并入，使后续所有回测**默认包含**退市股。

## 产出

| 文件 | 说明 |
|------|------|
| `stocks/{code}.csv` | 列 = `date,open,close,high,low,volume,amount`，与既有数据集一致 |
| `stocks/{code}.metadata.json` | 含 sha256，供 `professional_audit` 校验 |
| `pit_universe.json` | **按实际交易区间**把退市股加入快照 |

## PIT 正确性（关键）

退市股**只能出现在其实际交易的日期**的快照里。
若把它加入全区间快照，回测会在其退市后仍尝试交易 —— 这是新的前视偏差。

## 成交额口径

退市股日线源（腾讯/新浪）**不含成交额**，以 `volume × close` 近似。
metadata 中标记 `amount_approximated: true`，供下游识别。

用法::

    python scripts/merge_delisted_into_dataset.py --dataset D:/tdx_dataset
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tdx.tdx_csv_adapter import PIPELINE_COLUMNS, is_valid_ohlc  # noqa: E402
from pit.pit_snapshot_store import sha256_of_file as _sha256  # noqa: E402,F401 — P4 收敛（审计 4.2）

_I_DATE, _I_OPEN, _I_CLOSE, _I_HIGH, _I_LOW, _I_VOL = 0, 1, 2, 3, 4, 5


def klines_to_rows(rows: List[List[Any]]) -> List[Dict[str, Any]]:
    """K 线行 → 管线行字典（成交额为 ``volume × close`` 近似）。"""
    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            d = str(r[_I_DATE])
            o, c = float(r[_I_OPEN]), float(r[_I_CLOSE])
            h, low = float(r[_I_HIGH]), float(r[_I_LOW])
            v = float(r[_I_VOL])
        except (IndexError, TypeError, ValueError):
            continue
        out.append({"date": d, "open": o, "close": c, "high": h, "low": low,
                    "volume": v, "amount": v * c})
    out.sort(key=lambda b: b["date"])
    # 去重 (code, date) —— 管线会校验日期唯一
    seen: Set[str] = set()
    uniq: List[Dict[str, Any]] = []
    for row in out:
        if row["date"] in seen:
            continue
        seen.add(row["date"])
        uniq.append(row)
    # 过滤 OHLC 不自洽的行
    return [row for row in uniq if is_valid_ohlc(row)]


def main() -> int:
    ap = argparse.ArgumentParser(description="把退市股并入 TDX 数据集")
    ap.add_argument("--dataset", default="D:/tdx_dataset")
    ap.add_argument("--min-rows", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    d = os.path.abspath(args.dataset)
    stocks = os.path.join(d, "stocks")
    kpath = os.path.join(d, "delisted_klines.json")
    upath = os.path.join(d, "pit_universe.json")

    print("=" * 88)
    print("把窗口内退市股并入 TDX 认证数据集")
    print("=" * 88)

    with open(kpath, encoding="utf-8") as f:
        raw: Dict[str, List[List[Any]]] = json.load(f)
    with open(upath, encoding="utf-8") as f:
        universe = json.load(f)
    snaps: Dict[str, List[str]] = universe["snapshots"]
    all_dates: List[str] = sorted(snaps)

    existing = {f[:-4] for f in os.listdir(stocks) if f.endswith(".csv")}
    print(f"\n  已有股票 {len(existing):,} 只 · 待并入 {len(raw):,} 只 · "
          f"快照 {len(all_dates):,} 个交易日")

    written = 0
    skipped_small = 0
    skipped_collide = 0
    spans: List[Tuple[str, str, str]] = []   # (code, first, last)

    for market_code, rows in sorted(raw.items()):
        if not rows:
            continue
        code = market_code[2:]
        if code in existing:
            skipped_collide += 1
            continue
        clean = klines_to_rows(rows)
        if len(clean) < args.min_rows:
            skipped_small += 1
            continue
        if not args.dry_run:
            path = os.path.join(stocks, f"{code}.csv")
            # 与既有数据集一致：csv 默认终止符 \r\n
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                w = csv.DictWriter(fh, fieldnames=list(PIPELINE_COLUMNS))
                w.writeheader()
                for r in clean:
                    w.writerow({k: r[k] for k in PIPELINE_COLUMNS})
            meta = {
                "strict": True,
                "sha256": _sha256(path),
                "rows": len(clean),
                "code": code,
                "source": "tencent/sina kline (qfq)",
                "adjusted": False,
                "amount_approximated": True,
                "delisted_in_window": True,
                "note": ("Delisted A-share recovered to correct survivorship bias; "
                         "amount approximated as volume*close; third-party source"),
            }
            with open(os.path.join(stocks, f"{code}.metadata.json"), "w",
                      encoding="utf-8", newline="\n") as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=1)
        written += 1
        spans.append((code, clean[0]["date"], clean[-1]["date"]))

    print(f"\n  写入 {written} 只 · 行数不足跳过 {skipped_small} · 代码冲突跳过 {skipped_collide}")

    # ---- 更新 PIT 快照：只在退市股实际交易的日期加入 ----
    print("\n  更新 PIT 快照（按实际交易区间）...")
    added_total = 0
    for code, first, last in spans:
        for day in all_dates:
            if first <= day <= last:
                if code not in snaps[day]:
                    snaps[day].append(code)
                    added_total += 1
    print(f"  快照新增条目 {added_total:,} 条")
    if all_dates:
        print(f"  首日快照 {len(snaps[all_dates[0]])} 只 · "
              f"末日快照 {len(snaps[all_dates[-1]])} 只")

    universe["note"] = (str(universe.get("note", "")) +
                        " | 2026-09-14 并入 180 只窗口内退市股以修正幸存者偏差；"
                        "退市股仅在其实际交易区间内进入快照")

    if args.dry_run:
        print("\n  [dry-run] 未写盘")
        return 0

    with open(upath, "w", encoding="utf-8", newline="\n") as f:
        json.dump(universe, f, ensure_ascii=False)
    print(f"\n  已更新 {upath}")
    print("\n  提醒：退市股成交额为近似值（volume×close），")
    print("        依赖成交额的因子（amihud/log_amount/vol_ratio）需谨慎使用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
