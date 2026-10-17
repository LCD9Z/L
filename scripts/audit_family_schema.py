#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""同族产物结构一致性审计（防「同名不同物」）。

**动因（2026-10-15 实例）**：A2 两库合并时，`reports/decay_h5.json` 两侧
**同名但并非同一实验**——主干版 `source=D:/new_tdx/vipdoc`、1500 只、10 键
（含 `composite_ic`）；副本版 `D:/tdx_dataset_v3`、400 只、4 键
（`full/quintiles/subperiods/args`）。合并时按「同型」处置取了副本版，
导致同族产物 `h1`/`h60` 是 10 键、`h5`/`h10`/`h20` 是 4 键，
而 `HANDOVER.md` 仍把五份一并登记为「IC 衰减曲线原始结果」
→ **登记与产物不符**。

那次是**偶然撞上**的。本脚本把这件事变成机械检查：按文件名归族，
比较同族内各份的顶层键集合；结构不一致即报警。

**族名规则**（去掉试验变体后缀，只保留「同一个实验的不同参数/窗口」）：

- 窗口日期后缀 ``_2023-07-03``
- 期限后缀 ``_h5`` / ``_h5_ic``
- 批次后缀 ``_p1`` / ``_part1`` / ``_batchA``

**同类但结构**允许不同**的（如 `*_with_p.json` 与 `*.json` 本就是不同产物），
以「族名不同」自然区分，无需白名单。

用法::

    python scripts/audit_family_schema.py            # 只报不一致
    python scripts/audit_family_schema.py --all      # 连同一致的一起列
    python scripts/audit_family_schema.py --recalc   # 额外对比 _recalc 重算产物

退出码：发现不一致返回 1（可作为 CI/守卫收集项），否则 0。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

#: 去掉的后缀（按序应用，只去一次）
_SUFFIXES = (
    r"_20\d\d-\d\d-\d\d",      # 窗口日期
    r"_h\d+_ic",               # 期限 + 主干/副本口径标记
    r"_h\d+",                  # 期限
    r"_v\d+",                  # 数据集代次（v2 / v3）
    r"_p\d+",                  # 参数批次
    r"_part\d+",               # 分片
    r"_batch[A-Z]",            # 批次字母
)


#: 已知且已解释的族内结构差异。**白名单必须写明原因与出处**，
#: 否则它会变成「把不一致藏起来」的工具。
KNOWN_DIVERGENCE: Dict[str, str] = {
    "decay": (
        "两个**不同实验**共用 `decay_h*` 前缀：主干口径（1500 只 / 通达信 / 10 键含 "
        "`composite_ic`）已加 `_ic` 后缀，副本口径（400 只 / v3 / 4 键 "
        "`full/quintiles/subperiods`）保留原名。见 HANDOVER.md 第四节与 "
        "2026-10-15 A2 复核回执 §四"
    ),
}


def family_of(name: str) -> str:
    """由文件名推出族名（去掉扩展名与试验变体后缀）。"""
    stem = Path(name).stem          # ⚠️ 必须先剥 `.json`，否则 `_h5$` 锚不住
    for pat in _SUFFIXES:
        stem = re.sub(pat + r"$", "", stem)
    return stem


def _top_keys(path: Path) -> Tuple[str, ...] | None:
    """读顶层键；非 dict / 读不动 ⇒ None。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return tuple(sorted(data.keys()))


def collect(include_recalc: bool) -> Dict[str, List[Tuple[str, Tuple[str, ...]]]]:
    groups: Dict[str, List[Tuple[str, Tuple[str, ...]]]] = defaultdict(list)
    for p in sorted(REPORTS.rglob("*.json")):
        rel = p.relative_to(REPORTS).as_posix()
        # 探针/中间产物（`_` 前缀，含 `_recalc/`）默认不参与族内比较，
        # 它们与正式产物的对比由 --recalc 单独做。
        if rel.startswith("_"):
            if not (include_recalc and rel.startswith("_recalc/")):
                continue
        keys = _top_keys(p)
        if keys is None:
            continue
        groups[family_of(p.name)].append((rel, keys))
    return groups


def report(groups, show_all: bool) -> int:
    bad = 0
    known_n = 0
    for fam in sorted(groups):
        items = groups[fam]
        if len(items) < 2:
            continue
        schemas = {k for _, k in items}
        if len(schemas) == 1:
            if show_all:
                print(f"  OK   {fam}: {len(items)} 份同构（{len(next(iter(schemas)))} 键）")
            continue
        known = fam in KNOWN_DIVERGENCE
        if known:
            known_n += 1
        else:
            bad += 1
        head = "ℹ️ 已知" if known else "⚠️ "
        print(f"\n{head}  {fam}: {len(items)} 份 / **{len(schemas)} 种结构**")
        if known:
            print(f"     原因: {KNOWN_DIVERGENCE[fam]}")
        by_schema: Dict[Tuple[str, ...], List[str]] = defaultdict(list)
        for rel, k in items:
            by_schema[k].append(rel)
        for k, rels in sorted(by_schema.items(), key=lambda kv: -len(kv[1])):
            print(f"     [{len(k)} 键] {', '.join(rels)}")
            print(f"             键: {', '.join(k)}")
    if known_n:
        print(f"\n（{known_n} 处为已解释的已知差异，不计入失败 —— "
              f"见 KNOWN_DIVERGENCE）")
    return bad


def recalc_diff() -> int:
    """`_recalc` 重算产物 vs 原产物：顶层键是否可比（验收 V1 的机检部分）。"""
    recalc = REPORTS / "_recalc"
    if not recalc.is_dir():
        print("\n（无 reports/_recalc/，跳过重算对比）")
        return 0
    bad = 0
    print("\n=== _recalc 重算产物 vs 原产物（顶层键可比性）===")
    for rp in sorted(recalc.glob("*.json")):
        fam = family_of(rp.name)
        origin = REPORTS / f"{fam}.json"
        if not origin.exists():
            continue
        rk, ok = _top_keys(rp), _top_keys(origin)
        if rk is None or ok is None:
            continue
        if rk == ok:
            continue
        only_new = [k for k in rk if k not in ok]
        only_old = [k for k in ok if k not in rk]
        print(f"  ⚠️ {rp.name} vs {origin.name}: 新增 {only_new} / 缺失 {only_old}")
        bad += 1
    if not bad:
        print("  全部可比（顶层键集合一致）")
    return bad


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="同族产物结构一致性审计")
    ap.add_argument("--all", action="store_true", help="连同一致的一起列")
    ap.add_argument("--recalc", action="store_true", help="额外对比 _recalc 重算产物")
    args = ap.parse_args(argv)

    groups = collect(include_recalc=False)
    multi = {f: v for f, v in groups.items() if len(v) >= 2}
    print(f"扫描 {REPORTS}：{sum(len(v) for v in groups.values())} 份可解析产物，"
          f"{len(multi)} 个族（≥2 份）")
    bad = report(groups, args.all)
    if args.recalc:
        bad += recalc_diff()

    print()
    if bad:
        print(f"❌ 发现 {bad} 处结构不一致 —— 逐一判断是「同名不同物」还是「正常的族内演进」")
    else:
        print("✅ 未发现同族结构不一致")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
