# -*- coding: utf-8 -*-
"""通达信权息（gbbq）读取：解密缓存 + 零依赖消费。

`gbbq` 文件是 **3DES 加密**的（前 24 字节加密、后 5 字节明文，29 字节/条，
头部 4 字节为记录数）。解密依赖 pytdx 的密钥表，因此**只在建缓存时需要 pytdx**：

    # 建缓存（需 pytdx，用隔离环境的 python）
    python -m tdx_native.gbbq_reader --build --gbbq D:/new_tdx/T0002/hq_cache/gbbq \
        --out-cache data/gbbq_events.csv

产出 CSV（仅 category=1 除权除息）：code,date,cash,bonus,rights_price,rights_shares

之后 `load_events()` 用纯标准库读取缓存，主流程保持零第三方依赖。
"""
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, List, Tuple

# 事件字段（category=1 除权除息）：(date, 每股派息, 每股送转股, 配股价, 每股配股)
Event = Tuple[str, float, float, float, float]


def build_cache(gbbq_path: str, out_csv: str) -> int:
    """用 pytdx 解密 gbbq 并只保留除权除息事件，写 CSV。返回事件数。"""
    from pytdx.reader.gbbq_reader import GbbqReader
    print(f"[1/2] 解密 {gbbq_path}（约 1 分钟）...", flush=True)
    df = GbbqReader().get_df(gbbq_path)
    ex = df[df["category"] == 1]
    print(f"      总事件 {len(df)}，除权除息 {len(ex)}", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    n = 0
    with open(out_csv, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(["code", "date", "cash", "bonus", "rights_price", "rights_shares"])
        for _, r in ex.iterrows():
            # gbbq 单位：分红/送转/配股均为「每 10 股」，配股价为「元/股」
            w.writerow([str(r["code"]).zfill(6), str(int(r["datetime"])),
                        float(r["hongli_panqianliutong"]) / 10.0,
                        float(r["songgu_qianzongguben"]) / 10.0,
                        float(r["peigujia_qianzongguben"]),
                        float(r["peigu_houzongguben"]) / 10.0])
            n += 1
    print(f"[2/2] 已写入 {out_csv}（{n} 条）")
    return n


def load_events(cache_csv: str) -> Dict[str, List[Event]]:
    """读取缓存，返回 {code: [(date, cash_ps, bonus_ps, rights_price, rights_ps), ...]}（按日期升序）。"""
    events: Dict[str, List[Event]] = {}
    if not cache_csv or not os.path.exists(cache_csv):
        return events
    with open(cache_csv, encoding="utf-8", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            if i == 0:
                pass
            events.setdefault(r["code"].zfill(6), []).append(
                (r["date"], float(r["cash"]), float(r["bonus"]),
                 float(r["rights_price"]), float(r["rights_shares"])))
    for v in events.values():
        v.sort(key=lambda x: x[0])
    return events


def main() -> int:
    ap = argparse.ArgumentParser(description="gbbq 权息缓存构建")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--gbbq", default="D:/new_tdx/T0002/hq_cache/gbbq")
    ap.add_argument("--out-cache", default="data/gbbq_events.csv")
    args = ap.parse_args()
    if args.build:
        build_cache(args.gbbq, args.out_cache)
        return 0
    print("用法：--build --gbbq <路径> --out-cache <csv>")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
