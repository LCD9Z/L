"""同族产物结构审计的守卫（`scripts/audit_family_schema.py`）。

**为什么需要**：`decay_h5/h10/h20` 的「同名不同物」是 2026-10-15 A2 合并时
**偶然撞上**的（主干 1500 只 / 10 键 vs 副本 400 只 / 4 键）。这类问题
会让报告引用到**根本不是同一实验**的数字，且不报错。本守卫把它变成常驻检查。

**含反向验证**（本项目纪律：改守卫/加守卫必须证明它真能抓到问题）：
`test_audit_can_still_detect_known_case` 断言脚本对已知的 `decay` 仍能识别出
2 种结构 —— 否则这个审计就是「永远返回 0」的假守卫。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "audit_family_schema", ROOT / "scripts" / "audit_family_schema.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def test_family_strips_variant_suffixes():
    """族名规则：窗口日期 / 期限 / 批次后缀都要剥掉，但 `.json` 扩展名先剥。"""
    cases = {
        "decay_h5.json": "decay",
        "decay_h5_ic.json": "decay",
        "decay_h60.json": "decay",
        "combo_study_h20_2023-07-03.json": "combo_study",
        "tc_t1_p2.json": "tc_t1",
        "ab_n3_batchA.json": "ab_n3",
        "five_factor_ab_v2.json": "five_factor_ab",
    }
    bad = []
    for name, expected in cases.items():
        got = audit.family_of(name)
        if got != expected:
            bad.append(f"{name} -> {got!r}（应 {expected!r}）")
    assert bad == [], ("族名规则回归：\n  " + "\n  ".join(bad))


def test_no_unknown_family_divergence():
    """当前仓库不得存在**未解释**的同族结构不一致。"""
    groups = audit.collect(include_recalc=False)
    assert groups, "未扫到任何产物族 —— 审计可能失明"
    bad = audit.report(groups, show_all=False)
    assert bad == 0, (
        "存在未解释的同族结构不一致：逐一判断是「同名不同物」还是正常演进；"
        "若确属已知，须在 KNOWN_DIVERGENCE 写明原因与出处（不可静默加白）")


def test_audit_can_still_detect_known_case():
    """⚠️ 反向验证：脚本必须仍能识别 `decay` 的 2 种结构。

    否则审计退化成「永远返回 0」的假守卫（本项目反复栽过的静默失效形态）。
    """
    groups = audit.collect(include_recalc=False)
    decay = groups.get("decay", [])
    assert len(decay) >= 2, f"decay 族份数异常：{len(decay)}"
    n_schema = len({keys for _, keys in decay})
    assert n_schema == 2, (
        f"decay 族结构数 = {n_schema}（应 2）—— 要么产物被意外统一，"
        "要么审计的键提取失明，两者都需人工确认")


def test_known_divergence_entries_have_reason():
    """白名单不得只有族名没有理由（否则成了「藏问题」的工具）。"""
    for fam, reason in audit.KNOWN_DIVERGENCE.items():
        assert reason and len(reason) >= 20, f"{fam} 的白名单理由过短/缺失"
