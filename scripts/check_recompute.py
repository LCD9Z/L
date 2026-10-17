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
#: ⚠️ 2026-10-17 裁定 F：基准类字段移出本集合 —— 基准代次替换（沪深300→等权）不是
#: 「收益上升」，混判会让 V3 异常计数虚高（副本侧 15 处中约 8 处属此类）。
RETURN_KEYS = ("total_return_pct", "annualized_excess", "annualized_excess_pct",
               "net_return", "excess_delta_pp")

#: 基准类字段：只报告「基准口径替换」，**不**计入 V3 方向异常（2026-10-17 裁定 F）
BENCHMARK_KEYS = ("benchmark_return_pct", "ew_benchmark_return_pct")

#: 口径替换族：旧侧存在、新侧按「单一认证基准」不再产出（2026-10-17 裁定 C）。
#: **仅此一族**（`ew_*`：等权基准现算改为外部认证 CSV）。新增族须先有裁定，
#: 并同步 `tests/test_check_recompute_caliber.py` 的显式键集合。
#: 防滥用：仅当新记录**同时**含外部基准字段时才允许归类 CALIBER，否则仍计 V1 失败。
CALIBER_REMOVED_PREFIXES = ("ew_",)

#: **已归因为 D2（A2 代码基线演进）的产物**：其收益/超额上升计 ATTRIBUTED，
#: **不**计 V3 方向异常（但仍逐条打印，不静默）。
#:
#: 归因依据：`COST_BASELINE_PENDING_RECOMPUTE.md` §七（主因 `0a81a5f` 候选池修复）
#: + 信箱回执 `成本口径重算副本侧15跨线窗口验收_主干_2026-10-17.md` §九-D
#: （「24 份重算差异 100% 为 A2 代码基线演进，不含印花税修复成分」）。
#:
#: ⚠️ **这是显式白名单，不是默认**：新增产物（或换基线重跑）**不在**本清单内，
#: 其收益上升仍计 V3 → 守卫保持有效。增补须有新的归因裁定。
ATTRIBUTED_TO_BASELINE = frozenset({
    # 主侧 MAIN_TASKS 12 份（§六，基线 8db1c65）
    "ab_n3_batchA", "f4_p1", "five_factor_ab_main", "impact_p3", "rs_main",
    "ss_p1", "t1b_p1", "tc_t1_p2", "tc_t2_p1", "v2_c20_v1_p2",
    "v2_ew_bench_part1", "v2_p1",
    # 副本侧 COPY_TASKS 12 份（回执 §八/§九-D）
    "combo_study_h20", "combo_study_h20_fixed", "cost_model_check",
    "five_factor_ab_v2", "horizon_study", "horizon_study_turnover_fixed",
    "impact_cost", "tc_t0", "tc_t2", "v2_rolling_eval_ew",
    "v3_rolling_eval_ew", "v3_rolling_eval_ew_full",
})

#: 白名单的**适用基线**（P014 备注 2）。「24 份差异 100% 为 A2 基线演进」这一归因
#: 只对**下列基线**成立；换基线重跑同名产物时，必须先人工复核归因是否仍成立，
#: 复核后在原处更新时间戳 —— 让「复核」动作在 diff 中可见，而不是静默沿用旧白名单。
#: 守卫：`tests/test_check_recompute_caliber.py::test_attributed_whitelist_*`
ATTRIBUTED_BASELINE = {
    "main": "8db1c65",   # 主侧 MAIN_TASKS 落地提交
    "copy": "2b9f97d",   # 副本侧最近一次基线（精确名切分）
    "recorded_at": "2026-10-17",
}

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


