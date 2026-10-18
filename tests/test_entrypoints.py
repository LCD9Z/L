# -*- coding: utf-8 -*-
"""入口收敛守卫（整改清单 P2-1）。

## 验收标准

> **只有一个正式运行入口、一套正式配置和一份权威交接文档。**

## 防什么

项目有 **97 个可执行入口**（根目录 15 + `scripts/` 82），是历史积累的结果。
发散本身不是错（历史脚本是凭据），**但「不知道哪个是正式的」是错的** ——
新人接手会随手跑一个诊断脚本当生产用，或者引用一个已被取代的版本。

本测试确保：

1. `ENTRYPOINTS.md` 存在，且 §二 声明的入口与 `OFFICIAL_ENTRIES`（唯一事实源）
   在**数量与身份**上完全一致
2. 白名单里的正式入口**真实可用**
3. 根目录新增的 `__main__` 文件**必须**在清单里被提到（防悄悄冒出新入口）
4. 权威交接文档 `AGENTS.md` 存在

## 白名单变更留痕

原断言为「**恰好 2 个**」，注释写着「收敛的意思是少，不是多」。
2026-10-15 经用户拍板扩为 **3 个**（新增 **E3** `augment.cli`），理由：

- E3 与 E1/E2 同属**确定性、可重复调用**的正式能力；
- 但 E3 **不产出结论**，只产出旁注（`claim_tier` 恒为 `non-evidence`）；
- 生产侧**默认关闭**，且失败隔离（不改 E1 退出码）；
- 隔离契约见 `augment/__init__.py` 与 `CODE_WIKI/08` 篇。

> **改守卫本身也必须写明理由** —— 这是「守卫的守卫」纪律的延伸。
> 若日后要再扩白名单，请先在此处补一段同等的理由说明。

## 已知局限

- 本测试只管「根目录入口」与「本文件提到的脚本是否存在」；
  `scripts/` 下**每个**脚本被逐份分类由 `tests/test_scripts_registry.py` 覆盖
  （2026-10-18 之前此处写的是「逐个登记成本高于收益」—— 那个判断错了：
  成本是一次性的，收益是「谁在用」从猜变成查）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "ENTRYPOINTS.md"

#: 正式入口白名单（§二）—— **唯一事实源**，顺序即 E 编号顺序。
#: (E 编号, 入口)。想新增必须同时改这里与 ENTRYPOINTS.md §二，并写明理由。
OFFICIAL_ENTRIES = (
    ("E1", "tdx_native.run_daily"),
    ("E2", "run_ci.py"),
    ("E3", "augment.cli"),
)


def _entry_text() -> str:
    if not ENTRY.exists():
        pytest.fail("ENTRYPOINTS.md 缺失")
    return ENTRY.read_text(encoding="utf-8")


def test_entrypoints_doc_exists():
    assert ENTRY.is_file(), "ENTRYPOINTS.md 缺失"


def test_declared_entries_match_whitelist():
    """§二 列出的 E 编号必须与 OFFICIAL_ENTRIES 在**数量与身份**上一致。

    原形态断言「恰好 2 个」（「收敛的意思是少，不是多」）。扩为 3 个的理由
    已写在模块 docstring「白名单变更留痕」一节 —— 改守卫也要留痕。
    """
    text = _entry_text()
    # 在 §二 节里数 E 标记
    m = re.search(r"## 二、正式入口.*?(?=\n## )", text, re.S)
    assert m, "找不到 §二 正式入口节"
    ids = re.findall(r"\*\*(E\d+)\*\*", m.group(0))
    expected = [eid for eid, _ in OFFICIAL_ENTRIES]
    assert ids == expected, (
        f"§二 实际列出 {ids}，白名单为 {expected}\n"
        "→ 数量与身份都必须一致。想新增正式入口，"
        "先改 OFFICIAL_ENTRIES 并在模块 docstring 写明理由。")


def test_official_entries_exist():
    """白名单里的正式入口必须真实可用。"""
    import importlib
    for eid, entry in OFFICIAL_ENTRIES:
        if entry.endswith(".py"):
            assert (ROOT / entry).is_file(), f"{eid} {entry} 不存在"
            continue
        try:
            importlib.import_module(entry)
        except Exception as exc:                          # noqa: BLE001
            pytest.fail(f"{eid} {entry} 不可导入: {type(exc).__name__}: {exc}")


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


def test_listed_scripts_exist():
    """⚠️ 本文件提到的每个 `scripts/*.py` 必须**真实存在**。

    2026-10-18 发现 §三 登记了 **3 个从未存在**的脚本
    （`run_w1_split.py` / `run_portfolio_ab.py` / `run_adx_*`），
    存在了数周无人发现 —— 因为「登记」只是往表格写个名字，
    **没有任何守卫去核文件是否存在**。这与 `reports/` 白名单制同型：
    记账与实物脱钩，而所有检查都只看记账。

    历史注记里的删除线（`~~...~~`）不算「提到」—— 那是**已修正**的记录。
    """
    text = re.sub(r"~~.*?~~", "", _entry_text(), flags=re.S)
    refs = sorted(set(re.findall(r"scripts/([A-Za-z0-9_]+)\.py", text)))
    missing = [r for r in refs if not (ROOT / "scripts" / f"{r}.py").is_file()]
    assert missing == [], (
        "ENTRYPOINTS.md 引用了不存在的脚本（幽灵条目）:\n  " + "\n  ".join(missing))


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
