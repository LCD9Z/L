# -*- coding: utf-8 -*-
"""实验状态自动校验（整改清单 P1-1）。

## 验收标准

> **预注册、结果、判决、撤回状态一致。**

## 防什么

项目一半以上资产是**负结论**，而负结论的价值**完全依赖状态可判**：
- 若预注册写「已执行」却没有对应产物 → **结论无证据支撑**
- 若预注册写「待执行」却已有判决 → **判决来源不明**
- 若产物/判决已变而预注册状态没更新 → **文档与事实脱钩**

这些都不会报错，只会**静默腐烂** —— 与「报告与证据脱钩」同类。

## 本守卫的做法

对每份 `*_PREREG*.md`：

1. 读其「状态」字段（表格首行的 `| **状态** | ... |`）
2. 按状态给出**必须满足的条件**：
   - `已执行` / `已完成` → 必须有对应产物或判决
   - `待执行` / `提案` → **不得**有判决（否则来源不明）
   - 含「撤回」→ 必须写明撤回理由
3. 不一致即失败

## 已知局限（如实记录）

- 本守卫**只校验「有/无」**，不校验产物内容与预注册假设是否对应
  （那需要语义理解，超出机械校验范围）
- 「对应产物」的判定用**文件名关键词**，非精确映射；
  若某预注册的产物名与预注册名差异很大，会误报 —— 误报时
  **应在预注册里显式写明产物路径**，而非放宽守卫
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 状态 → 是否要求有产物/判决
REQUIRES_ARTIFACT = ("已执行", "已完成", "执行完毕", "已判决")
#: 状态 → 是否禁止有判决
FORBIDS_VERDICT = ("待执行", "待确认", "提案", "草稿", "待对方确认")


def _preregs() -> list[Path]:
    return sorted(ROOT.glob("*_PREREG*.md"))


def _status(text: str) -> str:
    """从预注册文档提取状态。

    ⚠️ 实测格式（2026-10-12）：本项目的预注册用
    `> **登记时间**：...　**状态**：待执行`（**粗体 + 全角冒号**），
    **不是表格**。初版正则按表格写，18 份全部匹配不到。
    """
    # 主格式：**状态**：xxx（值可被 ** 包裹，两侧文档两种变体都存在 ——
    # 2026-10-14 A2 兼容：原正则 `[^\n|*]+` 解析不了 `**状态**：**值**`，
    # 曾把 6 份有状态字段的预注册误判为「缺状态」）
    #
    # ⚠️ 2026-10-15 回归修复（A2 合并引入）：
    # A2 兼容版写成 `\**([^\n|*]+?)\**` —— 捕获组**非贪婪**且尾部 `\**` **可匹配 0 个
    # 星号**，于是捕获组只吃 1 个字符：「已完成（…）」→「已」。
    # 而判定用的是 `any(k in st for k in REQUIRES_ARTIFACT)`，
    # `"已执行" in "已"` = False → **9 份「已执行/已完成」预注册全部逃过产物校验**，
    # 本测试文件的核心守卫**静默失效**（坏正则判定需产物 0 份 vs 修复后 9 份）。
    # 修法：先**可选**吃掉包裹用的开头 `**`，再用**贪婪** `[^\n|*]+`。
    m = re.search(r"\*\*状态\*\*\s*[：:]\s*(?:\*\*)?([^\n|*]+)", text)
    if m:
        return m.group(1).strip().rstrip("。;；")
    # 表格格式（少数文档用）
    m2 = re.search(r"\|\s*\*\*状态\*\*\s*\|\s*([^|]+)\|", text)
    if m2:
        return m2.group(1).strip()
    return ""


def _has_verdict(name: str) -> bool:
    """是否存在对应判决文档（按关键词）。"""
    stem = name.replace("_PREREG", "").replace("_PREREG_", "_")
    for pat in (f"{stem}_VERDICT.md", f"{stem.replace('_PREREG','')}_VERDICT.md"):
        if (ROOT / pat).exists():
            return True
    # 也查 reports/ 子目录
    return any(stem.split("_")[0].lower() in p.name.lower()
               for p in ROOT.glob("reports/**/*VERDICT*.md"))


def test_prereegs_exist():
    assert _preregs(), "未找到任何 *_PREREG*.md（守卫失效）"


def test_status_parser_handles_all_known_variants():
    """⚠️ 守卫的守卫：`_status` 不得被回归（2026-10-15 补）。

    A2 合并曾引入非贪婪正则，把「已完成（…）」截成「已」，
    使 `test_executed_prereegs_have_artifacts` 静默失效（需产物 0 份 vs 实际 9 份）。
    本用例钉死四种已知写法，防止同类回归再次无声发生。
    """
    cases = [
        ("> **状态**：已完成（2026-10-13 出结果）", "已完成（2026-10-13 出结果）"),
        ("> **状态**：**已执行**", "已执行"),
        ("> **状态**：已执行 —— 判决见 X_VERDICT.md", "已执行 —— 判决见 X_VERDICT.md"),
        ("| **状态** | 已执行 |", "已执行"),
        ("> **状态**：待执行", "待执行"),
    ]
    bad = []
    for text, expected in cases:
        got = _status(text)
        if got != expected:
            bad.append(f"{text!r} -> {got!r}（应 {expected!r}）")
    assert bad == [], ("_status 解析回归：\n  " + "\n  ".join(bad))


def test_status_parser_does_not_truncate_to_one_char():
    """截断成单字符会让 `k in st` 恒 False —— 产物校验被整片跳过。"""
    st = _status("> **状态**：已完成（2026-10-13 出结果）")
    assert len(st) >= 3, f"状态被截断为 {st!r}（长度 {len(st)}）"
    assert any(k in st for k in REQUIRES_ARTIFACT), (
        f"状态 {st!r} 未命中 REQUIRES_ARTIFACT —— 产物校验将被跳过")


def test_executed_prereegs_have_artifacts():
    """⚠️ 核心：状态为「已执行」的预注册必须有对应判决/产物。"""
    problems = []
    for p in _preregs():
        text = p.read_text(encoding="utf-8", errors="replace")
        st = _status(text)
        if not st:
            continue                                # 无状态字段的另项处理
        if any(k in st for k in REQUIRES_ARTIFACT):
            if not _has_verdict(p.stem):
                problems.append(f"{p.name}: 状态=「{st}」但无对应判决/产物")
    assert problems == [], ("以下预注册声称已执行却无证据：\n  "
                            + "\n  ".join(problems))


def test_pending_prereegs_have_no_verdict():
    """状态为「待执行」的预注册不得有判决（否则判决来源不明）。"""
    problems = []
    for p in _preregs():
        text = p.read_text(encoding="utf-8", errors="replace")
        st = _status(text)
        if not st:
            continue
        if any(k in st for k in FORBIDS_VERDICT) and "撤回" not in st:
            if _has_verdict(p.stem):
                problems.append(f"{p.name}: 状态=「{st}」却已存在判决")
    assert problems == [], ("以下预注册状态与判决矛盾：\n  "
                            + "\n  ".join(problems))


def test_retracted_prereegs_state_reason():
    """撤回必须写明理由（不接受无声撤回）。"""
    problems = []
    for p in _preregs():
        text = p.read_text(encoding="utf-8", errors="replace")
        st = _status(text)
        if st and ("撤回" in st or "作废" in st):
            # 撤回的预注册须在正文说明理由
            if not re.search(r"撤回|作废", text[text.find(st):] if st in text else text):
                problems.append(f"{p.name}: 状态为撤回但正文无说明")
            # 且不得同时声称「已执行」
            if any(k in st for k in REQUIRES_ARTIFACT):
                problems.append(f"{p.name}: 状态同时含撤回与已执行（矛盾）")
    assert problems == [], ("撤回状态不自洽：\n  " + "\n  ".join(problems))


def test_all_prereegs_have_status_field():
    """每份预注册都必须有状态字段（否则无法机械校验）。"""
    missing = [p.name for p in _preregs()
               if not _status(p.read_text(encoding="utf-8", errors="replace"))]
    assert missing == [], f"以下预注册缺状态字段（请补，否则无法自动校验）: {missing}"
