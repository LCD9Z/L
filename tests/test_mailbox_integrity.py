# -*- coding: utf-8 -*-
"""信箱完整性守卫：台账所称的文件必须真实存在。

## 为什么需要（真实事故，2026-10-13）

主干侧 2026-10-12 20:10 在台账写下「回执已提交：
`02_回执/volume单位纠正+协议更新方式_主干_2026-10-12.md`」，但**该文件从未被创建**；
2026-10-13 由本侧独立核出（全盘搜索无）。

本侧同期在数据层发现**同类形态**：`meta/ingest_log.jsonl` 条目 `20261012-2042`
声称写入 `ingest_date=2026-10-13`（两个 sha256 俱全），但 raw/norm 两文件实测均不在
（去向无法重建，已按 `status=ANOMALY` 显式留痕）。

**「记录说有、磁盘没有」是一类问题，不是两个** —— 已并入 `README_协议.md` 第九节
（文件引用完整性），并明确按「静默失效」管理：必须显式记账，不得静默跳过。

## 本守卫的做法

解析 `_AI协作信箱/00_提案台账.md` 中所有形如 `NN_目录/文件名.md` 的引用，
断言对应文件真实存在。

## 已知局限

- 只校验**台账**里的引用；其他 md 里的引用暂未覆盖
- 不校验引用的**内容**是否与所称一致（那需要语义比对）
- **信箱为两侧共享**：主干侧同类守卫 `tests/test_mailbox_integrity.py` 并行运行，
  两侧互为交叉验证
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
#: 信箱在项目目录的**同级**（不在项目内），故用父目录定位
MAILBOX = ROOT.parent / "_AI协作信箱"
LEDGER = MAILBOX / "00_提案台账.md"

#: 台账里引用的文件形态：`02_回执/xxx.md` 或 `01_提案/xxx.md`
REF_PATTERN = re.compile(r"`?((?:0[0-9]|1[0-9])_[^`\s/]+/[^`\s]+\.md)`?")


def _ledger_text() -> str:
    if not LEDGER.exists():
        pytest.skip(f"台账不在预期位置：{LEDGER}")
    return LEDGER.read_text(encoding="utf-8", errors="replace")


def test_mailbox_exists():
    assert MAILBOX.is_dir(), f"协作信箱不存在：{MAILBOX}"


def test_ledger_referenced_files_exist():
    """⚠️ 核心守卫：台账里提到的每个文件都必须真实存在。"""
    text = _ledger_text()
    refs = sorted(set(REF_PATTERN.findall(text)))
    missing = []
    for rel in refs:
        if not (MAILBOX / rel).exists():
            missing.append(rel)
    assert missing == [], (
        "台账引用了不存在的文件（「声称落盘但没落盘」）:\n  "
        + "\n  ".join(missing)
        + "\n→ 请在台账中改正，或补落该文件。")


def test_ledger_has_no_placeholder_paths():
    """台账里不应出现明显的占位/示例路径（防复制粘贴残留）。"""
    text = _ledger_text()
    bad = [p for p in ("xxx.md", "yyy.md", "placeholder", "TODO.md")
           if p in text]
    assert bad == [], f"台账含占位路径: {bad}"


def test_receipt_dir_count_is_consistent():
    """回执目录里每个 .md 都应被台账提到（反向检查，防「写了但没记」）。

    ⚠️ 该检查只作**提示性**断言：允许存在尚未记账的最新回执，
    但数量差不应过大（>3 说明登记习惯已失控）。
    """
    rd = MAILBOX / "02_回执"
    if not rd.is_dir():
        pytest.skip("回执目录不存在")
    files = {p.name for p in rd.glob("*.md")}
    text = _ledger_text()
    unrecorded = sorted(f for f in files if f not in text)
    assert len(unrecorded) <= 3, (
        f"回执目录有 {len(unrecorded)} 个文件未被台账登记（登记习惯可能已失控）: "
        f"{unrecorded[:5]}")
