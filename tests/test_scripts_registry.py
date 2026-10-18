# -*- coding: utf-8 -*-
"""脚本注册表守卫（A2）—— 防 `scripts/` 变成第二个「静默失效面」。

## 防什么

`reports/` 那个坑的形态是：**新建子目录不补白名单 → 文件永远不入库**，
而所有测试都只从磁盘读文件 → **全部通过**，谁也发现不了。

`scripts/` 是**同型**的：新增脚本没有守卫会问「你登记了吗」，
废弃脚本也没有机制会被标记。`ENTRYPOINTS.md` §6.2 曾用**命名规则**
（「名字含 build_/migrate_ 且不在 §二~§五 → 默认一次性」）代替逐份清单 ——
规则覆盖不到的 `run_*` 部分，谁在用完全靠猜。

本守卫把「谁在用」从**猜**变成**查**：

1. `scripts/` 下每个 `.py` **必须**在 `scripts/REGISTRY.md` 里有且只有一行
2. 注册表里**不许有幽灵条目**（指向不存在的文件）
3. 状态只能是 `active` / `one-off` / `deprecated`
4. 状态必须与**自动判据**一致（用生成器的 `collect()` 重算，不靠人工印象）
5. 全文必须与 `render(collect())` 逐字节一致 —— 改了脚本就重生成
6. `deprecated` 的依据必须能在**那篇文档里真的检索到**
7. 非 `_` 前缀的脚本必须有 `__main__` 守卫（否则 import 即执行）

## 为什么比对全文而不是只比对状态

只校验状态的话，`被谁调用` / `入口` 两列会静默腐坏（生成时算对了，
但后来引用关系变了没人重跑）。全文比对失败信息明确：跑一次生成器即可。

## 已知局限

- **不判断「这个脚本该不该删」** —— 注册表只记录与被引用，不做取舍。
  `one-off` 与零引用都不等于可删（历史凭据，删了破坏可追溯性）。
- 引用判据是**文本级**（stem 整词命中），不做 import 图分析。
  因此「同一脚本被注释掉的一段代码提到」也算 `active` —— 这是**保守方向**
  （宁可高估在用的，不可低估）。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
REGISTRY = SCRIPTS_DIR / "REGISTRY.md"
GENERATOR = SCRIPTS_DIR / "gen_scripts_registry.py"

#: 表格行：`| 12 | \`x.py\` | 职责 | 入口 | 调用 | \`status\` |`
_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([A-Za-z0-9_]+\.py)`\s*\|(.*)\|\s*`([A-Za-z-]+)`\s*\|\s*$")


def _load_generator():
    assert GENERATOR.is_file(), "scripts/gen_scripts_registry.py 缺失"
    spec = importlib.util.spec_from_file_location("gen_scripts_registry", GENERATOR)
    # mypy: spec/loader 可能为 None —— 与 test_audit_family_schema 同写法
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _registry_text() -> str:
    if not REGISTRY.is_file():
        pytest.fail("scripts/REGISTRY.md 缺失 —— 跑 python scripts/gen_scripts_registry.py")
    return REGISTRY.read_text(encoding="utf-8")


def _rows() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in _registry_text().splitlines():
        m = _ROW_RE.match(line)
        if m:
            out.append({"no": int(m.group(1)), "script": m.group(2),
                        "mid": m.group(3), "status": m.group(4)})
    return out


def test_registry_exists():
    assert REGISTRY.is_file(), "scripts/REGISTRY.md 缺失"


def test_every_script_is_registered():
    """⚠️ 核心守卫：`scripts/*.py` 每个都必须在册（防「悄悄加一个脚本」）。"""
    on_disk = {p.name for p in SCRIPTS_DIR.glob("*.py")}
    registered = {r["script"] for r in _rows()}
    missing = sorted(on_disk - registered)
    assert missing == [], (
        "以下脚本未在 scripts/REGISTRY.md 登记（新增脚本须重跑生成器）:\n  "
        + "\n  ".join(missing))


def test_no_ghost_entries():
    """注册表不许指向不存在的文件（防「删了脚本但清单没改」）。"""
    on_disk = {p.name for p in SCRIPTS_DIR.glob("*.py")}
    registered = {r["script"] for r in _rows()}
    ghosts = sorted(registered - on_disk)
    assert ghosts == [], (
        "注册表里的以下条目在 scripts/ 下已不存在:\n  " + "\n  ".join(ghosts))


def test_status_values_are_enum():
    allowed = {"active", "one-off", "deprecated"}
    bad = sorted({r["status"] for r in _rows()} - allowed)
    assert bad == [], f"非法状态值 {bad}；只允许 {sorted(allowed)}"


def test_row_numbers_are_contiguous():
    """序号必须 1..N 连续（防手工插入/删除造成错位）。"""
    nos = [r["no"] for r in _rows()]
    assert nos == list(range(1, len(nos) + 1)), f"序号不连续：{nos[:5]}...{nos[-5:]}"


def test_status_matches_auto_judgement():
    """状态必须与生成器的自动判据一致 —— 不靠人工印象。"""
    mod = _load_generator()
    auto = {r["script"]: r["status"] for r in mod.collect()}
    mismatch = {r["script"]: (r["status"], auto.get(r["script"]))
                for r in _rows() if auto.get(r["script"]) != r["status"]}
    assert mismatch == {}, (
        "注册表状态与自动判据不一致（脚本, 表内, 应为）:\n  "
        + "\n  ".join(f"{k}: {v[0]} → {v[1]}" for k, v in sorted(mismatch.items())))


def test_registry_is_byte_identical_to_generated():
    """全文一致 —— 改了脚本/引用关系就必须重生成（含「被谁调用」两列）。"""
    mod = _load_generator()
    expected = mod.render(mod.collect())
    actual = _registry_text()
    if expected != actual:
        exp_lines, act_lines = expected.splitlines(), actual.splitlines()
        n = min(len(exp_lines), len(act_lines))
        diff = [f"  L{i+1}\n    期望: {exp_lines[i]}\n    实际: {act_lines[i]}"
                for i in range(n) if exp_lines[i] != act_lines[i]][:10]
        pytest.fail(
            "scripts/REGISTRY.md 与脚本现状不一致 —— 请跑：\n"
            "    python scripts/gen_scripts_registry.py\n"
            f"行数 期望 {len(exp_lines)} / 实际 {len(act_lines)}\n"
            + "\n".join(diff))


def test_deprecated_basis_is_searchable():
    """`deprecated` 的依据必须能在**那篇文档里含脚本名的那一行**找到。

    防「凭印象标废弃」—— 和 `AGENTS.md` §11「引证须回查原文」同一条纪律。
    """
    mod = _load_generator()
    for script, (doc, needle) in mod.DEPRECATED.items():
        p = ROOT / doc
        assert p.is_file(), f"{script} 的依据文档 {doc} 不存在"
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if script in ln]
        assert lines, f"{doc} 里找不到提到 {script} 的行"
        assert any(needle in ln for ln in lines), (
            f"{doc} 提到 {script} 的行里没有「{needle}」——\n  " + "\n  ".join(lines))


def test_deprecated_status_consistency():
    """DEPRECATED 表里的脚本，若仍被判 active，说明「取代」已失效 —— 必须复核。"""
    mod = _load_generator()
    auto = {r["script"]: r for r in mod.collect()}
    for script in mod.DEPRECATED:
        row = auto.get(script)
        assert row is not None, f"{script} 不在 scripts/ 下"
        assert row["status"] == "deprecated", (
            f"{script} 标注为 deprecated，但仍被判定为 {row['status']}"
            f"（证据：{row['evidence']}）——「已被取代」的说法需要复核")


def test_non_helper_scripts_have_main_guard():
    """非 `_` 前缀的脚本必须有 `__main__` 守卫。

    没有守卫 = `import` 即执行 argparse = **既不能当模块用，也不该被当模块用**
    （2026-10-18 修了 `run_portfolio_backtest` / `run_real_data_collection` /
    `run_walk_forward` 三个）。
    """
    bad = [r["script"] for r in _rows()
           if not r["script"].startswith("_")
           and "无 `__main__`" in r["mid"]]
    assert bad == [], f"以下脚本缺 `__main__` 守卫: {bad}"
