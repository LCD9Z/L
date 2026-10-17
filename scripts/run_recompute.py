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

#: 已落产物的**回溯基线**（按侧）：主侧 = 任务落地提交（登记册 §六），
#: 副本侧 = 10-17 验收回执文首基线。中间 docs/memory 类提交不改成本代码，故不取 mtime HEAD。
#: ⚠️ 必须与 `scripts/check_recompute.py::ATTRIBUTED_BASELINE` 的 main/copy 一致，
#: 由 `tests/test_recompute_baseline_stamp.py::test_baseline_constants_match_check_recompute` 守卫。
BASELINE_BY_SIDE = {"main": "8db1c65", "copy": "2b9f97d"}

#: 印花税分段生效日（与 `gen_evidence_index.STAMP_DUTY_CUT` 一致）。
#: 窗口**起点**早于该日 ⇒ 窗口内交易跨越生效日 ⇒ 受印花税缺陷影响。
#: ⚠️ 2026-10-15 实测：单窗口耗时 7~43 分钟（combo_study 5 组合 ≈ 43 min），
#: 52 窗口全量需 30+ 小时 → 提供 `--crossing-only` 只跑受影响窗口（15 个，约 29%）。
CROSSING_CUT = "2023-08-28"

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
    # ⚠️ 2026-10-17 修正（人工裁定「为副本 rolling_eval 补 --benchmark」）。
    #   原三项的 args 反推失真（只留 --dataset / --max-stocks），漏了
    #   max_stocks(v2=400) / min_rows_asset / survivorship_evidence / benchmark
    #   ⇒ 审计恒判 `preflight: LIMITED_OR_FAIL`
    #   （issues=['benchmark','insufficient_per_asset_history']）⇒ 6 个跨线窗口
    #   永久 `exit=2`。此处按两处凭据逐项还原：
    #     ① 主侧同款 `MAIN_TASKS['v2_ew_bench_part1']`（同 v2 数据集，原跑即
    #        `--max-stocks 400 --min-rows-asset 504 --benchmark .../benchmark_ew.csv --skip-audit`）；
    #     ② 副本原产物 `reports/{v2,v3}_rolling_eval_ew*.json` 的 `args` 字段。
    #   阻塞机理（实测）：`run_tdx_rolling_eval.py:128` 兜底 `bench = <ds>/benchmark.csv`，
    #   而 `bench_meta = bench + ".metadata.json"`；数据集里该 metadata 实际名为
    #   `benchmark.metadata.json` ⇒ 找不到 ⇒ 审计 `benchmark` 不过。
    #   基准来源见 `P005_3_3_BENCHMARK_PREREG.md` §六 与 `BENCHMARK_ALIGNMENT.md` §一/§四。
    {"name": "v2_rolling_eval_ew", "script": "scripts/run_tdx_rolling_eval.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--max-stocks", "400",
              "--min-rows-asset", "504",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--benchmark", "D:/tdx_dataset_v2/benchmark_ew.csv", "--skip-audit"],
     "windows": ["2023-01-03", "2023-07-03", "2024-01-02", "2024-07-01",
                 "2025-01-02", "2025-07-01"]},
    {"name": "v3_rolling_eval_ew", "script": "scripts/run_tdx_rolling_eval.py",
     "args": ["--dataset", "D:/tdx_dataset_v3", "--max-stocks", "1000",
              "--min-rows-asset", "504",
              "--survivorship-evidence", "D:/tdx_dataset_v3/evidence.json",
              "--benchmark", "D:/tdx_dataset_v3/benchmark_ew.csv", "--skip-audit"],
     "windows": ["2023-01-03", "2023-07-03", "2024-01-02", "2024-07-01",
                 "2025-01-02", "2025-07-01"]},
    {"name": "v3_rolling_eval_ew_full", "script": "scripts/run_tdx_rolling_eval.py",
     "args": ["--dataset", "D:/tdx_dataset_v3", "--max-stocks", "1000",
              "--min-rows-asset", "504",
              "--survivorship-evidence", "D:/tdx_dataset_v3/evidence.json",
              "--benchmark", "D:/tdx_dataset_v3/benchmark_ew.csv", "--skip-audit"],
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

#: 主侧 12 份（命令由主干 2026-10-15 晚逐份反推 args 确认，回应计划 §四 请求）。
#: P013 裁定口径：**只跑跨线窗口**（`--crossing-only`），产物作 D1 印花税影响量
#: 独立证据，**不并入**正式报告；A 档非跨线窗口不补跑。
#: `v2_ew_bench_part1` 生成脚本确认为 `run_tdx_rolling_eval.py`
#: （args 的 min_periods/min_rows_asset/benchmark_meta/skip_audit 形状匹配）。
MAIN_TASKS: List[Dict[str, Any]] = [
    {"name": "ab_n3_batchA", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--horizon", "20",
              "--exclude-ret20-top", "0.2", "--exclude-jump", "--exclude-limitup",
              "--skip-legacy-arms"],
     "windows": ["2023-07-03", "2024-01-02"]},
    {"name": "f4_p1", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--compare-factors", "ret20,vol20,loga20,maxret20"],
     "windows": ["2023-07-03", "2024-01-02"]},
    {"name": "five_factor_ab_main", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json"],
     "windows": ["2023-07-03", "2024-01-02", "2024-07-01"]},
    {"name": "impact_p3", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--horizon", "20",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--exclude-ret20-top", "0.2", "--impact-model"],
     "windows": ["2023-07-03", "2024-07-01"]},
    {"name": "rs_main", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--regime-switch"],
     "windows": ["2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02"]},
    {"name": "ss_p1", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--style-switch"],
     "windows": ["2023-07-03", "2024-01-02"]},
    {"name": "t1b_p1", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--horizon", "60",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--exclude-ret20-top", "0.2"],
     "windows": ["2023-07-03", "2024-01-02"]},
    {"name": "tc_t1_p2", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--horizon", "20",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--exclude-ret20-top", "0.2"],
     "windows": ["2023-07-03", "2024-01-02"]},
    {"name": "tc_t2_p1", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--exclude-ret20-top", "0.2", "--max-participation", "0.05"],
     "windows": ["2023-07-03", "2024-01-02"]},
    {"name": "v2_c20_v1_p2", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--exclude-ret20-top", "0.2"],
     "windows": ["2023-07-03", "2024-01-02", "2024-07-01"]},
    {"name": "v2_ew_bench_part1", "script": "scripts/run_tdx_rolling_eval.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--max-stocks", "400",
              "--min-rows-asset", "504",
              "--benchmark", "D:/tdx_dataset_v2/benchmark_ew.csv", "--skip-audit"],
     "windows": ["2023-07-03", "2024-01-02"]},
    {"name": "v2_p1", "script": "scripts/run_five_factor_ab.py",
     "args": ["--dataset", "D:/tdx_dataset_v2", "--horizon", "20",
              "--survivorship-evidence", "D:/tdx_dataset_v2/evidence.json",
              "--exclude-ret20-top", "0.2", "--exclude-jump"],
     "windows": ["2023-07-03", "2024-01-02"]},
]


