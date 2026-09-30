# -*- coding: utf-8 -*-
"""从认证数据集构建**等权全A基准**（PIT 股票池口径，零依赖）。

为什么要做：基线策略的选股池是全市场（含小票、双创、北交所），而既有超额收益
对标的是沪深300（大盘股指数）。因子研究已证明规模/流动性溢价强显著
（log_amount_20 IC -0.0676、t=-10.28）→ 组合系统性偏向小票。小票跌、大盘涨时，
负超额里混着**风格敞口**与**选股能力**两件事，必须分开。

口径（事前设定，不调参）：
- 成员：PIT 快照中当日已上市且未退市的标的（停牌不除名，但当日无行情则不参与当日收益）
- 权重：等权（全市场等权 A 股指数）
- 收益：当日有收益的成员的**算术平均日收益**（t-1 与 t 均有收盘价的标的）
- 基准序列：I_t = I_{t-1} × (1 + mean(r_t))，起点 100

输出：认证格式 CSV（date/open/high/low/close）+ metadata（strict + sha256），
可直接被 `load_certified_csv` 与 `run_tdx_rolling_eval --benchmark` 消费。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Set


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="构建等权全A基准（PIT 口径）")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v2")
    ap.add_argument("--out-name", default="benchmark_ew.csv")
    ap.add_argument("--start-level", type=float, default=100.0)
    args = ap.parse_args()
    t0 = time.time()
    ds = Path(args.dataset)
    stock_dir = ds / "stocks"
    uni_path = ds / "pit_universe.json"
    if not uni_path.exists():
        raise SystemExit(f"缺少 PIT 快照: {uni_path}")
    snapshots: Dict[str, List[str]] = json.loads(
        uni_path.read_text(encoding="utf-8"))["snapshots"]
    dates = sorted(snapshots)

    # 逐只读收盘价日期序列（内存只保留必要结构：date -> {code: close}）
    closes: Dict[str, Dict[str, float]] = {}
    codes = sorted(p.stem for p in stock_dir.glob("*.csv")
                   if (stock_dir / f"{p.stem}.metadata.json").exists())
    print(f"[1/3] 读取 {len(codes)} 只收盘价序列 ...", flush=True)
    for i, code in enumerate(codes, 1):
        if i % 300 == 0:
            print(f"      {i}/{len(codes)}", flush=True)
        with (stock_dir / f"{code}.csv").open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    c = float(r["close"])
                except (TypeError, ValueError):
                    continue
                if c > 0:
                    closes.setdefault(r["date"], {})[code] = c

    print("[2/3] 计算等权日收益 ...", flush=True)
    rows: List[List[str]] = []
    level = float(args.start_level)
    prev_close: Dict[str, float] = {}
    n_contrib: List[int] = []
    for d in dates:
        members: Set[str] = set(snapshots[d])
        cur = closes.get(d, {})
        if not prev_close or not cur:
            prev_close = {c: v for c, v in cur.items() if c in members}
            continue
        rets: List[float] = []
        # 循环变量不与上面的 `c = float(r["close"])` 复用（复用会让类型推断崩塌）
        for code_m, px in cur.items():
            if code_m not in members:
                continue
            p = prev_close.get(code_m)
            if p and p > 0:
                rets.append(px / p - 1.0)
        prev_close = {c: v for c, v in cur.items() if c in members}
        if len(rets) < 30:   # 成员太少不计算（数据缺口/极早期）
            continue
        mean_r = sum(rets) / len(rets)
        n_contrib.append(len(rets))
        level = level * (1.0 + mean_r)
        rows.append([d, f"{level:.6f}", f"{level:.6f}", f"{level:.6f}", f"{level:.6f}"])

    print("[3/3] 写认证基准 ...", flush=True)
    out = ds / args.out_name
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close"])
        w.writerows(rows)
    meta = {
        "strict": True,
        "sha256": sha256_file(out),
        "rows": len(rows),
        "kind": "benchmark",
        "code": "EW_ALL",
        "market": "all",
        "adjusted": True,
        "note": "等权全A基准（PIT 股票池口径，算术平均日收益，起点100）",
    }
    (ds / f"{args.out_name}.metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    avg = sum(n_contrib) / len(n_contrib) if n_contrib else 0
    print(f"    交易日 {len(rows)} 天（{rows[0][0]} ~ {rows[-1][0]}），"
          f"平均参与 {avg:.0f} 只/日")
    print(f"    终值 {level:.2f}，用时 {time.time()-t0:.0f}s")
    print(f"    已写入: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
