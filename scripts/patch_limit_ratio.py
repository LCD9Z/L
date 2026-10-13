# -*- coding: utf-8 -*-
r"""把已构建数据集里的 ``limit_ratio`` 按 **PIT 正确规则**重算并回写。

## 为什么需要单独打补丁

``exchange_rules.derive_limit_ratio`` 曾对创业板**无条件返回 0.20**，
把 2020-08-24 起才生效的 ±20% 追溯到了 2016 年。代码已修，
但**个股 CSV 里是逐行存了 ``limit_ratio`` 字段的** ——
``exchange_rules.limit_ratio(code, bar)`` 会**优先采用存储值**，
因此**光修代码不影响已有数据**，必须回写。

量化（v3，2026-09-25 实测）：创业板 2,121,218 行中 **738,070 行（34.8%）**
涨跌幅被高估，涉及 834 只。

## 后果不是"近似"而是**偏乐观**

该期间 10% 涨停的「一字板」不会被「涨跌停不可买」检查拦住
（10% < 20% 阈值），回测因而多吃了本不可成交的成交。

## 审计链

``professional_audit`` 会校验 ``metadata.sha256`` 与文件内容一致，
故回写后**必须重算 sha256**，否则整个数据集会被判为 ``sha256_mismatch``。

## 用法

::

    python scripts/patch_limit_ratio.py --dataset D:/tdx_dataset_v3            # 试算
    python scripts/patch_limit_ratio.py --dataset D:/tdx_dataset_v3 --apply    # 落盘
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange_rules import derive_limit_ratio, is_st_flag  # noqa: E402
from pit.pit_snapshot_store import sha256_of_file as _sha256  # noqa: E402,F401 — P4 收敛（审计 4.2）


def _fmt(value: float) -> str:
    """与构建脚本一致的字符串化：0.1 / 0.05 / 0.2，不写 0.100000。"""
    return f"{value:g}"


def patch_stock(csv_path: str, meta_path: str, *, apply: bool) -> Tuple[int, Dict[str, int]]:
    """返回 ``(改动行数, {新值: 次数})``。"""
    code = os.path.basename(csv_path)[:-4]
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields: List[str] = list(reader.fieldnames or [])
        rows: List[Dict[str, str]] = list(reader)

    if "limit_ratio" not in fields or not rows:
        return 0, {}

    changed = 0
    tally: Dict[str, int] = {}
    for r in rows:
        date = r.get("date") or ""
        is_st = is_st_flag(r.get("is_st"))
        want, _basis = derive_limit_ratio(code, is_st=is_st, trade_date=date)
        want_s = _fmt(want)
        have = (r.get("limit_ratio") or "").strip()
        # 数值比较而非字符串比较：构建脚本可能写成 "0.10" 而这里是 "0.1"
        try:
            same = abs(float(have) - want) < 1e-9
        except (TypeError, ValueError):
            same = False
        if same:
            continue
        changed += 1
        tally[want_s] = tally.get(want_s, 0) + 1
        r["limit_ratio"] = want_s
        r["limit_basis"] = "patched_pit"

    if changed and apply:
        tmp = csv_path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, csv_path)
        # 审计链：内容变了，sha256 必须同步
        if os.path.exists(meta_path):
            meta: Dict[str, Any] = json.loads(Path(meta_path).read_text(encoding="utf-8"))
            meta["sha256"] = _sha256(csv_path)
            meta["limit_ratio_patched"] = (
                "2026-09-25 修正创业板 PIT 违规：2020-08-24 前为 10%（ST 为 5%）"
            )
            Path(meta_path).write_text(
                json.dumps(meta, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8", newline="\n")
    return changed, tally


def main() -> int:
    ap = argparse.ArgumentParser(description="按 PIT 正确规则重算并回写 limit_ratio")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--apply", action="store_true",
                    help="真正落盘（默认只试算，不写任何文件）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只（调试用）")
    args = ap.parse_args()

    stock_dir = os.path.join(args.dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                   if f.endswith(".csv") and f[:-4].isdigit())
    if args.limit:
        codes = codes[:args.limit]

    print("=" * 92)
    print("limit_ratio PIT 修正" + ("（试算，不写盘）" if not args.apply else "（**落盘**）"))
    print("=" * 92)
    print(f"数据集 {args.dataset} | 股票 {len(codes):,} 只\n")

    t0 = time.time()
    total_rows = 0
    touched_files = 0
    tally: Dict[str, int] = {}
    for i, c in enumerate(codes, 1):
        csv_path = os.path.join(stock_dir, f"{c}.csv")
        meta_path = os.path.join(stock_dir, f"{c}.metadata.json")
        try:
            n, t = patch_stock(csv_path, meta_path, apply=args.apply)
        except (OSError, csv.Error) as exc:
            print(f"  [warn] {c} 处理失败: {exc!r}")
            continue
        if n:
            touched_files += 1
            total_rows += n
            for k, v in t.items():
                tally[k] = tally.get(k, 0) + v
        if i % 500 == 0:
            print(f"  ... {i}/{len(codes)}  已改 {total_rows:,} 行", flush=True)

    print(f"\n涉及文件 {touched_files:,} 只 | 改动行数 {total_rows:,}")
    print(f"新值分布: {dict(sorted(tally.items()))}")
    if not args.apply:
        print("\n⚠️ 试算模式 —— 未写任何文件。加 --apply 才落盘。")
    else:
        print("\n✅ 已落盘，并同步更新 metadata.sha256（保持审计链完整）。")
    print(f"用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
