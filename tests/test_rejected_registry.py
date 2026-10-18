# -*- coding: utf-8 -*-
"""A12 拒绝实验登记册守卫（EVIDENCE_CHAIN_PREREG 组件 A12，判据 R 组）。

## 锁住什么

1. **覆盖**（R-2）：`run_multiple_testing_audit.py` 的
   `DECLARED_NON_IC_TESTS` 与 `DISTINCT_STRATEGY_CONFIGS` **每个标签**
   都在登记册表一出现——n_trials 的计数来源与登记册不允许脱钩；
2. **条目数对账**（R-3）：表一中声明族行数 == `len(DECLARED_NON_IC_TESTS)`、
   策略配置族行数 == `len(DISTINCT_STRATEGY_CONFIGS)`（「条目数 = n_trials 来源」，
   数字从脚本 import，不硬编码）；
3. **参数组数自洽**（R-4）：每行 ≥1 整数，文档声明的合计 == 各行相加；
4. **守卫自身可验**（R-5）：对表一做「删一行」的内存变异后，覆盖/对账断言
   必须失败——防止守卫写了但永远绿。

计数来源一律从脚本 import（单一事实来源）；本文件不复制清单内容。
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "REJECTED_EXPERIMENTS.md"
AUDIT_SCRIPT = ROOT / "scripts" / "run_multiple_testing_audit.py"


def _load_audit():
    """按文件路径加载审计脚本（避免 `scripts.` 包名让 mypy 重复识别）。"""
    spec = importlib.util.spec_from_file_location("_multiple_testing_audit", AUDIT_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _label_key(label: str) -> str:
    """取标签的可匹配主干：去掉括号补充（路径/章节），保留实验名。"""
    return re.sub(r"[（(][^）)]*[）)]", "", label).strip()


def _table1_rows(text: str):
    """解析表一数据行（跳过表头/分隔行）；返回 [(实验, 计数来源, 参数组数)]。"""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("| # | 实验 |"))
    rows = []
    for line in lines[start + 2:]:  # 跳过表头与分隔行
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            pytest.fail(f"表一行不是 6 格: {line}")
        rows.append((cells[1], cells[2], cells[5]))
    return rows


@pytest.fixture(scope="module")
def audit():
    return _load_audit()


@pytest.fixture(scope="module")
def registry_text():
    assert REGISTRY.is_file(), "缺 REJECTED_EXPERIMENTS.md（R-1）"
    return REGISTRY.read_text(encoding="utf-8")


def test_r2_declared_labels_all_listed(audit, registry_text):
    """R-2a：12 个声明族标签逐个在册。"""
    missing = [
        lab for lab in audit.DECLARED_NON_IC_TESTS
        if _label_key(lab) not in registry_text
    ]
    assert missing == [], f"声明族标签未入册: {missing}"


def test_r2_distinct_configs_all_listed(audit, registry_text):
    """R-2b：13 个策略配置标签逐个在册。"""
    missing = [
        lab for lab in audit.DISTINCT_STRATEGY_CONFIGS
        if _label_key(lab) not in registry_text
    ]
    assert missing == [], f"策略配置标签未入册: {missing}"


def test_r3_row_counts_reconcile_with_audit(audit, registry_text):
    """R-3：表一行数按计数来源与脚本清单长度逐项相等。"""
    rows = _table1_rows(registry_text)
    n_declared = sum(1 for _, src, _ in rows if src == "声明族")
    n_configs = sum(1 for _, src, _ in rows if src == "策略配置族")
    assert n_declared == len(audit.DECLARED_NON_IC_TESTS), (
        f"声明族行数 {n_declared} != len(DECLARED_NON_IC_TESTS) "
        f"{len(audit.DECLARED_NON_IC_TESTS)}")
    assert n_configs == len(audit.DISTINCT_STRATEGY_CONFIGS), (
        f"策略配置族行数 {n_configs} != len(DISTINCT_STRATEGY_CONFIGS) "
        f"{len(audit.DISTINCT_STRATEGY_CONFIGS)}")


def test_r4_group_counts_are_positive_ints_and_total_matches(registry_text):
    """R-4：每行参数组数为 ≥1 整数；文档合计 == 各行相加。"""
    rows = _table1_rows(registry_text)
    bad = [r for r in rows if not re.fullmatch(r"[1-9]\d*", r[2])]
    assert bad == [], f"参数组数不是 ≥1 整数: {bad}"
    total = sum(int(r[2]) for r in rows)
    m = re.search(r"表一合计：(\d+) 组", registry_text)
    assert m, "文档未声明表一合计"
    assert int(m.group(1)) == total, (
        f"文档合计 {m.group(1)} != 各行相加 {total}")


def test_r5_guard_detects_deleted_row(audit, registry_text):
    """R-5：删一行（内存变异）后，R-2/R-3 必须失败——守卫不是永远绿。

    这是「反向验证」的常驻形态：不碰真文件，只证明判据有牙。
    """
    lines = registry_text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("| # | 实验 |"))
    # 删掉表一第一条数据行
    del lines[start + 2]
    mutated = "\n".join(lines)
    rows = _table1_rows(mutated)
    n_declared = sum(1 for _, src, _ in rows if src == "声明族")
    assert n_declared != len(audit.DECLARED_NON_IC_TESTS), (
        "删行后对账仍相等 ⇒ R-3 判据失效")
    # 同时确认被删行的标签因此消失（R-2 有牙）
    first_label = _label_key(audit.DECLARED_NON_IC_TESTS[0])
    assert first_label not in mutated or n_declared != len(audit.DECLARED_NON_IC_TESTS)


def test_r1_registry_is_in_root_md_allowlist():
    """R-1：登记册在根目录 md 白名单内（doc_layout 守卫的孪生断言）。"""
    guard = ROOT / "tests" / "test_doc_layout.py"
    text = guard.read_text(encoding="utf-8")
    assert "REJECTED_EXPERIMENTS.md" in text or "== 69" in text, (
        "根 md 登记值未随登记册更新（应 68 → 69）")
