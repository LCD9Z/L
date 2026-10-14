# -*- coding: utf-8 -*-
"""成本口径待重算登记册守卫（`COST_BASELINE_PENDING_RECOMPUTE.md`）。

背景：`backtest_engine._stamp_rate` 印花税分段失效（2026-10-14 两侧独立发现），
受影响产物在重算前**不得作为有效结论引用**。登记册是这条纪律的载体 ——
本测试锁两件事，防它变成一纸空文：

1. 册内列出的每个产物**必须真实存在**（防产物被改名/删除而册子还挂着旧名单）；
2. 册子必须**显式声明**「只标注、不改数字」与解除条件（防纪律被悄悄删掉）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGISTER = ROOT / "COST_BASELINE_PENDING_RECOMPUTE.md"


def test_register_exists_and_states_discipline():
    assert REGISTER.exists(), "成本口径待重算登记册缺失（缺陷未归档）"
    src = REGISTER.read_text(encoding="utf-8")
    for needle in ("只标注、不改任何数字", "不得作为有效结论引用", "解除条件"):
        assert needle in src, f"登记册缺纪律声明: {needle!r}"


def test_every_listed_product_exists():
    """册内 `reports/xxx.json` 路径必须都在磁盘上（防名单与实况漂移）。"""
    src = REGISTER.read_text(encoding="utf-8")
    listed = sorted(set(re.findall(r"`(reports/[A-Za-z0-9_./-]+\.json)`", src)))
    assert listed, "登记册未列出任何产物（异常：缺陷应至少影响 1 份）"
    missing = [p for p in listed if not (ROOT / p).exists()]
    assert missing == [], f"登记册列出的产物不存在（名单已漂移）: {missing}"


def test_register_records_both_sides_independent_discovery():
    """双向印证是本缺陷定性的依据，须留痕（含两侧 commit）。"""
    src = REGISTER.read_text(encoding="utf-8")
    assert "8b3cba8" in src, "缺主干侧独立发现的 commit"
    assert "755212c" in src, "缺副本侧独立发现的 commit"
