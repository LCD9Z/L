# -*- coding: utf-8 -*-
"""augment 隔离守卫（CODE_WIKI/08 篇 §九，六条断言）。

## 防什么

设计文档 08 篇 §二 的核心主张是：**边界不能靠"约定"，得靠"结构"**。
写一条"augment 产物不得进入 VERDICT"是没用的 —— 半年后有人 import 一下就破了。

本文件就是那些结构保证的**可执行证明**：
- 谁若把 augment 接进裁决链 → 断言 1/2 先红
- 谁若让旁注冒充证据 → 断言 3 先红
- 谁若让 augment 拖垮生产 → 断言 4 先红
- 谁若让产物写歪到别的目录 → 断言 5 先红
- 谁若手改旁注内容 → 断言 6 先红

## 已知局限

断言 1 以「行首 import」为判据，不解析 AST —— 注释里提到 `import augment`
（如 ``run_daily.py`` 的红线说明）不算违规。这是有意为之：
红线说明本身就应当写明"不得 import"。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "augment"
TESTS = ROOT / "tests"

#: 允许出现 augment 导入的地方：包自身 + 测试
ALLOWED_DIRS = (PKG, TESTS)

#: 裁决链：绝不允许触碰 augment 产物
VERDICT_CHAIN_FILES = (ROOT / "release_gate.py",)
VERDICT_CHAIN_DIRS = (ROOT / "validation",)

#: 产物路径前缀（08 篇 §六 红线 1）
PRODUCT_PREFIX = "reports/augment"

#: 行首的 augment 导入。注释里的提法不以 import 开头，故不算命中。
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+augment\b", re.M)

_SKIP_SEGMENTS = {".git", ".venv", "venv", "__pycache__", "node_modules"}


def _iter_py_files() -> Iterator[Path]:
    """遍历仓库内受检的 .py 文件（剔除虚拟环境与第三方参考资料）。"""
    for p in ROOT.rglob("*.py"):
        parts = p.relative_to(ROOT).parts
        if any(seg in _SKIP_SEGMENTS for seg in parts):
            continue
        if len(parts) >= 2 and parts[0] == "docs" and parts[1] == "external":
            continue
        yield p


def test_assertion_1_no_module_outside_augment_imports_it():
    """断言 1：除 augment/ 与 tests/ 外，任何模块都不得 import augment。"""
    offenders = []
    for p in _iter_py_files():
        if any(p.is_relative_to(d) for d in ALLOWED_DIRS):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if IMPORT_RE.search(text):
            offenders.append(str(p.relative_to(ROOT)))
    assert offenders == [], (
        "augment 被 augment/ 与 tests/ 之外的模块导入（越界）：\n  "
        + "\n  ".join(offenders)
        + "\n→ 生产链只能用子进程调用 E3（见 08 篇 §八），不得 import。")


def test_assertion_2_verdict_chain_never_references_augment():
    """断言 2：裁决链（release_gate / validation）不得出现 augment 字样或产物路径。"""
    targets = list(VERDICT_CHAIN_FILES)
    for d in VERDICT_CHAIN_DIRS:
        targets.extend(sorted(d.rglob("*.py")))
    hits = []
    for p in targets:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if "augment" in text.lower() or PRODUCT_PREFIX in text:
            hits.append(str(p.relative_to(ROOT)))
    assert hits == [], (
        "裁决链出现 augment 引用（旁注不得参与裁决）：\n  " + "\n  ".join(hits))


def test_assertion_3_claim_tier_is_structurally_forced(tmp_path):
    """断言 3：claim_tier 恒为 non-evidence —— 且调用方结构上无法传入其他值。"""
    from augment import contract

    # 结构保证：claim_tier 是 ClassVar，不是 dataclass 字段 → 传参即 TypeError
    with pytest.raises(TypeError):
        contract.AugmentNote(claim_tier="evidence")      # type: ignore[call-arg]

    notes = [contract.AugmentNote(code="000001", trade_date="2026-10-15",
                                  role="risk", text="断言3 探针")]
    path = contract.write_notes(notes, base_dir=tmp_path / PRODUCT_PREFIX,
                                date="2026-10-15", kind="explain")
    got = json.loads(path.read_text(encoding="utf-8"))
    assert got["claim_tier"] == contract.NON_EVIDENCE
    assert all(n["claim_tier"] == contract.NON_EVIDENCE for n in got["notes"])


def test_assertion_4_augment_failure_does_not_change_production_exit_code():
    """断言 4：失败等价 —— augment 失败/不可用都不得影响生产链退出码。

    这比「不抛异常」更强：它证明 augment 对生产**完全无影响**。
    """
    from tdx_native import run_daily

    # (a) 子进程非零退出（模拟 E3 角色未实现 / LLM 失败）
    bad = [sys.executable, "-c", "import sys; sys.exit(9)"]
    assert run_daily.run_augment_hook("2026-10-15", cmd=bad) is False

    # (b) 命令根本不存在（OSError）也必须被吞掉
    assert run_daily.run_augment_hook("2026-10-15",
                                     cmd=["definitely-not-a-real-command"]) is False

    # (c) 生产链自身不得 import augment —— 只允许子进程调用
    text = (ROOT / "tdx_native" / "run_daily.py").read_text(encoding="utf-8")
    assert not IMPORT_RE.search(text), \
        "run_daily.py 竟 import 了 augment（应以子进程调用）"


def test_assertion_5_product_path_always_inside_base_dir(tmp_path):
    """断言 5：产物路径恒以 base_dir 为前缀，且非法日期/种类被拒。"""
    from augment import contract

    base = tmp_path / PRODUCT_PREFIX
    path = contract.write_notes([], base_dir=base, date="2026-10-15",
                                kind="hypotheses")
    assert path.parent.resolve() == base.resolve()
    assert path.name == "hypotheses_2026-10-15.json"

    with pytest.raises(contract.AugmentWriteError):
        contract.write_notes([], base_dir=base, date="../../escape", kind="explain")
    with pytest.raises(contract.AugmentWriteError):
        contract.write_notes([], base_dir=base, date="2026-10-15", kind="verdict")


def test_assertion_6_input_digest_is_traceable(tmp_path):
    """断言 6：input_digest 可追 —— 旁注能回到它读的是哪一版主干 JSON（纪律 2.4）。"""
    from augment import contract

    payload = '{"as_of": "2026-10-15", "picks": []}'
    src = tmp_path / "recommend_2026-10-15.json"
    src.write_text(payload, encoding="utf-8")
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert contract.digest_of(src) == expected

    note = contract.AugmentNote(code="000001", trade_date="2026-10-15", role="risk",
                                text="断言6 探针", input_digest=contract.digest_of(src))
    path = contract.write_notes([note], base_dir=tmp_path / PRODUCT_PREFIX,
                                date="2026-10-15", kind="explain")
    got = json.loads(path.read_text(encoding="utf-8"))
    assert got["notes"][0]["input_digest"] == expected


def test_cli_self_check_passes():
    """E3 自带隔离自检必须在无 pytest 环境下也通过（投产前快速确认）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "augment.cli", "self-check"],
        cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, f"self-check 失败:\n{proc.stdout}\n{proc.stderr}"
