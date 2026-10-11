# -*- coding: utf-8 -*-
"""把退市股 CSV 转成通达信原生 `.day` 格式。

## 为什么需要

H-CD 读的是通达信二进制 `.day`（`tdx_native.day_reader`），
而 `fetch_delisted_klines.py` 系列产出的是 CSV。
**项目此前没有这个方向的转换器**（只有 `tdx_csv_adapter` 的反向导出）。

## 通达信 `.day` 格式（32 字节/条）

```
偏移  类型      字段
 0    uint32    date     YYYYMMDD
 4    uint32    open     价格 × 100
 8    uint32    high     价格 × 100
12    uint32    low      价格 × 100
16    uint32    close    价格 × 100
20    float32   amount   成交额（元）
24    uint32    volume   成交量（股）
28    uint32    reserved
```
struct 格式：`<IIIIIfII`（小端）

## 设计要点

- **不覆盖原数据**：输出到独立目录，`D:/new_tdx_vipdoc_dl/`
- **幂等**：已存在的 `.day` 默认跳过（`--overwrite` 可强制）
- **可校验**：转换后回读，核对条数与首末日期
- **断点续传**：逐只转换、逐只落盘，死机后重跑自动跳过

用法：
    python scripts/csv_to_tdx_day.py --src D:/dl_backfill/klines \\
        --out D:/new_tdx_vipdoc_dl
    python scripts/csv_to_tdx_day.py --src ... --out ... --overwrite
"""
from __future__ import annotations

import argparse
import csv
import os
import struct
import sys
from typing import Dict, List, Optional, Tuple

REC = struct.Struct("<IIIIIfII")
REC_SIZE = 32


def _to_dir(market: str, out_root: str) -> str:
    d = os.path.join(out_root, market, "lday")
    os.makedirs(d, exist_ok=True)
    return d


def csv_to_day(rows: List[Dict[str, str]], path: str) -> Tuple[int, str, str]:
    """把已排序的 CSV 行写入 `.day`。返回 (条数, 首日, 末日)。"""
    recs = bytearray()
    first = last = ""
    for r in rows:
        try:
            date = int(str(r["date"]).replace("-", "").strip())
            o = float(r["open"])
            h = float(r["high"])
            lo = float(r["low"])
            c = float(r["close"])
            vol = float(r.get("volume") or 0)
            amt = float(r.get("amount") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        if date <= 0 or c <= 0:
            continue
        recs += REC.pack(date, int(round(o * 100)), int(round(h * 100)),
                         int(round(lo * 100)), int(round(c * 100)),
                         float(amt), int(vol), 0)
        if not first:
            first = str(date)
        last = str(date)
    with open(path, "wb") as fh:
        fh.write(recs)
    return len(recs) // REC_SIZE, first, last


def read_day_span(path: str) -> Tuple[int, str, str]:
    """回读 `.day` 校验：条数 + 首末日期（与 day_reader 同格式）。"""
    raw = open(path, "rb").read()
    n = len(raw) // REC_SIZE
    if n == 0:
        return 0, "", ""
    d0 = REC.unpack_from(raw, 0)[0]
    dn = REC.unpack_from(raw, (n - 1) * REC_SIZE)[0]
    return n, str(d0), str(dn)


def main() -> int:
    ap = argparse.ArgumentParser(description="CSV → 通达信 .day")
    ap.add_argument("--src", required=True, help="CSV 目录")
    ap.add_argument("--out", required=True, help="输出根目录（会建 {sh,sz}/lday）")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--verify", action="store_true", default=True,
                    help="转换后回读校验（默认开）")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.src) if f.lower().endswith(".csv"))
    if not files:
        print(f"{args.src} 下没有 CSV"); return 2

    print(f"待转换 {len(files)} 个 CSV")
    ok = skip = fail = 0
    bad: List[str] = []
    for i, fn in enumerate(files, 1):
        stem = os.path.splitext(fn)[0]           # 形如 sh600806
        if len(stem) < 3 or stem[:2] not in ("sh", "sz", "bj"):
            bad.append(f"{fn}: 文件名无市场前缀"); fail += 1; continue
        market, code = stem[:2], stem[2:]
        dst = os.path.join(_to_dir(market, args.out), f"{market}{code}.day")
        if os.path.exists(dst) and not args.overwrite:
            skip += 1
            continue
        src = os.path.join(args.src, fn)
        try:
            with open(src, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            rows.sort(key=lambda r: str(r["date"]))
            n, first, last = csv_to_day(rows, dst)
            if args.verify:
                n2, f2, l2 = read_day_span(dst)
                if n2 != n or f2 != first or l2 != last:
                    bad.append(f"{fn}: 回读不一致 ({n}/{first}/{last} "
                               f"vs {n2}/{f2}/{l2})")
                    fail += 1
                    continue
            ok += 1
        except Exception as e:                    # noqa: BLE001
            bad.append(f"{fn}: {type(e).__name__}: {e}")
            fail += 1
        if i % 50 == 0:
            print(f"      {i}/{len(files)}  成功 {ok} 跳过 {skip} 失败 {fail}",
                  flush=True)

    print(f"\n完成：成功 {ok}  跳过(已存在) {skip}  失败 {fail}")
    if bad:
        print(f"\n失败样例（前 10/{len(bad)}）：")
        for b in bad[:10]:
            print("   ", b)
    return 0 if fail == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