def out_path(task: Dict[str, Any], window: str) -> Path:
    return OUT_DIR / f"{task['name']}_{window}.json"


def git_short_sha() -> str:
    """当前 HEAD 短 sha（P013-④ 的基线标识）；git 不可用时返回 ``unknown``。"""
    try:
        proc = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"],
                              cwd=str(ROOT), capture_output=True, text=True)
        sha = proc.stdout.strip()
        return sha if proc.returncode == 0 and sha else "unknown"
    except OSError:                       # git 不在 PATH（如纯净 cmd）
        return "unknown"


def json_style(raw: str) -> tuple[Optional[Any], str]:
    """探测 JSON 文本的**原生字节风格**：``(indent, trailing)``。

    ``indent``：``None`` = 单行；整数/``"\\t"`` = 缩进单位（取第二行前导空白）。
    ``trailing``：文件尾部的换行串（可能为空）。重写产物时必须沿用，
    否则「只加一个字段」会顺手把整份文件的格式改掉。
    """
    trailing = raw[len(raw.rstrip("\r\n")):]
    body = raw[:len(raw) - len(trailing)]
    lines = body.splitlines()
    indent: Optional[Any] = None
    if len(lines) > 1:
        nxt = lines[1]
        lead = nxt[:len(nxt) - len(nxt.lstrip(" \t"))]
        if lead:
            indent = "\t" if lead[0] == "\t" else len(lead)
    return indent, trailing


