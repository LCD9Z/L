# -*- coding: utf-8 -*-
"""A5 预注册偏离登记守卫（EVIDENCE_CHAIN_PREREG 组件 A5，判据 E 组）。

## 锁住什么

1. **全覆盖**（E-1）：每份 `*_PREREG*.md` 都有行首零列的 `## 偏离登记` 节，
   表头五列逐字一致；
2. **行完整**（E-2）：节内每行恰好 5 个非空单元格（`—` 是合法占位），且至少一行；
3. **真实记账**（E-3）：今天三个立项的偏离行，其关键词必须能在对应 VERDICT
   正文找到同源记录——防止「区块建好了但内容是编的」；
4. **新文件自带**（E-4）：本机制的载体预注册（EVIDENCE_CHAIN_PREREG.md）
   自己的区块非空。

## 两个实现要点（都踩过）

- 判定「节存在」必须用**行首零列**锚定：预注册正文里有代码块格式示意
  （缩进的 `## 偏离登记`），子串匹配或 `strip()` 匹配都会假跳过
  （补登脚本第一版即因此漏挂一份）。
- E-3 只覆盖今天三份。其余历史文件是「未逐份复核」债务行，
  本守卫**不**声称它们无偏离——见 VERDICT 的「证明了什么/没证明什么」。
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SECTION = "## 偏离登记"
HEADER = "| 项目 | 预注册值 | 实际值 | 理由 | 影响 |"
SEPARATOR = "|---|---|---|---|---|"

#: E-3：今天三个立项的偏离行 → (VERDICT 文件, 必须出现在 VERDICT 的关键词)
CROSSCHECK = {
    "DSR_IC_FAMILY_PREREG.md": ("DSR_IC_FAMILY_VERDICT.md", ["D:/_ext_verify"]),
    "COST_AUTHORITY_AND_EMBARGO_PREREG.md": (
        "COST_AUTHORITY_AND_EMBARGO_VERDICT.md", ["embargo_days", "零调用方"]),
    "DATA_CHANNEL_PREREG.md": ("DATA_CHANNEL_VERDICT.md", ["三批", "meta_repaired_at"]),
}


def _preregs() -> list:
    return sorted(ROOT.glob("*_PREREG*.md"))


def _section_rows(text: str):
    """取偏离登记节内的数据行（跳过表头与分隔行）；节不存在返回 None。"""
    lines = text.splitlines()
    if SECTION not in lines:
        return None
    i = lines.index(SECTION)
    rows = []
    for line in lines[i + 1:]:
        if line.startswith("## "):  # 下一个二级标题 ⇒ 节结束
            break
        if not line.startswith("|"):
            if line.strip():
                break  # 表格后紧跟非空非表内容 ⇒ 形态异常
            continue
        if line.strip() in (HEADER, SEPARATOR):
            continue
        rows.append(line)
    return rows


def test_every_prereg_has_deviation_section():
    """E-1：30 份全覆盖 + 表头逐字一致。"""
    files = _preregs()
    assert len(files) == 30, f"预期 30 份 *_PREREG*.md，实际 {len(files)}"
    missing = [f.name for f in files if _section_rows(f.read_text(encoding="utf-8")) is None]
    assert missing == [], f"以下预注册缺少 {SECTION} 节: {missing}"
    bad_header = [
        f.name for f in files
        if HEADER not in f.read_text(encoding="utf-8")
    ]
    assert bad_header == [], f"以下预注册偏离表头不符: {bad_header}"


def test_deviation_rows_are_well_formed():
    """E-2：每行恰好 5 个非空单元格；节内至少一行。"""
    bad = []
    for f in _preregs():
        rows = _section_rows(f.read_text(encoding="utf-8"))
        assert rows is not None, f"{f.name} 缺节（E-1 已覆盖，此处不应发生）"
        if not rows:
            bad.append(f"{f.name}: 节内无数据行")
        for r in rows:
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            if len(cells) != 5:
                bad.append(f"{f.name}: 行不是 5 格: {r}")
            elif any(not c for c in cells):
                bad.append(f"{f.name}: 行有空单元格: {r}")
    assert bad == [], "偏离行形态不符:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("prereg", sorted(CROSSCHECK))
def test_deviations_are_backed_by_verdict(prereg):
    """E-3：偏离行的关键词能在对应 VERDICT 找到同源记录。"""
    verdict_name, keywords = CROSSCHECK[prereg]
    verdict = ROOT / verdict_name
    assert verdict.is_file(), f"缺判定文件 {verdict_name}"
    vtext = verdict.read_text(encoding="utf-8")
    rows = _section_rows((ROOT / prereg).read_text(encoding="utf-8"))
    assert rows, f"{prereg} 偏离节为空"
    for kw in keywords:
        assert kw in vtext, f"{kw!r} 未在 {verdict_name} 中出现（偏离行无据）"


def test_self_carrying_prereg_has_nonempty_block():
    """E-4：机制载体自己的区块非空（自举）。"""
    rows = _section_rows((ROOT / "EVIDENCE_CHAIN_PREREG.md").read_text(encoding="utf-8"))
    assert rows, "EVIDENCE_CHAIN_PREREG.md 的偏离节为空（新文件必须自带）"


def test_legacy_rows_do_not_claim_no_deviation():
    """历史文件只允许「未逐份复核」行，不允许未经复核的「无偏离」断言。"""
    offenders = []
    for f in _preregs():
        if f.name in CROSSCHECK or f.name == "EVIDENCE_CHAIN_PREREG.md":
            continue
        rows = _section_rows(f.read_text(encoding="utf-8")) or []
        for r in rows:
            if "（无登记偏离）" in r:
                offenders.append(f"{f.name}: {r}")
    assert offenders == [], (
        "历史预注册不允许写未经复核的「无偏离」断言:\n  " + "\n  ".join(offenders)
    )


def test_row_count_matches_registered_deviations():
    """结构自洽：三份真实偏离文件的行数 = 各自在预注册 §三.3 登记的行数。"""
    expected = {
        "DSR_IC_FAMILY_PREREG.md": 1,
        "COST_AUTHORITY_AND_EMBARGO_PREREG.md": 2,
        "DATA_CHANNEL_PREREG.md": 2,
    }
    for name, n in expected.items():
        rows = _section_rows((ROOT / name).read_text(encoding="utf-8"))
        assert len(rows) == n, f"{name} 偏离行数 {len(rows)} != 登记的 {n}"


def test_section_detection_is_line_anchored():
    """守卫自身的判据也要被验：行首零列锚定不能被子串/缩进示意骗过。

    植入：一段含缩进 `  ## 偏离登记` 示意的文本必须被判为「无节」。
    """
    fake = "正文里有格式示意：\n\n    ## 偏离登记\n\n| 项目 | ... |\n"
    assert _section_rows(fake) is None, "行首锚定失效：缩进示意被当成真节"
