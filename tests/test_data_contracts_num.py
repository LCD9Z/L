# -*- coding: utf-8 -*-
"""``data_contracts.to_float_or_none`` —— 数值列解析的**唯一标准实现**守卫。

背景（CODE_REDUNDANCY_AUDIT P1，2026-10-13 落地）：此前 10 个模块各自实现
``_num``：5 个过滤 NaN、5 个不过滤 → 同一条 NaN 在因子引擎当缺失、在估值
模块当数值，**且不报错**（「静默失效」类别）。现全部替换为本标准。

本测试锁两件事：
  1. 标准语义本身（每个边界一例）；
  2. **10 个消费模块的 ``_num`` 全部同一指向标准**（防止有人再写本地变体）。
"""
from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path
from typing import Any, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_contracts import to_float_or_none  # noqa: E402

# 原 10 处本地实现的位置（审计报告 §4.1 逐条列出）
_NUM_SITES: List[str] = [
    "factors.factor_gate",
    "factors.factor_validation",
    "stage2.stage2_ablation",
    "stage2.stage2_scoring",
    "ashare.ashare_cross_section",
    "ashare.ashare_event_engine",
    "risk.valuation_weight",
    "fetch.fundamentals_source",
    "pit.pit_fundamentals",
    "pit.pit_quarterly",
]


@pytest.mark.parametrize(
    ("raw", "expect"),
    [
        (None, None),                       # None
        ("", None),                         # 空串
        ("   ", None),                      # 纯空白（strip 后为空）
        ("-", None),                        # 东财占位
        ("--", None),                       # 东财占位（业绩报表常见）
        ("None", None),                     # 字符串化的 None
        ("nan", None),                      # 字符串化的 NaN（大小写均拒）
        ("NaN", None),
        ("abc", None),                      # 非数值
        ("1.2.3", None),                    # 伪数值
        ([], None),                         # 容器转 str 后非数值
        (float("nan"), None),               # ⚠️ NaN 必须过滤（本测试存在的理由）
        (float("inf"), math.inf),           # inf 不过滤：显式计算结果，由消费方处置
        (3, 3.0),
        (3.5, 3.5),
        ("3.5", 3.5),
        (" 3.5 ", 3.5),                     # 空白容忍
        ("1,234.5", 1234.5),                # 千分位逗号（东财列的现实格式）
        ("-2", -2.0),                       # 负号数字 ≠ 占位 "-"
        ("-2.5%", None),                    # 百分号不解析（非数值列由消费方处理）
    ],
)
def test_to_float_or_none_standard_semantics(raw: Any, expect: Any):
    got = to_float_or_none(raw)
    if expect is None:
        assert got is None, f"{raw!r} 应解析为 None（不补造），实得 {got!r}"
    else:
        assert got is not None and math.isclose(got, expect), f"{raw!r} → {got!r}，期望 {expect!r}"


def test_to_float_or_none_bool_is_numeric():
    """bool 是 int 子类：True→1.0（与 float(True) 一致，不做特殊政策）。"""
    assert to_float_or_none(True) == 1.0
    assert to_float_or_none(False) == 0.0


@pytest.mark.parametrize("module_name", _NUM_SITES)
def test_module_num_is_the_standard(module_name: str):
    """⚠️ 每个原 ``_num`` 站点必须**同一指向**标准实现（identity，非等价）。"""
    mod = importlib.import_module(module_name)
    assert mod._num is to_float_or_none, (
        f"{module_name}._num 不再是 data_contracts.to_float_or_none —— "
        "本地变体正是『同一条 NaN 两种处置』静默失效的根源（审计 P1）"
    )


def test_all_num_sites_covered_by_test():
    """防站点清单与仓库现实漂移：仓库内不得再出现本地 ``def _num(``。

    ⚠️ 模式用拼接（``"def _num" + "("``）避免匹配到本测试自身的字符串字面量；
    ⚠️ ``_num_or_blank`` 是**输出格式化**函数（run_pit_snapshot_ingest），
    与本标准的**解析**语义不同，不在收敛范围。
    """
    import subprocess

    # --exclude 自身：本文件的 docstring/字面量含模式串，不排除会自匹配
    out = subprocess.run(
        ["grep", "-rn", "def _num" + "(", "--include=*.py",
         "--exclude=test_data_contracts_num.py", "."],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert out.stdout.strip() == "", f"仍有本地 _num 定义:\n{out.stdout}"