def stamp_baseline(task: Dict[str, Any], window: str,
                   commit: Optional[str] = None) -> Optional[str]:
    """给**新落盘**产物补 ``_baseline``（P013-④ 原文：生成时写 HEAD 短 sha + 时间戳）。

    幂等：已有 ``_baseline`` 的产物不覆盖（防重跑抹掉原始基线）。
    ``git`` 不可用（sha = ``unknown``）时**不落戳** —— 否则会把 ``unknown`` 永久写死，
    幂等逻辑反而阻断日后补戳。
    重写沿用产物**原生缩进与尾换行**（实测 `_recalc` 产物为 ``indent=1``、无尾换行）。
    返回写入的 commit；不适用（无产物 / 已有戳 / sha 不可用 / 解析失败）时返回 ``None``。
    """
    p = out_path(task, window)
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "_baseline" in data:
        return None
    sha = commit or git_short_sha()
    if sha == "unknown":
        return None
    data["_baseline"] = {
        "commit": sha,
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "run_recompute",
    }
    indent, trailing = json_style(raw)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + trailing,
                 encoding="utf-8", newline="")
    return sha


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
    if ok:
        sha = stamp_baseline(task, window)
        if sha:
            print(f"    ⓘ _baseline = {sha}（P013-④）", flush=True)
    print(f"    {'✓' if ok else '✗'} {task['name']} @ {window} "
          f"（{dur:.0f}s，exit={proc.returncode}）", flush=True)
    return 0 if ok else 1


def run_task(task: Dict[str, Any], resume: bool, crossing_only: bool = False) -> int:
    wins = [w for w in task["windows"] if (not crossing_only or w < CROSSING_CUT)]
    if crossing_only:
        print(f"=== {task['name']}（跨线 {len(wins)}/{len(task['windows'])} 窗口）===",
              flush=True)
    else:
        print(f"=== {task['name']}（{len(task['windows'])} 窗口）===", flush=True)
    fails = 0
    for w in wins:
        if resume and is_done(task, w):
            print(f"  ⏭ {task['name']} @ {w} 已完成，跳过", flush=True)
            continue
        fails += run_window(task, w)
    return fails


def progress(tasks: List[Dict[str, Any]], side: str) -> str:
    done = total = 0
    for t in tasks:
        for w in t["windows"]:
            total += 1
            done += is_done(t, w)
    label = "副本侧" if side == "copy" else "主侧"
    return f"{label}进度：{done}/{total} 窗口"


