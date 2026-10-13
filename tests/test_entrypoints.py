# -*- coding: utf-8 -*-
"""入口收敛守卫（整改清单 P2-1）。

## 验收标准

> **只有一个正式运行入口、一套正式配置和一份权威交接文档。**

## 防什么

项目有 **67 个可执行入口**（根目录 15 + scripts/ 52），是历史积累的结果。
发散本身不是错（历史脚本是凭据），**但「不知道哪个是正式的」是错的** ——
新人接手会随手跑一个诊断脚本当生产用，或者引用一个已被取代的版本。

本测试确保：

1. `ENTRYPOINTS.md` 存在，且声明了**恰好两个**正式入口
2. 两个正式入口**真实可用**（`run_daily` 可导入、`run_ci.py` 存在）
3. 根目录新增的 `__main__` 文件**必须**在清单里被提到（防悄悄冒出新入口）
4. 权威交接文档 `AGENTS.md` 存在

## 已知局限

- 不检查 scripts/ 下每个脚本都被分类（52 个里多数是一次性工具，
  逐个登记成本高于收益）；只要求**根目录**入口被覆盖
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "ENTRYPOINTS.md"

#: 正式入口（清单 §二）—— 只允许这两个
OFFICIAL_ENTRIES = ("tdx_native.run_daily", "run_ci.py")


def _entry_text() -> str:
    if not ENTRY.exists():
        pytest.fail("ENTRYPOINTS.md 缺失")
    return ENTRY.read_text(encoding="utf-8")


def test_entrypoints_doc_exists():
    assert ENTRY.is_file(), "ENTRYPOINTS.md 缺失"


def test_declares_exactly_two_official_entries():
    """正式入口必须恰好两个 —— 多了就不是「收敛」。"""
    text = _entry_text()
    # 在 §二 节里数 E1/E2 标记
    m = re.search(r"## 二、正式入口.*?(?=\n## )", text, re.S)
    assert m, "找不到 §二 正式入口节"
    section = m.group(0)
    ids = re.findall(r"\*\*(E\d+)\*\*", section)
    assert len(ids) == 2, (
        f"正式入口应为恰好 2 个，实测 {len(ids)} 个：{ids}\n"
        "→ 收敛的意思是「少」，不是「多列几个都算正式」")


def test_official_entries_exist():
    """两个正式入口必须真实可用。"""
    import importlib
    try:
        importlib.import_module("tdx_native.run_daily")
    except Exception as exc:                          # noqa: BLE001
        pytest.fail(f"tdx_native.run_daily 不可导入: {type(exc).__name__}: {exc}")
    assert (ROOT / "run_ci.py").is_file(), "run_ci.py 不存在"


def test_root_main_files_are_all_listed():
    """⚠️ 核心守卫：根目录所有含 __main__ 的 .py 必须在清单中出现。

    防「悄悄新增一个入口而不登记」——
    这正是入口发散的产生方式。
    """
    main_files = []
    for p in sorted(ROOT.glob("*.py")):
        try:
            if "__main__" in p.read_text(encoding="utf-8", errors="replace"):
                main_files.append(p.name)
        except OSError:
            continue
    text = _entry_text()
    missing = [f for f in main_files if f not in text]
    assert missing == [], (
        "以下根目录入口未在 ENTRYPOINTS.md 登记（新增入口须显式登记）:\n  "
        + "\n  ".join(missing))


def test_authoritative_handover_doc_exists():
    """权威交接文档必须存在（清单 §八 指定为 AGENTS.md）。"""
    assert (ROOT / "AGENTS.md").is_file(), "AGENTS.md 缺失"


def test_config_values_not_tracked():
    """实值配置不得入库（只允许 .example 模板）。"""
    import subprocess
    out = subprocess.run(["git", "ls-files"], cwd=str(ROOT),
                         capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("git 不可用")
    tracked = out.stdout.splitlines()
    for risk in ("llm_config.json", "feishu_config.json", ".env"):
        assert risk not in tracked, \
            f"实值配置 {risk} 被入库（应只入库 .example 模板）"
