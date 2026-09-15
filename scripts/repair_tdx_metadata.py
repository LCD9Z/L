# -*- coding: utf-8 -*-
"""为已导出的每股 CSV 重建 .metadata.json（修复用）。

背景：一次有缺陷的清理脚本用 `os.path.splitext` 解析文件名，
把 `600519.metadata.json` 解析成 `600519.metadata`，导致元数据被误删。
本脚本按 CSV 实际内容重算 sha256 与行数，重建元数据，不触碰 CSV。

用法::

    python repair_tdx_metadata.py --dataset D:/tdx_dataset
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_rows(path: str) -> int:
    with open(path, encoding="utf-8", newline="") as f:
        rd = csv.reader(f)
        next(rd, None)
        return sum(1 for _ in rd)


def main() -> int:
    ap = argparse.ArgumentParser(description="重建 TDX 数据集元数据")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--only-universe", action="store_true", default=True,
                    help="仅处理 PIT 池内的代码（默认开启）")
    args = ap.parse_args()

    d = os.path.abspath(args.dataset)
    stock_dir = os.path.join(d, "stocks")

    codes = None
    uni_path = os.path.join(d, "pit_universe.json")
    if args.only_universe and os.path.exists(uni_path):
        with open(uni_path, encoding="utf-8") as f:
            snaps = json.load(f)["snapshots"]
        codes = set()
        for v in snaps.values():
            codes.update(v)
        print(f"PIT 池代码数: {len(codes):,}")
    else:
        codes = {os.path.basename(f)[:-4] for f in os.listdir(stock_dir)
                 if f.endswith(".csv")}

    made, skipped = 0, 0
    for code in sorted(codes):
        csv_p = os.path.join(stock_dir, f"{code}.csv")
        meta_p = os.path.join(stock_dir, f"{code}.metadata.json")
        if not os.path.exists(csv_p):
            skipped += 1
            continue
        rows = _count_rows(csv_p)
        meta = {"strict": True, "sha256": _sha256(csv_p), "rows": rows,
                "code": code, "source": "tdx_daily_all.zip", "adjusted": False,
                "note": "TDX raw (unadjusted) daily bars; survivorship-biased universe"}
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        made += 1
        if made % 300 == 0:
            print(f"  已重建 {made} ...")

    print(f"完成：重建 {made} 个元数据，跳过 {skipped} 个（CSV 缺失）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