def write_baseline_index(tasks_by_side: Dict[str, List[Dict[str, Any]]]) -> Path:
    """为**已落盘**产物登记基线，写入 ``reports/_recalc/_baseline_index.json``。

    **取值分两层，产物自证优先**（2026-10-18 修）：
    ① 产物已有内嵌 ``_baseline``（`stamp_baseline()` 落的）→ **照抄**，``origin="embedded"``；
       这是产物自己说的生成时 HEAD，比任何按侧推断都准，**不得被按侧值覆盖**；
    ② 无内嵌（P013-④ 之前的旧产物）→ 按侧**回溯补记**：主侧 ``8db1c65``（登记册 §六）、
       副本侧 ``2b9f97d``（10-17 验收回执文首），``origin="backfilled"``。
       中间若干「docs(memory)」类提交不改成本代码，故取任务落地提交而非 mtime 当时 HEAD。

    ⚠️ 2026-10-18 教训：旧实现对**全部**产物一律按侧写死，把 37 份**自证产物**
    （内嵌 a4be6ab / da7f6ac）也盖成 ``2b9f97d``+``origin=backfilled`` ——
    与 2026-10-17「43 份统一记 f8f020d」**同型**：批量赋值忽略逐份事实。

    ⚠️ **不改产物字节、不改 mtime** —— 本索引只是**旁挂**登记
    （2026-10-17 自创的证据保全方案），不是产物自证。
    """
    entries: Dict[str, Dict[str, Any]] = {}
    for side, tasks in tasks_by_side.items():
        side_commit = BASELINE_BY_SIDE[side]
        for t in tasks:
            for w in t["windows"]:
                p = out_path(t, w)
                if not p.exists():
                    continue
                commit, origin, embedded_as_of = side_commit, "backfilled", None
                try:
                    doc = json.loads(p.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                    doc = None
                emb = doc.get("_baseline") if isinstance(doc, dict) else None
                if isinstance(emb, dict):
                    sha = str(emb.get("commit") or "").strip()
                    if sha and sha != "unknown":
                        commit, origin = sha, "embedded"
                        embedded_as_of = emb.get("as_of")
                rec = {
                    "product": t["name"],
                    "side": side,
                    "window": w,
                    "commit": commit,
                    "as_of": time.strftime("%Y-%m-%dT%H:%M:%S",
                                           time.localtime(p.stat().st_mtime)),
                    "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime(p.stat().st_mtime)),
                    "size": p.stat().st_size,
                    "origin": origin,   # embedded = 产物自证；backfilled = 按侧回溯补记
                }
                if embedded_as_of:
                    rec["embedded_as_of"] = embedded_as_of
                entries[p.name] = rec
    out = OUT_DIR / "_baseline_index.json"
    out.write_text(json.dumps({
        "_note": (
            "P013-④ 基线登记，**两种来源**：origin=embedded 者照抄产物内嵌 `_baseline`"
            "（生成时 HEAD，产物自证）；origin=backfilled 者按侧回溯补记（main 依据 "
            "COST_BASELINE 册 §六 = 8db1c65，copy 依据 10-17 验收回执 = 2b9f97d；"
            "中间文档/测试提交不影响成本代码，故取任务落地提交）。产物字节与 mtime 未改动。"),
        "baseline_by_side": dict(BASELINE_BY_SIDE),
        "entries": entries},
        ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="成本口径重算驱动（方案③下半场）")
    ap.add_argument("--list", action="store_true", help="列出任务与进度")
    ap.add_argument("--side", choices=["copy", "main"], default="copy",
                    help="产物侧别（main = 主侧 12 份，命令已由 P013 配套确认）")
    ap.add_argument("--only", default="", help="只跑指定产物名")
    ap.add_argument("--batch", type=int, default=0, help="只跑指定批次号（仅副本侧）")
    ap.add_argument("--no-resume", action="store_true",
                    help="不跳过已完成窗口（默认跳过）")
    ap.add_argument("--crossing-only", action="store_true",
                    help=f"只跑窗口起点 < {CROSSING_CUT} 的窗口（受印花税缺陷影响者）")
    ap.add_argument("--baseline-index", action="store_true",
                    help="为已落盘产物回溯补记基线索引（按侧取值；不重写产物字节）")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_tasks = COPY_TASKS if args.side == "copy" else MAIN_TASKS

    if args.baseline_index:
        # 一次覆盖**两侧**全部已落盘产物（当前 80 份 = 主 28 + 副本 52），与 --side 无关
        p = write_baseline_index({"main": MAIN_TASKS, "copy": COPY_TASKS})
        data = json.loads(p.read_text(encoding="utf-8"))
        ents = data["entries"]
        groups: Dict[str, int] = {}
        for e in ents.values():
            key = f"{e['side']}:{e['commit']}:{e['origin']}"
            groups[key] = groups.get(key, 0) + 1
        print(f"基线索引已写入 {p.relative_to(ROOT)}（{len(ents)} 份产物；"
              f"embedded = 产物自证 / backfilled = 按侧补记）")
        for k, n in sorted(groups.items()):
            print(f"  {k:34} {n:2} 份")
        return 0

    if args.list:
        for t in all_tasks:
            marks = "".join("✓" if is_done(t, w) else "·" for w in t["windows"])
            print(f"  {t['name']:34} [{marks}]  {t['script']}")
        print(progress(all_tasks, args.side))
        return 0

    tasks = all_tasks
    if args.only:
        tasks = [t for t in tasks if t["name"] == args.only]
        if not tasks:
            raise SystemExit(f"未知产物名：{args.only}")
    if args.batch:
        if args.side != "copy":
            raise SystemExit("--batch 仅适用于副本侧（主侧按 --only 或全量）")
        names = BATCHES.get(args.batch)
        if names is None:
            raise SystemExit(f"未知批次：{args.batch}（可用 {sorted(BATCHES)}）")
        tasks = [t for t in tasks if t["name"] in names]

    fails = 0
    for t in tasks:
        fails += run_task(t, resume=not args.no_resume,
                        crossing_only=args.crossing_only)
    print(f"\n{progress(all_tasks, args.side)}　失败窗口数：{fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
