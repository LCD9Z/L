# -*- coding: utf-8 -*-
"""用修正后的数据集（含 180 只退市股）重跑全部既有研究。

## 背景

此前所有研究结论都建立在**含幸存者偏差**的 TDX 数据集上。
2026-09-14 已把 180 只窗口内退市股正式并入（`pit_universe.json` 按实际
交易区间更新，preflight 门禁 PASS）。

本脚本按**原参数**依次重跑，以便逐项对比结论是否改变。

## 跑哪些

| 脚本 | 研究内容 |
|------|---------|
| `run_factor_study.py` | 横截面因子假设检验（10 个因子） |
| `run_tdx_rolling_eval.py` | 滚动窗口评估（基线策略超额收益） |
| `run_tail_exclusion_study.py` | 尾部剔除实验 |
| `run_concentration_study.py` | 持仓分散度研究 |

## 输出

每个研究的完整 stdout 落到 `reports/survivorship_rerun/<name>.log`，
便于与修正前的报告逐项对照。

用法::

    python scripts/rerun_studies_corrected.py --dataset D:/tdx_dataset
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: (脚本名, 附加参数)
STUDIES: Tuple[Tuple[str, List[str]], ...] = (
    ("run_factor_study", ["--max-stocks", "1500"]),
    ("run_tdx_rolling_eval", ["--max-stocks", "800"]),
    ("run_tail_exclusion_study", ["--max-stocks", "400"]),
    ("run_concentration_study", ["--sample-size", "300"]),
)


def main() -> int:
    ap = argparse.ArgumentParser(description="用修正后数据集重跑既有研究")
    ap.add_argument("--dataset", default="D:/tdx_dataset")
    ap.add_argument("--only", default="", help="只跑指定脚本（逗号分隔）")
    ap.add_argument("--timeout", type=int, default=3600, help="单个研究超时（秒）")
    args = ap.parse_args()

    out_dir = os.path.join(ROOT, "reports", "survivorship_rerun")
    os.makedirs(out_dir, exist_ok=True)

    selected = {s.strip() for s in args.only.split(",") if s.strip()}
    todo = [(n, a) for n, a in STUDIES if not selected or n in selected]

    print("=" * 88)
    print("用修正后的数据集重跑既有研究（含 180 只退市股）")
    print("=" * 88)
    print(f"  数据集: {args.dataset}")
    print(f"  输出  : {out_dir}")
    print(f"  待跑  : {len(todo)} 个\n")

    results = []
    for name, extra in todo:
        script = os.path.join(ROOT, "scripts", f"{name}.py")
        log = os.path.join(out_dir, f"{name}.log")
        cmd = [sys.executable, "-u", script, "--dataset", args.dataset,
               "--out", os.path.join(out_dir, f"{name}.json"), *extra]
        print(f"[{name}] 启动 ...", flush=True)
        t0 = time.time()
        env = dict(os.environ)
        env.setdefault("FETCH_RATE_PER_SEC", "0")
        try:
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                  timeout=args.timeout, env=env)
            ok = proc.returncode == 0
            body = (proc.stdout or "") + ("\n--- STDERR ---\n" + proc.stderr if proc.stderr else "")
        except subprocess.TimeoutExpired:
            ok = False
            body = f"!! 超时（{args.timeout}s）"
        with open(log, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        dt = time.time() - t0
        results.append((name, ok, dt, log))
        print(f"[{name}] {'OK' if ok else 'FAIL'}  {dt:.0f}s  -> {log}", flush=True)

    print("\n" + "=" * 88)
    print("汇总")
    print("=" * 88)
    for name, ok, dt, log in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:28s} {dt:>7.0f}s  {log}")
    failed = [n for n, ok, _, _ in results if not ok]
    if failed:
        print(f"\n  失败: {', '.join(failed)}")
        return 1
    print("\n  全部完成。请逐个对照修正前的报告，看结论是否改变。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
