#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""成本口径重算 · 驱动脚本（方案③下半场）。

用法::

    python scripts/run_recompute.py --list              # 列出全部任务与进度
    python scripts/run_recompute.py --side copy         # 跑副本侧全部（跳过已完成）
    python scripts/run_recompute.py --only tc_t0        # 跑单份（其所有窗口）
    python scripts/run_recompute.py --side copy --batch 1   # 跑第 1 批

设计要点（依据 ``RECOMPUTE_EXECUTION_PLAN.md``）：

1. **按窗口拆进程** —— 单份产物运行 790~3542 s，超过本机后台静默死亡窗口
   （25~40 min，AGENTS.md §5），故每个窗口一个子进程、各自落盘；
2. **输出隔离** —— 一律写 ``reports/_recalc/<产物>_<窗口>.json``；``_`` 前缀命中
   ``.gitignore`` 的 ``reports/_*.json`` ⇒ 不会误入库，原产物保持不动；
3. **可续跑** —— 已完成窗口（产物存在且非空）自动跳过，中断后重跑同命令即续；
4. **不替产物下结论** —— 本脚本只跑与落盘，验收（V1~V5）由人工/对账脚本执行。

⚠️ 参数由原产物 ``args`` 字段反推（见执行清单 §三/§五）；**显式传参 = 原值 ≠ 默认值者**。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "_recalc"
PY = sys.executable

#: 副本侧 12 份（`gen_evidence_index.stamp_duty_stale` 规范集 ∩ 副本侧产物）
COPY_TASKS: List[Dict[str, Any]] = [
    {"name": "combo_study_h20", "script": "scripts/run_combo_study.py",
     "args": ["--dataset", "D:/tdx_dataset_v3", "--max-stocks", "300",
              "--top-frac", "0.2", "--threshold", "70.0", "--horizon", "20"],
     "windows": ["2023-07-03", "2024-01-02", "2025-01-02"]},
    {"name": "combo_study_h20_fixed", "script": "scripts/run_combo_study.py",
     "args": ["--dataset", "D:/tdx_dataset_v3", "--max-stocks", "300",
              "--top-frac", "0.2", "--threshold", "70.0", "--horizon", "20"],
     "windows": ["2023-07-03", "2024-01-02", "2025-01-02"]},
    {"name": "cost_model_check", "script": "scripts/run_cost_model_check.py",
     "args": ["--dataset", "D:/tdx_dataset", "--max-stocks", "400"],
     "windows": ["2023-07-03", "2024-01-02"]},
    {"name": "five_factor_ab_v2", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--horizon", "20",
              "--exclude-ret20-top", "0.2", "--exclude-jump"],
     "windows": ["2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02", "2025-07-01"]},
    {"name": "horizon_study", "script": "scripts/run_horizon_study.py",
     "args": ["--dataset", "D:/tdx_dataset_v3", "--horizons", "5,10,20,40",
              "--max-stocks", "300", "--top-n", "5", "--position-pct", "0.25",
              "--threshold", "70.0"],
     "windows": ["2023-07-03", "2024-01-02", "2025-01-02"]},
    {"name": "horizon_study_turnover_fixed", "script": "scripts/run_horizon_study.py",
     "args": ["--dataset", "D:/tdx_dataset_v3", "--horizons", "5,10,20,40",
              "--max-stocks", "300", "--top-n", "5", "--position-pct", "0.25",
              "--threshold", "70.0"],
     "windows": ["2023-07-03", "2024-01-02", "2025-01-02"]},
    {"name": "impact_cost", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--horizon", "20",
              "--exclude-ret20-top", "0.2", "--impact-model"],
     "windows": ["2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02", "2025-07-01"]},
    {"name": "tc_t0", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--exclude-ret20-top", "0.2"],
     "windows": ["2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02", "2025-07-01"]},
    {"name": "tc_t2", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--exclude-ret20-top", "0.2",
              "--max-participation", "0.05"],
     "windows": ["2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02", "2025-07-01"]},
    {"name": "v2_rolling_eval_ew", "script": "scripts/run_tdx_rolling_eval.py",
     "args": ["--dataset", "D:/tdx_dataset_v2"],
     "windows": ["2023-01-03", "2023-07-03", "2024-01-02", "2024-07-01",
                 "2025-01-02", "2025-07-01"]},
    {"name": "v3_rolling_eval_ew", "script": "scripts/run_tdx_rolling_eval.py",
     "args": ["--dataset", "D:/tdx_dataset_v3", "--max-stocks", "1000"],
     "windows": ["2023-01-03", "2023-07-03", "2024-01-02", "2024-07-01",
                 "2025-01-02", "2025-07-01"]},
    {"name": "v3_rolling_eval_ew_full", "script": "scripts/run_tdx_rolling_eval.py",
     "args": ["--dataset", "D:/tdx_dataset_v3", "--max-stocks", "1000"],
     "windows": ["2023-01-03", "2023-07-03", "2024-01-02", "2024-07-01",
                 "2025-01-02", "2025-07-01"]},
]

