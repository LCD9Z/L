# -*- coding: utf-8 -*-
"""L3 回填收官核查（2026-10-13）：universe vs raw 差额代码的显式定性。

背景：11:09-14:16 的 resume 跑采集 2,367 只，落盘 2,086 只/3,999,734 行；
差额 281 只「查询成功但 0 行」——**不落在 raw 里 → --resume 永远重试、
且收官跑会因 min_rows=false-FAIL**。必须先逐只定性，不静默跳过。

本脚本做三件事（只读 + 少量 baostock 直查，不写任何数据层）：
  1. 流式扫 raw jsonl → 每 code 行数与集合（约 1.7 GB，内存只存 code→count）；
  2. 与 universe（D:/tdx_dataset_v3/stocks/*.csv）差减 → 零数据代码清单；
  3. 抽样（默认 12 只）直查 baostock 同窗口 + 检查本地 tdx csv，确认「源侧无数据」。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

RAW = Path("D:/pit_snapshots/raw/baostock/query_history_k_data_plus/2026-10-13.jsonl")
UNIVERSE = Path("D:/tdx_dataset_v3/stocks")
OUT = Path("D:/pit_snapshots/meta/l3_zero_data_codes_2026-10-13.txt")
START, END = "2016-01-01", "2026-10-13"
SAMPLE_N = 12


def scan_raw_codes(path: Path) -> Counter:
    """流式统计 raw 里每个 code 的行数（坏行跳过，与 read_raw_keys 同约定）。"""
    counts: Counter = Counter()
    n_lines = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n_lines += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = str(rec.get("code", "")).split(".")[-1]
            if code:
                counts[code] += 1
    print(f"[raw] {n_lines:,} 行 · {len(counts):,} 个 code", flush=True)
    return counts


def main() -> int:
    t0 = time.time()
    counts = scan_raw_codes(RAW)
    universe = sorted(p.stem for p in UNIVERSE.glob("*.csv") if p.stem.isdigit())
    print(f"[universe] {len(universe):,} 个 code", flush=True)

    raw_codes = set(counts)
    missing = [c for c in universe if c not in raw_codes]
    extra = sorted(raw_codes - set(universe))
    print(f"[diff] universe 有而 raw 无: {len(missing)} 只 · raw 有而 universe 无: {len(extra)} 只",
          flush=True)

    # 行数分布（sanity：每个 code 应只有一个连续块；0 行本就不落盘）
    print(f"[raw] 行数 min={min(counts.values())} max={max(counts.values())} · "
          f"恰为页长 2000 的 code: {sum(1 for n in counts.values() if n == 2000)} 只", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        fh.write(f"# L3 universe 中 baostock 同窗口零数据的代码（{START}~{END}）\n")
        fh.write(f"# 生成: 2026-10-13 收官核查 · universe {len(universe)} - raw {len(raw_codes)} "
                 f"= {len(missing)}\n")
        for c in missing:
            fh.write(c + "\n")
    print(f"[out] 零数据清单已写 {OUT}", flush=True)

    # ---- 抽样直查 baostock + 本地 tdx ----
    import baostock as bs

    lg = bs.login()
    print(f"[baostock] login: {lg.error_code} {lg.error_msg}", flush=True)
    sample = missing[:: max(1, len(missing) // SAMPLE_N)][:SAMPLE_N]
    print(f"[sample] 抽查 {len(sample)} 只: {sample}", flush=True)
    for code in sample:
        sym = ("sh." if code[0] in "69" else "sz." if code[0] in "023" else "bj.") + code
        rs = bs.query_history_k_data_plus(
            sym, "date,code,close", start_date=START, end_date=END,
            frequency="d", adjustflag="3")
        n = 0
        first = last = ""
        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            n += 1
            if n == 1:
                first = row[0]
            last = row[0]
        local = UNIVERSE / f"{code}.csv"
        local_rows = sum(1 for _ in local.open("r", encoding="utf-8", errors="ignore")) - 1 \
            if local.exists() else -1
        print(f"  {code}: baostock error_code={rs.error_code!r} msg={rs.error_msg!r} "
              f"rows={n}" + (f"（{first}~{last}）" if n else "")
              + f" · 本地tdx csv={'缺失' if local_rows < 0 else f'{local_rows} 行'}", flush=True)
    bs.logout()
    print(f"[done] 耗时 {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
