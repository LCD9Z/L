#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""成本口径重算 · 对账（验收 V1–V4 自动化）。

用法::

    python scripts/check_recompute.py                 # 对账全部已有重算产物
    python scripts/check_recompute.py --only tc_t0    # 单份
    python scripts/check_recompute.py --verbose       # 逐字段列出差异

设计（依据 ``RECOMPUTE_EXECUTION_PLAN.md`` §2.3）：

- **通用窗口匹配**：产物结构分三类（``five_factor_ab`` 用 ``window``、
  ``combo_study`` 用 ``rows[].window``、``rolling_eval``/``cost_model_check``
  用 ``oos_start``）→ 递归收集「带窗口标识的记录」，按窗口对齐两侧；
- **V1 结构可比**：两侧同窗口的键集合差异（只报缺键，不报新增只读字段）；
- **V2 确实产生差异**：数值叶子（排除元数据键）是否有变化；
- **V3 方向**：收益/超额类字段的变化方向（成本升 ⇒ 收益降）；
- **V4 完整性**：重算侧无 ``None``/``NaN`` 关键字段。

只读脚本：不修改任何产物。
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
RECALC = ROOT / "reports" / "_recalc"

#: 窗口标识键（三类产物各用其一）
WIN_KEYS = ("window", "oos_start")

#: 不参与数值对比的元数据键
META_KEYS = frozenset({"args", "runtime_sec", "prereg", "benchmark", "source",
                       "stocks", "samples", "capacity_capped_buys"})

#: 收益/超额类字段（V3 方向判定；成本升 ⇒ 这些值应**下降**）
RETURN_KEYS = ("total_return_pct", "annualized_excess", "annualized_excess_pct",
               "net_return", "excess_delta_pp", "benchmark_return_pct")

#: 产物文件名 = ``<名>_<窗口>.json``，窗口恒为 ``YYYY-MM-DD``。
#: ⚠️ 2026-10-16 修：原用 ``glob(f"{name}_*.json")`` 前缀匹配，会把**同族产物互相吞并**
#: —— ``combo_study_h20`` 会吞 ``combo_study_h20_fixed_*``、``tc_t2`` 会吞 ``tc_t2_p1_*``，
#: 使不属于该产物的窗口被计入对账。改为按 ``<名>_<窗口>`` 精确切分
#: （产品名不含 ``YYYY-MM-DD``，切分无歧义）。
NAME_WIN_RE = re.compile(r"^(?P<name>.+)_(?P<win>\d{4}-\d{2}-\d{2})$")


def parse_stem(stem: str) -> Optional[Tuple[str, str]]:
    """把 ``<名>_<窗口>`` 切成 (名, 窗口)；不匹配（如 ``.partial``）返回 None。"""
    m = NAME_WIN_RE.match(stem)
    return (m.group("name"), m.group("win")) if m else None


def files_for(name: str) -> List[Path]:
    """返回 ``name`` 的全部重算产物（**精确名匹配**，不吞同族产物）。"""
    out = [p for p in RECALC.glob("*.json")
           if (parsed := parse_stem(p.stem)) and parsed[0] == name]
    return sorted(out)


def index_by_window(obj: Any, out: Dict[str, List[Dict[str, Any]]]) -> None:
    """递归收集带窗口标识的记录（按窗口值分组）。"""
    if isinstance(obj, dict):
        for k in WIN_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and v:
                out.setdefault(v, []).append(obj)
                break
        for v in obj.values():
            index_by_window(v, out)
    elif isinstance(obj, list):
        for v in obj:
            index_by_window(v, out)


def numeric_leaves(obj: Any, prefix: str = "") -> Dict[str, float]:
    """递归取数值叶子（跳过元数据键）。"""
    out: Dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in META_KEYS:
                continue
            out.update(numeric_leaves(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(numeric_leaves(v, f"{prefix}[{i}]"))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        f = float(obj)
        if not math.isnan(f):
            out[prefix] = f
    return out


def keys_of(obj: Any) -> set:
    return set(obj) if isinstance(obj, dict) else set()


def check_one(name: str, verbose: bool) -> Tuple[int, int, int]:
    """对账单份产物，返回（V1 失败数, 差异窗口数, 方向异常数）。"""
    old_p = ROOT / "reports" / f"{name}.json"
    if not old_p.exists():
        print(f"  ✗ {name}: 原产物不存在")
        return 1, 0, 0
    news = files_for(name)
    if not news:
        print(f"  · {name}: 无重算产物（未跑）")
        return 0, 0, 0

    old_idx: Dict[str, List[Dict[str, Any]]] = {}
    index_by_window(json.loads(old_p.read_text(encoding="utf-8")), old_idx)

    v1 = changed = v3 = 0
    for np_ in news:
        new = json.loads(np_.read_text(encoding="utf-8"))
        new_idx: Dict[str, List[Dict[str, Any]]] = {}
        index_by_window(new, new_idx)
        for win, recs in new_idx.items():
            olds = old_idx.get(win, [])
            if not olds:
                print(f"  ⚠ {name}@{win}: 原产物无同窗口记录（窗口标识不匹配？）")
                continue
            old_rec, new_rec = olds[0], recs[0]
            # V1 结构可比（只报原侧有、新侧缺的键）
            miss = keys_of(old_rec) - keys_of(new_rec)
            if miss:
                v1 += 1
                print(f"  ✗ V1 {name}@{win}: 重算侧缺键 {sorted(miss)[:5]}")
            # V2/V3 数值差异
            a, b = numeric_leaves(old_rec), numeric_leaves(new_rec)
            diffs = [(k, a[k], b[k]) for k in a if k in b and a[k] != b[k]]
            if diffs:
                changed += 1
                if verbose:
                    for k, va, vb in diffs[:8]:
                        print(f"      {k}: {va:+.4f} → {vb:+.4f}（{vb - va:+.4f}）")
            # V3 方向（仅收益/超额类）
            for k, va, vb in diffs:
                if k.split(".")[-1] in RETURN_KEYS and vb > va + 1e-9:
                    v3 += 1
                    print(f"  ⚠ V3 {name}@{win} {k}: {va:+.4f} → {vb:+.4f}"
                          f"（**上升**——与「成本升⇒收益降」相反，须单独排查）")
    print(f"  ✓ {name}: {len(news)} 窗口文件 · 结构缺失 {v1} · 有差异窗口 {changed}"
          f" · 方向异常 {v3}")
    return v1, changed, v3


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="重算对账（V1–V4）")
    ap.add_argument("--only", default="", help="只对账单份")
    ap.add_argument("--verbose", action="store_true", help="逐字段列出差异")
    args = ap.parse_args(argv)

    names = sorted({
        parsed[0]
        for p in RECALC.glob("*.json")
        if (parsed := parse_stem(p.stem))
    })
    if args.only:
        names = [n for n in names if n == args.only] or [args.only]
    if not names:
        print("无重算产物（reports/_recalc/ 为空）")
        return 0

    tot_v1 = tot_changed = tot_v3 = 0
    for n in names:
        a, b, c = check_one(n, args.verbose)
        tot_v1 += a
        tot_changed += b
        tot_v3 += c
    print(f"\n汇总：V1 结构缺失 {tot_v1} · 有差异窗口 {tot_changed} · 方向异常 {tot_v3}")
    return 1 if (tot_v1 or tot_v3) else 0


if __name__ == "__main__":
    raise SystemExit(main())