#: 批次划分（按估算时长分组，每批 ~40~60 min，适配本机后台限制）
BATCHES: Dict[int, List[str]] = {
    1: ["cost_model_check", "combo_study_h20", "combo_study_h20_fixed"],
    2: ["horizon_study", "horizon_study_turnover_fixed"],
    3: ["tc_t0", "tc_t2"],
    4: ["v2_rolling_eval_ew"],
    5: ["v3_rolling_eval_ew", "v3_rolling_eval_ew_full"],
    6: ["five_factor_ab_v2"],
    7: ["impact_cost"],
}


def out_path(task: Dict[str, Any], window: str) -> Path:
    return OUT_DIR / f"{task['name']}_{window}.json"


def is_done(task: Dict[str, Any], window: str) -> bool:
    p = out_path(task, window)
    if not p.exists() or p.stat().st_size == 0:
        return False
    try:
        json.loads(p.read_text(encoding="utf-8"))
    except Exception:                     # noqa: BLE001 — 半截文件视为未完成
        return False
    return True


def run_window(task: Dict[str, Any], window: str) -> int:
    cmd = [PY, str(ROOT / task["script"]), *task["args"],
           "--windows", window, "--out", str(out_path(task, window))]
    t0 = time.time()
    print(f"  ▶ {task['name']} @ {window} …", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT))
    dur = time.time() - t0
    ok = proc.returncode == 0 and is_done(task, window)
    print(f"    {'✓' if ok else '✗'} {task['name']} @ {window} "
          f"（{dur:.0f}s，exit={proc.returncode}）", flush=True)
    return 0 if ok else 1


def run_task(task: Dict[str, Any], resume: bool) -> int:
    print(f"=== {task['name']}（{len(task['windows'])} 窗口）===", flush=True)
    fails = 0
    for w in task["windows"]:
        if resume and is_done(task, w):
            print(f"  ⏭ {task['name']} @ {w} 已完成，跳过", flush=True)
            continue
        fails += run_window(task, w)
    return fails


def progress() -> str:
    done = total = 0
    for t in COPY_TASKS:
        for w in t["windows"]:
            total += 1
            done += is_done(t, w)
    return f"副本侧进度：{done}/{total} 窗口"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="成本口径重算驱动（方案③下半场）")
    ap.add_argument("--list", action="store_true", help="列出任务与进度")
    ap.add_argument("--side", choices=["copy"], default="copy",
                    help="产物侧别（当前仅副本侧；主侧待双方确认命令）")
    ap.add_argument("--only", default="", help="只跑指定产物名")
    ap.add_argument("--batch", type=int, default=0, help="只跑指定批次号")
    ap.add_argument("--no-resume", action="store_true",
                    help="不跳过已完成窗口（默认跳过）")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.list:
        for t in COPY_TASKS:
            marks = "".join("✓" if is_done(t, w) else "·" for w in t["windows"])
            print(f"  {t['name']:34} [{marks}]  {t['script']}")
        print(progress())
        return 0

    tasks = COPY_TASKS
    if args.only:
        tasks = [t for t in tasks if t["name"] == args.only]
        if not tasks:
            raise SystemExit(f"未知产物名：{args.only}")
    if args.batch:
        names = BATCHES.get(args.batch)
        if names is None:
            raise SystemExit(f"未知批次：{args.batch}（可用 {sorted(BATCHES)}）")
        tasks = [t for t in tasks if t["name"] in names]

    fails = 0
    for t in tasks:
        fails += run_task(t, resume=not args.no_resume)
    print(f"\n{progress()}　失败窗口数：{fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
