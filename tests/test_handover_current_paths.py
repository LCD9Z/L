# -*- coding: utf-8 -*-
"""HANDOVER.md 现行操作指引守卫（2026-10-18）。

背景（两处 P0 硬伤，均由盘点发现）：

  ① **§7.2 曾有两份待办表**（编号 1–8 与 1–9 重叠、同一任务状态互相矛盾，
     三行「已结案 / 已完成」夹在两张表中间破坏渲染）⇒ 照它判断「什么还没做」会判错。
  ② **§8 恢复流程等 4 处路径失效**：写的是 `cd C:/Users/T430/Desktop/1.0`，
     该目录自 2026-10-15 迁移后**已是空目录**，活主干为 `D:/hunhe/trunk`。

本测试只守**现行操作指引**（HANDOVER / AGENTS / README）。
历史报告（`AOCI_INDEX_DEFECT_REPORT.md` 等）里的旧路径是**当时事实的记录**，
按「只追加不改写」原则保留，**不在守卫范围内**。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 现行操作指引：照它操作会直接落空，必须指向活主干
GUIDES = ("HANDOVER.md", "AGENTS.md", "README.md")

# 失效路径：`cd C:/Users/T430/Desktop/1.0` 或 `cd C:\Users\T430\Desktop\1.0`
_STALE_CD = re.compile(
    r"cd\s+[`\"']?[A-Za-z]:[/\\]+Users[/\\]+T430[/\\]+Desktop[/\\]+1\.0",
    re.IGNORECASE,
)

# 「唯一开发目录」这一断言在迁移后已不成立（该目录现在是空的）
_STALE_CLAIM = "唯一开发目录"


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_current_guides_have_no_stale_workdir_command():
    """现行操作指引里不得出现 `cd <Desktop/1.0>` 这类失效命令。"""
    offenders = []
    for name in GUIDES:
        path = ROOT / name
        if not path.exists():
            continue
        for lineno, line in enumerate(_read(name).split("\n"), 1):
            if _STALE_CD.search(line):
                offenders.append(f"{name}:{lineno}: {line.strip()[:80]}")
    assert offenders == [], (
        "现行操作指引仍指向已失效的 Desktop/1.0（迁移后为空目录，活主干是 D:/hunhe/trunk）:\n"
        + "\n".join(offenders)
    )


def test_handover_points_to_live_trunk():
    """HANDOVER 必须至少有一处把工作目录写成活主干 `D:/hunhe/trunk`。"""
    text = _read("HANDOVER.md")
    assert "cd D:/hunhe/trunk" in text
    assert _STALE_CLAIM not in text, "「唯一开发目录」的断言已过时，应写明活主干与空目录的区别"


def test_handover_section_7_2_is_single_table():
    """§7.2 只允许一张待办表、一个「建议顺序」（曾出现双表 + 编号冲突）。"""
    lines = _read("HANDOVER.md").split("\n")
    start = next((i for i, v in enumerate(lines) if v.startswith("### 7.2")), None)
    assert start is not None, "HANDOVER 缺少 §7.2"
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ") or lines[i].startswith("### 7.3")), len(lines))
    body = lines[start:end]

    tables = [ln for ln in body if ln.startswith("| 优先级 | 任务")]
    orders = [ln for ln in body if ln.startswith("**建议顺序**")]
    assert len(tables) == 1, f"§7.2 有 {len(tables)} 个待办表头（应为 1）"
    assert len(orders) == 1, f"§7.2 有 {len(orders)} 个「建议顺序」（应为 1）"

    # 编号必须连续 1..N，不得重号
    nums = []
    for ln in body:
        m = re.match(r"\|\s*\*{0,2}(\d+)\*{0,2}\s*\|", ln)
        if m:
            nums.append(int(m.group(1)))
    assert nums == list(range(1, len(nums) + 1)), f"§7.2 编号不连续或重号: {nums}"
