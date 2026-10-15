# -*- coding: utf-8 -*-
"""augment — A 线（LLM 母体）作为**可选增强模块**的隔离容器。

⚠️ 隔离红线（设计见 CODE_WIKI/08 篇 §二、§六，与本包同效力）

1. **单向只读**：只读 ``reports/`` 与 ``data/``；**只写** ``reports/augment/``。
2. **claim_tier 强制**：所有落盘产物恒为 ``"non-evidence"`` ——
   ``contract.AugmentNote`` 以 ``ClassVar`` 表达，调用方**结构上**无法传入其他值。
3. **不进裁决链**：``release_gate.py`` / ``validation/`` / 任何 ``*_VERDICT.md`` /
   ``tracking.csv`` 不得使用本包产物。
4. **失败隔离**：本包任何异常都不得改变生产链（E1 ``run_daily``）的退出码。
5. **入口**：只经 E3（``python -m augment.cli``）调用；生产侧默认关闭。

本包**不产出结论**，只产出旁注。它存在的意义是给 A 线（LLM）能力一个
**有界的正式角色**，而不是让 LLM 进入选股或裁决。
"""

from __future__ import annotations

__all__ = ["contract"]
