# -*- coding: utf-8 -*-
"""代码冗余基线守卫（tests/test_code_redundancy_baseline.py）。

锁住的失效：**新产生的完全重复函数体**（复制粘贴）不经评审就入库。
本测试不阻止「消除旧重复」（数量下降总是安全），只阻止**新增** ——
调高基线 = 事后放宽判定标准，须先在 ``CODE_REDUNDANCY_AUDIT.md`` 留痕。

基线（2026-10-13，commit 见报告）：
* 完全重复组数 = 13
* 同构不同值组数 = 7
审计工具：``scripts/audit_code_redundancy.py``（只读，AST 归一化）。
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audit_code_redundancy as red  # noqa: E402

#: 基线组数（2026-10-13 实测）。**下调无需测试；上调必须先在报告里留痕。**
BASELINE_EXACT_GROUPS = 13
BASELINE_ISOMORPHIC_GROUPS = 7


def _collect_or_skip() -> dict:
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(ROOT),
                       capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("非 git 工作树，跳过冗余基线守卫")
    return red.collect(ROOT)


def test_audit_collects_all_tracked_files():
    data = _collect_or_skip()
    assert data["parse_errors"] == [], "存在解析失败的 .py，须先修复再谈冗余"
    n_files = sum(v[0] for v in data["area_stats"].values())
    assert n_files >= 300, f"只解析到 {n_files} 个文件 —— 采集面缩水（静默失效）"


def test_no_new_exact_duplicate_functions():
    """⚠️ 核心守卫：完全重复组数不得超过基线（新增复制粘贴须先评审）。"""
    data = _collect_or_skip()
    groups = red.exact_duplicate_groups(data["funcs"])
    assert len(groups) <= BASELINE_EXACT_GROUPS, (
        f"完全重复组数 {len(groups)} > 基线 {BASELINE_EXACT_GROUPS}："
        "出现了新的复制粘贴。先合并/参数化，或在 CODE_REDUNDANCY_AUDIT.md "
        "留痕后上调基线（调基线=改判定标准，禁止静默进行）"
    )


def test_no_new_isomorphic_functions():
    data = _collect_or_skip()
    groups = red.isomorphic_groups(data["funcs"])
    assert len(groups) <= BASELINE_ISOMORPHIC_GROUPS, (
        f"同构不同值组数 {len(groups)} > 基线 {BASELINE_ISOMORPHIC_GROUPS}："
        "出现了新的「复制后改参数」函数，优先参数化收敛"
    )


# ---------------------------------------------------------------------------
# 归一化器本身的行为锁定（判定工具的工具）
# ---------------------------------------------------------------------------
def _parse_fn(src: str) -> ast.FunctionDef:
    tree = ast.parse(src)
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef)
    return fn


def test_normalizer_ignores_identifier_names():
    """仅变量名不同 ⇒ 归一化后同哈希（这是「完全重复」判定的前提）。"""
    a = _parse_fn("def f(a, b):\n"
                  "    total = 0\n"
                  "    for x in a:\n"
                  "        total += x * b\n"
                  "    return total\n")
    b = _parse_fn("def g(p, q):\n"
                  "    acc = 0\n"
                  "    for y in p:\n"
                  "        acc += y * q\n"
                  "    return acc\n")
    assert red.norm_dump(a, False) == red.norm_dump(b, False)


def test_normalizer_keeps_constants_in_exact_mode():
    """常量不同 ⇒ 精确口径下**不同**哈希（默认不允许「改了阈值也算重复」）。"""
    a = _parse_fn("def f(v):\n    return v > 0.005\n")
    b = _parse_fn("def f(v):\n    return v > 0.5\n")
    assert red.norm_dump(a, False) != red.norm_dump(b, False)
    assert red.norm_dump(a, True) == red.norm_dump(b, True), "同构口径应忽略常量"


def test_normalizer_strips_docstring():
    """docstring 差异不得影响重复判定。"""
    a = _parse_fn("def f(v):\n    '''文档 A。'''\n    return v + 1\n")
    b = _parse_fn("def f(v):\n    return v + 1\n")
    assert red.norm_dump(a, False) == red.norm_dump(b, False)
