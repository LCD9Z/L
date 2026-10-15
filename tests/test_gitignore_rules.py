"""`.gitignore` 的 `_` 前缀探针规则（顺序即硬约束）。

**背景（2026-10-16，副本侧裁定请求，主干侧实测采纳）**：

gitignore 的匹配规则是「**后规则优先**」。原 `.gitignore` 把
`reports/_*.json` 写在 `!reports/*.json` **之前**，于是被后者覆盖
—— `_` 前缀 JSON 实际**不被忽略**。

副本侧用 `git check-ignore -v reports/_recalc_ss_p1_20230703.json`
实测，命中 `.gitignore:44:!reports/*.json`（「不忽略」），据此发现：
**`_turnover_fix_probe.json` 很可能不是「有意入库的探针」，
而是规则没拦住、被 `git add -A` 顺带带入的。**

**后果**：探针 / 重算中间产物会污染证据库，而「已跟踪 = 证据快照」
是本项目「结论数字可追溯」的前提（见 `test_evidence_index.py`）。

**修法**：把 `reports/_*.json` 移到 `!reports/*.json` **之后**。
本文件即该修复的守卫 —— 含**反向验证**（断言它真能拦住），
防「改了规则却不知道规则已失效」这类静默失效。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(ROOT),
                          capture_output=True, text=True)


def _in_git_repo() -> bool:
    return (ROOT / ".git").exists()


def _ignored(rel: str) -> bool:
    """`git check-ignore -q <path>` 为 0 表示被忽略。"""
    r = _git("check-ignore", "-q", rel)
    return r.returncode == 0


def test_underscore_probe_json_is_ignored():
    """`reports/_xxx.json` 必须被忽略（探针 / 中间产物不得入库）。"""
    if not _in_git_repo():
        return
    for probe in ("reports/_probe_test.json",
                  "reports/_recalc_ss_p1_20230703.json"):
        assert _ignored(probe), (
            f"{probe} 未被忽略 —— `_` 前缀探针会被 git add -A 顺带入库")


def test_plain_evidence_json_is_not_ignored():
    """反向验证：普通证据 JSON 必须**不**被忽略（否则修复过度）。"""
    if not _in_git_repo():
        return
    for keep in ("reports/decay_h5_ic.json",
                 "reports/EVIDENCE_INDEX.md"):
        assert not _ignored(keep), (
            f"{keep} 被忽略了 —— 修复过度，证据将无法入库")


def test_underscore_rule_comes_after_negation():
    """规则顺序：`reports/_*.json` 必须在 `!reports/*.json` 之后。

    这是**文本层**断言 —— 即使 git 行为因环境变化而不同，
    也能拦住「有人把规则挪回前面」的回归。
    """
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = text.splitlines()
    idx_neg = next(i for i, l in enumerate(lines) if l.strip() == "!reports/*.json")
    idx_under = next(i for i, l in enumerate(lines) if l.strip() == "reports/_*.json")
    assert idx_under > idx_neg, (
        f"`reports/_*.json`（第 {idx_under + 1} 行）排在 "
        f"`!reports/*.json`（第 {idx_neg + 1} 行）之前 —— "
        "gitignore 后规则优先，前者会被覆盖而失效")


def test_already_tracked_underscore_artifacts_untouched():
    """已入库的 `_` 前缀产物（子目录内）不受本次修复影响。"""
    if not _in_git_repo():
        return
    out = _git("ls-files", "reports/*.json").stdout.splitlines()
    tracked_underscore = [p for p in out if Path(p).name.startswith("_")]
    # 只断言「仍然 tracked」（不关心具体份数，避免脆弱断言）
    for p in tracked_underscore:
        assert (ROOT / p).exists(), f"{p} 已跟踪但磁盘上不存在"