def files_for(name: str, recalc: Optional[Path] = None) -> List[Path]:
    """返回 ``name`` 的全部重算产物（**精确名匹配**，不吞同族产物）。

    ``recalc`` 为 ``None`` 时读模块级 ``RECALC``（运行时解析，便于测试 monkeypatch）。
    """
    recalc = RECALC if recalc is None else recalc
    out = [p for p in recalc.glob("*.json")
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


def check_one(name: str, verbose: bool, root: Optional[Path] = None,
              recalc: Optional[Path] = None) -> Tuple[int, int, int, int, int, int]:
    """对账单份产物。

    返回 ``(V1 真实缺键, CALIBER 口径替换, 差异窗口数, V3 未归因上升, 基准替换数,
    ATTRIBUTED 已归因上升)``。

    - **CALIBER**：旧侧有 ``ew_*`` 族、新侧因改用单一认证基准不再产出，
      且新记录**含外部基准字段**（``benchmark_return_pct`` / ``annualized_excess``）
      ⇒ 归类为口径替换，**不计 V1 失败**（2026-10-17 裁定 C）；
      缺「外部基准字段」则不构成替换证据，``ew_*`` 缺键仍并入 V1 失败。
    - **BENCHMARK**：基准类字段数值变化只报告，**不计 V3 方向异常**（裁定 F）。
    - **ATTRIBUTED**：产物在 ``ATTRIBUTED_TO_BASELINE`` 白名单内的收益上升，
      已归因 D2 基线演进（裁定 D），单列不计 V3；不在白名单仍计 V3。
    """
    root = ROOT if root is None else root
    recalc = RECALC if recalc is None else recalc
    old_p = root / "reports" / f"{name}.json"
    if not old_p.exists():
        print(f"  ✗ {name}: 原产物不存在")
        return 1, 0, 0, 0, 0, 0
    news = files_for(name, recalc)
    if not news:
        print(f"  · {name}: 无重算产物（未跑）")
        return 0, 0, 0, 0, 0, 0

    old_idx: Dict[str, List[Dict[str, Any]]] = {}
    index_by_window(json.loads(old_p.read_text(encoding="utf-8")), old_idx)

    v1 = caliber = changed = v3 = bench = attributed = 0
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
            # V1 结构可比（只报原侧有、新侧缺的键；口径替换族单列 CALIBER）
            miss = keys_of(old_rec) - keys_of(new_rec)
            if miss:
                caliber_miss = {k for k in miss
                                if k.startswith(CALIBER_REMOVED_PREFIXES)}
                real_miss = miss - caliber_miss
                has_ext_bench = ("benchmark_return_pct" in new_rec
                                 or "annualized_excess" in new_rec)
                if caliber_miss and has_ext_bench:
                    caliber += 1
                    print(f"  ℹ️ CALIBER {name}@{win}: 口径替换 "
                          f"{sorted(caliber_miss)}（新侧单一认证基准，不计 V1）")
                else:
                    real_miss |= caliber_miss   # 无基准替换证据 ⇒ 不得销项
                if real_miss:
                    v1 += 1
                    print(f"  ✗ V1 {name}@{win}: 重算侧缺键 {sorted(real_miss)[:5]}")
            # V2/V3 数值差异
            a, b = numeric_leaves(old_rec), numeric_leaves(new_rec)
            diffs = [(k, a[k], b[k]) for k in a if k in b and a[k] != b[k]]
            if diffs:
                changed += 1
                if verbose:
                    for k, va, vb in diffs[:8]:
                        print(f"      {k}: {va:+.4f} → {vb:+.4f}（{vb - va:+.4f}）")
            # V3 方向（仅收益/超额类）；基准类单列
            for k, va, vb in diffs:
                leaf = k.split(".")[-1]
                if leaf in BENCHMARK_KEYS:
                    bench += 1
                    if verbose:
                        print(f"      ℹ️ BENCHMARK {name}@{win} {k}: "
                              f"{va:+.4f} → {vb:+.4f}（基准口径替换，不计 V3）")
                elif leaf in RETURN_KEYS and vb > va + 1e-9:
                    if name in ATTRIBUTED_TO_BASELINE:
                        attributed += 1
                        if verbose:
                            print(f"      ℹ️ ATTRIBUTED {name}@{win} {k}: "
                                  f"{va:+.4f} → {vb:+.4f}"
                                  f"（上升，已归因 D2 基线演进，不计 V3）")
                    else:
                        v3 += 1
                        print(f"  ⚠ V3 {name}@{win} {k}: {va:+.4f} → {vb:+.4f}"
                              f"（**上升**——与「成本升⇒收益降」相反，须单独排查）")
    print(f"  ✓ {name}: {len(news)} 窗口文件 · V1 真实缺键 {v1} · CALIBER {caliber}"
          f" · 有差异窗口 {changed} · V3 未归因上升 {v3}"
          f" · ATTRIBUTED {attributed} · 基准替换 {bench}")
    return v1, caliber, changed, v3, bench, attributed


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

    tot_v1 = tot_cal = tot_changed = tot_v3 = tot_bench = tot_attr = 0
    for n in names:
        a, cal, b, c, d, e = check_one(n, args.verbose)
        tot_v1 += a
        tot_cal += cal
        tot_changed += b
        tot_v3 += c
        tot_bench += d
        tot_attr += e
    print(f"\n汇总：V1 真实缺键 {tot_v1} · CALIBER 口径替换 {tot_cal}"
          f" · 有差异窗口 {tot_changed} · V3 未归因上升 {tot_v3}"
          f" · ATTRIBUTED 已归因上升 {tot_attr} · 基准替换 {tot_bench}")
    return 1 if (tot_v1 or tot_v3) else 0


if __name__ == "__main__":
    raise SystemExit(main())
