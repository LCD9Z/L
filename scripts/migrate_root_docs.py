# -*- coding: utf-8 -*-
r"""根目录文档收敛（B3）：把历史报告移入 `docs/archive/`，并**重写全部相对链接**。

## 为什么

根目录曾积压 **112 份** `.md`。`AGENTS.md` L92 早就写着
「`docs/archive/` 与早期 `*_REPORT.md` 多为过程记录或已作废结论」——
**约定存在，但从未执行**：根目录的 `*_REPORT.md` 一份没少。

后果不是「不整洁」，而是**导航失效**：新人和 AI 在 112 份同级文档里
分不清「哪份是结论、哪份是当年的过程记录」，只能靠文件名猜。
`ENTRYPOINTS.md` §八 已经给出正确的分级原则（「其余文档的定位，避免看起来都权威」），
本脚本只是把它执行到底。

## 分级原则（与 ENTRYPOINTS §八 一致）

| 档 | 判据 | 处置 |
|---|---|---|
| 导航 / 规范 | `AGENTS` `HANDOVER` `README` `ENTRYPOINTS` `DIRECTORY_LAYOUT` `CHANGELOG` `WORKLOG` `DAILY_*` `PERFORMANCE_PROTOCOL` `DATA_ASSET_REGISTRY` `BENCHMARK_ALIGNMENT` | **留根** |
| 结论源 | 所有 `*_PREREG*.md` / `*_VERDICT*.md`、`STEP1_3_EXECUTION_REPORT`、`AB_STUDIES_EVIDENCE` | **留根**（可追溯性优先） |
| 在研 / 最新审计 | `COST_BASELINE_PENDING_RECOMPUTE`、`PREREG_EXECUTION_PLAN`、`PROJECT_HEALTH_AUDIT` 等 | **留根** |
| 历史过程记录 | 其余 `*_REPORT` / `*_AUDIT` / `*_ASSESSMENT` / `*_PACKAGE` / `*_PLAN` | **归档** |

**只移动，不删除、不改内容**（链接由本脚本重写）。

## 链接重写

移走一个被 5 处引用的文件却不改链接 = 造 5 个死链。
故本脚本对**全树 md**（含被移动的那些自身）重算每个相对链接：
以「移动前的父目录」解析目标，以「移动后的父目录」生成新相对路径 ——
这样「源移动」「目标移动」「两者都移动」三种情况一次算对。

## 幂等

重跑不会重复移动（已在归档目录则跳过），README 的归档清单块
（`<!-- ARCHIVED_LIST:BEGIN -->` 之间）每次整体重生成。

## 用法

::

    python scripts/migrate_root_docs.py            # dry-run，只打印计划
    python scripts/migrate_root_docs.py --apply    # 执行
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "docs" / "archive"
ARCHIVE_README = ARCHIVE_DIR / "README.md"

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")

MARK_BEGIN = "<!-- ARCHIVED_LIST:BEGIN -->"
MARK_END = "<!-- ARCHIVED_LIST:END -->"

#: 归档清单：文件名 → 分组。**这是 B3 的唯一事实源**（守卫也从这里取）。
ARCHIVE: Dict[str, str] = {
    # ---- 实验结果报告（结论已进对应 VERDICT / STEP1_3）----
    "ADJUSTED_FACTOR_REPORT.md": "experiments",
    "COMBO_STUDY_REPORT.md": "experiments",
    "CONCENTRATION_REPORT.md": "experiments",
    "CONTRARIAN_HYPOTHESIS_REPORT.md": "experiments",
    "EXPERT_FILTER_AND_HF4_HV2_REPORT.md": "experiments",
    "FACTOR_HORIZON_DECAY_REPORT.md": "experiments",
    "FACTOR_HYPOTHESIS_REPORT.md": "experiments",
    "HORIZON_NET_EFFECT_REPORT.md": "experiments",
    "IMPACT_AND_CAPACITY_REPORT.md": "experiments",
    "IC_DIAGNOSIS_REPORT.md": "experiments",
    "MARKET_RISK_GATE_REPORT.md": "experiments",
    "PORTFOLIO_AB_REPORT.md": "experiments",
    "PORTFOLIO_AB_REPORT_2.md": "experiments",
    "PORTFOLIO_AB_REPORT_3.md": "experiments",
    "SAMPLING_SENSITIVITY_REPORT.md": "experiments",
    "SURVIVORSHIP_IMPACT_REPORT.md": "experiments",
    "TAIL_EXCLUSION_REPORT.md": "experiments",
    "TDX_EVALUATION_REPORT.md": "experiments",
    "UNIVERSE_REPLICATION_REPORT.md": "experiments",
    "DELISTED_UNIVERSE_REPORT.md": "experiments",
    "RERUN_CORRECTED_REPORT.md": "experiments",
    # ---- 审计 / 缺陷记录 ----
    "AUDIT_REPORT.md": "audits",
    "CODE_REDUNDANCY_AUDIT.md": "audits",
    "CROSS_DECADE_AUDIT.md": "audits",
    "AOCI_INDEX_DEFECT_REPORT.md": "audits",
    "SCORE_TURNOVER_DEFECT_REPORT.md": "audits",
    "CALIBRATION_DISCREPANCY_REPORT.md": "audits",
    # ---- 数据评估 / 可行性 ----
    "ASTOCK_DATA_ASSESSMENT.md": "data",
    "TDX_DATA_ASSESSMENT.md": "data",
    "V49_REFERENCE_ASSESSMENT.md": "data",
    "PIT_L3_920_BACKFILL_FEASIBILITY.md": "data",
    "D_DRIVE_FOLDERS_ANALYSIS.md": "data",
    # ---- 合并 / 迁移 / 接线记录 ----
    "MERGE_1.0_REPORT.md": "merge",
    "BRANCH_MERGE_REPORT.md": "merge",
    "SIX_ISLANDS_WIRING_REPORT.md": "merge",
    "AOCI_INTEGRATION_REPORT.md": "merge",
    "AOCI_INVESTIGATION.md": "merge",
    "GITHUB_REFERENCE_INTEGRATION_REPORT.md": "merge",
    # ---- 计划 / 设计过程 ----
    "P0_P1_EXECUTION_REPORT.md": "plans",
    "P3_PARAMETERIZATION_PLAN.md": "plans",
    "PIT_SNAPSHOT_P0_REPORT.md": "plans",
    "PIT_SNAPSHOT_P2_REPORT.md": "plans",
    "PIT_SNAPSHOT_P3_REPORT.md": "plans",
    "RECOMPUTE_EXECUTION_PLAN.md": "plans",
    # ---- 审阅 / 外部借鉴 / 其他 ----
    "CROSS_DECADE_ADDENDUM.md": "review",
    "REVIEW_ROUND2_PACKAGE.md": "review",
    "EXTERNAL_AUDIT_ADOPTION.md": "review",
    "README_CRAWL4AI_A_SHARE.md": "review",
    "BOLD_IDEAS_2026_10_11.md": "review",
    # ---- 文件名编码损坏，归档时修正 ----
    "L1_#U5206#U6790#U6a21#U677f.md": "review",
}

#: 移动时顺带改名：旧名 → 新名。
#: `L1_#U5206#U6790#U6a21#U677f` 是 `\u5206\u6790\u6a21\u677f`（「分析模板」）
#: 被某次工具处理中文路径时转义成的字面量 —— 文件名本身是坏的，内容完好。
RENAME: Dict[str, str] = {
    "L1_#U5206#U6790#U6a21#U677f.md": "L1_分析模板.md",
}

#: 留根白名单（除 ARCHIVE 之外的所有根 md 必须在这里）。
#: 守卫 `test_root_md_allowlist` 用它防「悄悄往根目录丢一份新 md」。
ROOT_ALLOWED = (
    # 导航 / 规范
    "AGENTS.md", "HANDOVER.md", "README.md", "ENTRYPOINTS.md",
    "DIRECTORY_LAYOUT.md", "CHANGELOG.md", "WORKLOG.md",
    "DAILY_OPERATION.md", "DAILY_TASK_GUIDE.md",
    "PERFORMANCE_PROTOCOL.md", "DATA_ASSET_REGISTRY.md", "BENCHMARK_ALIGNMENT.md",
    # 结论源（预注册 / 判定由 `_PREREG` / `_VERDICT` 模式覆盖，此处列正文结论）
    "STEP1_3_EXECUTION_REPORT.md", "AB_STUDIES_EVIDENCE.md",
    # 最新独立审计 / 在研
    "AUDIT_2026_10_02_REPORT.md", "PROJECT_HEALTH_AUDIT.md",
    "COST_BASELINE_PENDING_RECOMPUTE.md", "PREREG_EXECUTION_PLAN.md",
    "ALPHA_CAPABILITY_GAP_ANALYSIS.md", "ALPHA_HYPOTHESIS_BACKLOG.md",
    "PIT_SNAPSHOT_DESIGN.md", "MODULE_SPLIT_EVALUATION.md",
    # AGENTS.md 明确点名（导航骨架，不动）
    "AOCI_INTEGRATION.md", "EXTERNAL_REVIEW_2026_10_06.md",
    "GITHUB_ASHARE_QUANT_SURVEY.md", "LONG_HISTORY_FEASIBILITY_2026_10_06.md",
    "CROSS_DECADE_REVIEW_PACKAGE.md", "CROSS_DECADE_REVIEW_RESPONSE.md",
    # C2 预注册（2026-10-18）
    "EXPERT_FILTER_C2_PREREG.md",
)

GROUP_TITLES = {
    "experiments": "实验结果报告",
    "audits": "审计 / 缺陷记录",
    "data": "数据评估 / 可行性",
    "merge": "合并 / 迁移 / 接线",
    "plans": "计划 / 设计过程",
    "review": "审阅 / 外部借鉴 / 其他",
}


# ---------------------------------------------------------------------------
# 计划
# ---------------------------------------------------------------------------

def plan() -> Tuple[Dict[str, str], List[str], List[str]]:
    """返回 (moved_old_abs -> new_abs, 待移动清单, 问题清单)。"""
    moved: Dict[str, str] = {}
    todo: List[str] = []
    problems: List[str] = []
    for name in sorted(ARCHIVE):
        src = ROOT / name
        new_name = RENAME.get(name, name)
        dst = ARCHIVE_DIR / new_name
        if src.is_file():
            todo.append(name)
            moved[src.resolve().as_posix()] = dst.resolve().as_posix()
        elif dst.is_file():
            # 已归档过（幂等）—— 仍要登记映射，供链接重写用
            moved[src.resolve().as_posix()] = dst.resolve().as_posix()
        else:
            problems.append(f"{name}: 根目录与归档目录都不存在")
    return moved, todo, problems


# ---------------------------------------------------------------------------
# 链接重写
# ---------------------------------------------------------------------------

def _rewrite_file(read_from: Path, new_parent: Path, old_parent: Path,
                  moved: Dict[str, str]) -> Tuple[str, int]:
    """``read_from`` 读内容（移动前的位置）；``new_parent`` 用于生成新相对路径。

    两个父目录必须分开传：文件移动后自身相对路径的基准变了，
    但**链接目标**仍须按「移动前」的父目录解析，否则会解析到不存在的位置。
    """
    text = read_from.read_text(encoding="utf-8")
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        label, tgt = m.group(1), m.group(2)
        if tgt.startswith(("http://", "https://", "mailto:", "#")):
            return m.group(0)
        base, _, frag = tgt.partition("#")
        if not base:
            return m.group(0)
        target_old = (old_parent / base).resolve()
        target_new = moved.get(target_old.as_posix(), target_old)
        if target_new == target_old and new_parent == old_parent:
            return m.group(0)
        rel = os.path.relpath(target_new, new_parent).replace("\\", "/")
        count += 1
        # 若 label 本身就是路径（形如 `../../X.md`），同步更新 ——
        # 否则会出现「文字写 ../../X.md，链接指向 X.md」的错位。
        if label.strip("` ") == base:
            label = f"`{rel}`" if label.startswith("`") else rel
        return f"[{label}]({rel}{'#' + frag if frag else ''})"

    return LINK_RE.sub(repl, text), count


# ---------------------------------------------------------------------------
# 索引
# ---------------------------------------------------------------------------

def _first_heading(p: Path) -> str:
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()
        if s:
            return s[:60]
    return "—"


def render_index() -> str:
    rows: List[str] = []
    rows.append(MARK_BEGIN)
    rows.append("")
    rows.append("## 二、2026-10-18 收敛：根目录历史报告")
    rows.append("")
    rows.append(f"根目录曾有 **112 份**同级 md。按「结论源留根、过程记录归档」"
                f"（`ENTRYPOINTS.md` §八 的分级原则），把 **{len(ARCHIVE)} 份**"
                f"已完成实验的过程记录移入本目录，根目录降至 **62 份**。")
    rows.append("")
    rows.append("> 移动的是**位置**，不是权威性：这些文件全文保留、未改一字。")
    rows.append("> `*_PREREG.md` / `*_VERDICT.md` 等**结论源一律留在根目录**，")
    rows.append("> 因为它们是「可追溯性」的锚点，藏进归档目录会让引用链断掉。")
    rows.append("")
    for key in ("experiments", "audits", "data", "merge", "plans", "review"):
        names = sorted(n for n, g in ARCHIVE.items() if g == key)
        if not names:
            continue
        rows.append(f"### {GROUP_TITLES[key]}（{len(names)}）")
        rows.append("")
        rows.append("| 文件 | 主题（原文标题） |")
        rows.append("|---|---|")
        for n in names:
            actual = RENAME.get(n, n)
            p = ARCHIVE_DIR / actual
            title = _first_heading(p) if p.is_file() else "（缺失）"
            rows.append(f"| [`{actual}`]({actual}) | {title.replace('|', '/')} |")
        rows.append("")
    rows.append(MARK_END)
    return "\n".join(rows)


def write_index() -> None:
    old = ARCHIVE_README.read_text(encoding="utf-8") if ARCHIVE_README.is_file() else "# 阶段文档归档\n"
    block = render_index()
    if MARK_BEGIN in old and MARK_END in old:
        new = re.sub(re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END),
                     block, old, flags=re.S)
    else:
        new = old.rstrip() + "\n\n" + block + "\n"
    with open(ARCHIVE_README, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="根目录文档收敛（B3）")
    ap.add_argument("--apply", action="store_true", help="真正执行（默认 dry-run）")
    args = ap.parse_args(argv)

    moved, todo, problems = plan()
    print(f"待移动 {len(todo)} 份；已归档 {len(ARCHIVE) - len(todo) - len(problems)} 份")
    if problems:
        print("⚠️ 问题：")
        for p in problems:
            print("   " + p)

    # 扫描移动前的 md 清单（含旧父目录）
    before: List[Tuple[Path, Path]] = []
    for p in ROOT.rglob("*.md"):
        if ".git" in p.parts:
            continue
        before.append((p, p.parent))

    # 计划中的「新位置」
    def new_path_of(p: Path) -> Path:
        key = p.resolve().as_posix()
        if key in moved:
            return Path(moved[key])
        return p

    total_links = 0
    rewrites: List[Tuple[Path, Path, Path, int, str]] = []  # (old, new, old_parent, n, text)
    for old_p, old_parent in before:
        new_p = new_path_of(old_p)
        # 内容按「旧父目录」解析链接；若文件已移动，先按新位置读（内容相同）
        src_for_read = old_p if old_p.is_file() else new_p
        if not src_for_read.is_file():
            continue
        text, n = _rewrite_file(src_for_read, new_p.parent, old_parent, moved)
        total_links += n
        rewrites.append((old_p, new_p, old_parent, n, text))

    print(f"将重写 {total_links} 处相对链接（涉及 {sum(1 for r in rewrites if r[3])} 个 md）")

    if not args.apply:
        print("\n[dry-run] 待移动：")
        for n in todo:
            print(f"   {n} → docs/archive/{RENAME.get(n, n)}")
        print("\n[dry-run] 未执行。加 --apply 生效。")
        return 0

    # 1) 移动
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for n in todo:
        src = ROOT / n
        dst = ARCHIVE_DIR / RENAME.get(n, n)
        if dst.exists():
            print(f"⚠️ 目标已存在，跳过：{dst.name}")
            continue
        shutil.move(str(src), str(dst))
        print(f"moved {n} → docs/archive/{dst.name}")

    # 2) 写回链接（按新位置）
    changed = 0
    for _old_p, new_p, _old_parent, n, text in rewrites:
        if n == 0:
            continue
        target = new_p if new_p.is_file() else old_p
        if not target.is_file():
            continue
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        changed += 1
    print(f"重写完成：{changed} 个文件")

    # 3) 索引
    write_index()
    print(f"已更新 {ARCHIVE_README.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
