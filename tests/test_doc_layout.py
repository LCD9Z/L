# -*- coding: utf-8 -*-
"""文档布局守卫（B3）：根目录收敛 + 链接完整性。

## 防什么

根目录曾积压 **112 份**同级 md。`AGENTS.md` L92 早就写着
「`docs/archive/` 与早期 `*_REPORT.md` 多为过程记录或已作废结论」——
**约定存在，但从未执行**。后果不是「不整洁」，而是**导航失效**：
新人和 AI 在 112 份同级文档里分不清哪份是结论、哪份是当年的过程记录。

2026-10-18 按 `ENTRYPOINTS.md` §八 的分级原则收敛到 62 份，
50 份历史过程记录移入 `docs/archive/`（全文保留、未改一字）。

## 四条守卫

1. **根目录白名单**：根 md 必须属于
   `ROOT_ALLOWED` / `*_PREREG*` / `*_VERDICT*` 之一 —— 防「悄悄往根目录丢一份新 md」；
2. **归档到位**：`ARCHIVE` 清单里每个文件都在 `docs/archive/`，
   且根目录**不残留**同名文件（防「复制而非移动」造成两份并存）；
3. **索引覆盖**：`docs/archive/README.md` 必须提到每个归档文件，
   否则「归档了但没人知道」，等于埋掉；
4. **链接不悬空**：全树 md 的相对链接必须解析到存在的文件。
   这是本次收敛的**安全网** —— 移走一个被 5 处引用的文件却不改链接＝造 5 个死链。

## 为什么链接守卫要排除 `tools/aoci/`

`tools/aoci/` 是 **vendored 第三方项目**（AOCI 认知索引），其 README 引用
`assets/*.jpg`、`LICENSE` 等**它自己仓库**的文件，本项目只复制了代码。
改它的 README 会让下次同步冲突，所以按「第三方目录不改不看」排除，
并在失败信息里显式说明排除了哪些 —— 不做无声跳过。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "docs" / "archive"
ARCHIVE_README = ARCHIVE_DIR / "README.md"
MIGRATOR = ROOT / "scripts" / "migrate_root_docs.py"

#: 链接守卫的排除前缀（vendored 第三方目录）
LINK_EXEMPT_PREFIXES = ("tools/aoci/",)

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")


def _load_migrator():
    assert MIGRATOR.is_file(), "scripts/migrate_root_docs.py 缺失"
    spec = importlib.util.spec_from_file_location("migrate_root_docs", MIGRATOR)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _root_mds() -> List[str]:
    return sorted(p.name for p in ROOT.glob("*.md"))


# ---------------------------------------------------------------------------
# 1 根目录白名单
# ---------------------------------------------------------------------------

def test_root_md_allowlist():
    """⚠️ 核心守卫：根目录不许出现未登记的新 md。

    文档数与**结论源**数量是治理指标。让根目录随便长文档，
    「哪份权威」就再次变成靠文件名猜。
    """
    mod = _load_migrator()
    allowed = set(mod.ROOT_ALLOWED)
    unregistered = [n for n in _root_mds()
                    if n not in allowed
                    and "_PREREG" not in n
                    and "_VERDICT" not in n]
    assert unregistered == [], (
        "以下 md 在根目录但未登记（新文档要么进 ROOT_ALLOWED，"
        "要么归档到 docs/archive/）:\n  " + "\n  ".join(unregistered))


# ---------------------------------------------------------------------------
# 2 归档到位
# ---------------------------------------------------------------------------

def test_every_archived_file_is_in_archive_dir():
    mod = _load_migrator()
    missing = [n for n in mod.ARCHIVE
               if not (ARCHIVE_DIR / mod.RENAME.get(n, n)).is_file()]
    assert missing == [], f"以下文件不在 docs/archive/：{missing}"


def test_no_archived_file_left_in_root():
    """防「复制而非移动」：同名文件不许同时存在于根与 archive。"""
    mod = _load_migrator()
    both = [n for n in mod.ARCHIVE if (ROOT / n).is_file()]
    assert both == [], (
        "以下文件既在根目录又在归档清单里（应只有归档一份）:\n  "
        + "\n  ".join(both))


def test_root_count_is_reported():
    """根 md 数量变化必须显式——这是「收敛」的度量。

    不是断言「必须 ≤62」，而是钉死当前值：变成 63 时要么归档，
    要么改这里并说明理由（数字不能悄悄漂）。

    2026-10-18 12:09：62 → 63，新增 `COST_AUTHORITY_AND_EMBARGO_PREREG.md`；
    12:40 63 → 64，新增 `COST_AUTHORITY_AND_EMBARGO_VERDICT.md`（守卫要求
    「已执行」的预注册必须有独立判定，见 test_experiment_status）。
    14:0x 64 → 66，新增 `DSR_IC_FAMILY_PREREG.md` + `DSR_IC_FAMILY_VERDICT.md`
    （DSR 接线的预注册与判定，同样属「预注册与判定」档）。
    15:0x 66 → 68，新增 `DATA_CHANNEL_PREREG.md` + `DATA_CHANNEL_VERDICT.md`
    （A8 公告日第二源 + ② 证券代码映射表 + dataset_fingerprint 的
    预注册与判定，属「预注册与判定」档，非过程记录）。变更理由已写入
    AGENTS.md §4。
    16:4x 68 → 71，新增 `EVIDENCE_CHAIN_PREREG.md` + `EVIDENCE_CHAIN_VERDICT.md`
    （A5+A6+A12 的预注册与判定）+ `REJECTED_EXPERIMENTS.md`（A12 登记册，
    survey §8.4-A12；条目数与 n_trials 来源对账，属「登记册」档）。
    变更理由已写入 AGENTS.md §4。
    17:5x 71 → 73，新增 `DATA_SNOOPING_PREREG.md` + `DATA_SNOOPING_VERDICT.md`
    （A2 PBO via CSCV + A3 SPA/StepM 的预注册与判定，survey §8.7 第 4 档）。
    18:2x 73 → 75，新增 `RECEIPT_PREREG.md` + `RECEIPT_VERDICT.md`
    （A7 收据升级的预注册与判定，survey §8.7 第 5 档）。
    20:2x 75 → 76，新增 `REGIME_ATTRIBUTION_PREREG.md`（regime 分层归因预注册）。
    21:0x 76 → 77，新增 `REGIME_ATTRIBUTION_VERDICT.md`（同上立项的判定；
    预注册 §八 要求「已执行」的预注册必须有独立判定）。
    本次改的是**常数**，判据本身（「根目录 md 数必须等于登记值」）未变；
    反向验证：把常量改成 64 时本测试必须失败，且失败信息含 `len(_root_mds())`。
    """
    assert len(_root_mds()) == 77, (
        f"根目录 md 数 = {len(_root_mds())}，与登记的 77 不符。\n"
        "新增结论源文档请改本断言并在提交信息里说明；"
        "过程记录请归档到 docs/archive/。")


# ---------------------------------------------------------------------------
# 3 索引覆盖
# ---------------------------------------------------------------------------

def test_archive_index_covers_all():
    """归档目录里每个 md（除 README 自己）必须在 README 的清单里被提到。"""
    mod = _load_migrator()
    index = ARCHIVE_README.read_text(encoding="utf-8") if ARCHIVE_README.is_file() else ""
    assert index, "docs/archive/README.md 缺失"

    # 只校验本次归档的 50 份（更早的 33 份 PHASE 文档由原 README 文字概括）
    missing = [mod.RENAME.get(n, n) for n in mod.ARCHIVE
               if mod.RENAME.get(n, n) not in index]
    assert missing == [], (
        "以下归档文件未出现在 docs/archive/README.md 索引里"
        "（跑了 migrate 但没重建索引？）:\n  " + "\n  ".join(missing))


# ---------------------------------------------------------------------------
# 4 链接不悬空
# ---------------------------------------------------------------------------

def _iter_md():
    for p in ROOT.rglob("*.md"):
        if ".git" in p.parts:
            continue
        rel = p.relative_to(ROOT).as_posix()
        if any(rel.startswith(pref) for pref in LINK_EXEMPT_PREFIXES):
            continue
        yield p, rel


def test_md_relative_links_resolve():
    """⚠️ 全树 md 的相对链接必须解析到存在的文件。

    排除项：`http(s)://` / `file:` / `mailto:` / 纯锚点 `#x`。
    vendored 第三方目录见模块 docstring。
    """
    broken: List[Dict[str, str]] = []
    total = 0
    for p, rel in _iter_md():
        text = p.read_text(encoding="utf-8", errors="ignore")
        for m in LINK_RE.finditer(text):
            tgt = m.group(2).strip()
            if not tgt or tgt.startswith(("http://", "https://", "file:",
                                          "mailto:", "#")):
                continue
            base = tgt.split("#")[0]
            if not base:
                continue
            total += 1
            if not (p.parent / base).resolve().exists():
                broken.append({"src": rel, "target": tgt})
    assert total > 150, f"只扫到 {total} 个相对链接，扫描逻辑可能坏了"
    assert broken == [], (
        f"{len(broken)} 个断链（共扫 {total} 个）:\n  "
        + "\n  ".join(f"{b['src']} -> {b['target']}" for b in broken[:30]))


def test_link_checker_can_find_broken_links(tmp_path):
    """反向验证内嵌：造一个断链样本，确认判据本身**会红**。

    没有这条，`test_md_relative_links_resolve` 可能因正则写错而**恒绿** ——
    「测试全绿 ≠ 纪律成立」。
    """
    sample = tmp_path / "sample.md"
    sample.write_text("[x](definitely-not-here.md)\n", encoding="utf-8")
    text = sample.read_text(encoding="utf-8")
    hits = [m.group(2) for m in LINK_RE.finditer(text)]
    assert hits == ["definitely-not-here.md"]
    assert not (sample.parent / hits[0]).exists(), "样本必须指向不存在的文件"
