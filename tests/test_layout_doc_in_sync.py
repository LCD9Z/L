# -*- coding: utf-8 -*-
"""守卫：`DIRECTORY_LAYOUT.md` 必须与仓库真实结构一致。

## 背景

该文档声明「由脚本自动生成、请勿手工编辑」，但生成器一度**不在仓库里**
（`git log --all -- gen_layout_doc.py` 无记录），于是它静默漂移：

- 漏掉后来新增的 `console/` 包（子包数仍写 18，实际 19）；
- 3 个数据准备脚本迁走后仍列在根目录；
- `main.py` 仍写 402 行（实际已拆为 `console/` 包）。

文档与实际结构不一致，属于本项目最警惕的**静默失效**：
读它的人会基于错误的前提做判断。因此把「一致」固化为断言。

## 口径

比对**结构指纹**（包集合、各包模块集合、根目录模块集合），**不比对行数** ——
行数随每次改动变化，纳入门禁会造成无意义的持续红。
"""
from __future__ import annotations

import gen_layout_doc


def test_layout_doc_is_in_sync_with_repository():
    """结构不一致时必须失败，并给出可操作的修复指引。"""
    diffs = gen_layout_doc.check_sync()
    assert diffs == [], (
        "DIRECTORY_LAYOUT.md 与仓库结构不同步：\n  - "
        + "\n  - ".join(diffs)
        + "\n修复：python scripts/gen_layout_doc.py"
    )


def test_layout_doc_checker_detects_drift():
    """反向守卫：指纹比对必须真的能发现差异，而不是恒真。

    做法：构造一份「缺一个包」的指纹，断言比对能报出来。
    若哪天 check 退化为空实现，这条会先失败。
    """
    expected = gen_layout_doc.structural_fingerprint()
    drifted: gen_layout_doc.LayoutFingerprint = {
        "packages": list(expected["packages"])[:-1],  # 故意去掉最后一个包
        "package_modules": dict(expected["package_modules"]),
        "root_modules": [*expected["root_modules"], "phantom_module"],
    }
    diffs = gen_layout_doc._describe_diff(expected, drifted)  # noqa: SLF001
    assert diffs, "指纹比对未能发现人为制造的差异 —— 守卫形同虚设"
    assert any("phantom_module" in d for d in diffs), (
        f"未报告多出的根目录模块，实际差异: {diffs}"
    )
