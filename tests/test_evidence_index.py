# -*- coding: utf-8 -*-
"""证据索引守卫（`reports/EVIDENCE_INDEX.md` + `.gitignore` 的 `reports/` 策略）。

> **来源**：移植自副本 `tests/test_evidence_index.py`（P008，
> 2026-10-12），按主干实际规则适配。

## 锁住什么

报告里的数字来自 `reports/**/*.json`。此前 `.gitignore` 整体排除 `reports/`，
于是**报告与证据脱钩** —— 换会话/换人时无法判断数字来源。

现策略：**跟踪 `reports/` 下的证据 JSON**，忽略日志 / `_*` 探针 / `*.partial`。

本测试防三类回归：

1. **新增证据但没进索引** → 证据变成无标签散件
2. **`.gitignore` 被改回整体排除** → 证据再次脱钩
3. **临时探针混入跟踪范围** → 噪声入库

## 与副本的差异（主干适配，P008 §4.2 / §4.4）

| 项 | 副本 | 主干 |
|---|---|---|
| 索引路径 | `EVIDENCE_INDEX.md`（根目录） | **`reports/EVIDENCE_INDEX.md`** |
| 证据位置 | 仅 `reports/*.json` 根层 | **含子目录**（`cross_decade/`、`delisted/`） |
| `.gitignore` | `!reports/*.json` | **更宽**：另含 `!reports/*.md` + 例外目录 |
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
INDEX = REPORTS / "EVIDENCE_INDEX.md"          # ⚠️ 主干在 reports/ 下
GITIGNORE = ROOT / ".gitignore"


def _tracked_evidence() -> list[str]:
    """已跟踪的证据 JSON（相对 reports/ 的路径）。

    ⚠️ 用 `git ls-files` 而非磁盘 glob —— 项目规则是「**已跟踪 = 证据快照**」。
    不排除 `_` 前缀：实测有 3 份带 `_` 的被 tracked
    （`_intermediate/VERDICT_partial.json` 等），它们既然入库就是证据。
    """
    out = subprocess.run(["git", "ls-files", "reports/*.json"],
                         cwd=str(ROOT), capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("git 不可用")
    rels = []
    for line in out.stdout.splitlines():
        line = line.strip().replace("\\", "/")
        if line.startswith("reports/") and line.endswith(".json"):
            rels.append(line[len("reports/"):])
    return sorted(set(rels))


def test_index_exists():
    assert INDEX.is_file(), (
        "reports/EVIDENCE_INDEX.md 缺失（运行 scripts/gen_evidence_index.py）")


def test_index_is_auto_generated():
    """索引必须自我声明为自动生成，防止被手改后失去可信度。"""
    text = INDEX.read_text(encoding="utf-8")
    assert "自动生成" in text
    assert "gen_evidence_index.py" in text


def test_index_preserves_main_history_preamble():
    """⚠️ 主干特有守卫：自动生成**不得覆盖**历史说明段（P008 §4.3）。

    该段记录 2026-10-02 独立审计发现的动因（`.gitignore` 曾忽略整个
    `reports/` → 2026-09-19 后全部实验原始 JSON 从未入库）。
    """
    text = INDEX.read_text(encoding="utf-8")
    assert "为什么有这个文件" in text, "历史说明段被自动生成覆盖了"
    assert "2026-10-02" in text, "历史说明段丢失日期凭据"


def test_index_covers_every_tracked_evidence():
    """⚠️ 核心守卫：每份已跟踪证据都必须出现在索引里（P008 §5.1）。"""
    text = INDEX.read_text(encoding="utf-8")
    missing = [n for n in _tracked_evidence()
               if f"`{n}`" not in text and f"`{n.split('/')[-1]}`" not in text]
    assert missing == [], (
        f"索引未覆盖以下证据（请重跑 gen_evidence_index.py）: {missing}")


def test_index_has_no_phantom_entries():
    """索引里不应出现磁盘上不存在的文件（防复制粘贴错误）。"""
    text = INDEX.read_text(encoding="utf-8")
    listed = {
        line.split("`")[1]
        for line in text.splitlines()
        if line.startswith("| `") and line.count("`") >= 2
    }
    phantom = sorted(n for n in listed if not (REPORTS / n).exists())
    assert phantom == [], f"索引含不存在的文件: {phantom}"


def test_gitignore_tracks_evidence_jsons():
    """`.gitignore` 必须保留证据白名单（否则证据再次脱钩）。

    ⚠️ 主干适配：主干规则比副本宽（另有 `!reports/*.md` 与例外目录），
    故只断言「存在某种放行 json 的规则」，不锁定具体形态。
    """
    text = GITIGNORE.read_text(encoding="utf-8")
    assert "!reports/*.json" in text or "!reports/**/*.json" in text, \
        ".gitignore 丢失证据白名单"


def test_gitignore_ignores_logs_partials_and_scratch():
    text = GITIGNORE.read_text(encoding="utf-8")
    for pat in ("*.log", "*.partial"):
        assert pat in text, f".gitignore 丢失忽略规则 {pat}"


def test_git_actually_tracks_evidence_and_ignores_scratch():
    """用真实 git 复核（无 git / 非仓库则跳过，不误报失败）。"""
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT,
                       capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("非 git 仓库或 git 不可用")

    def ignored(rel: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", rel],
                              cwd=ROOT).returncode == 0

    assert not ignored("reports/ic_diagnosis.json"), "证据 JSON 被忽略了"
    assert ignored("reports/_ci.log"), "日志未被忽略"
    assert ignored("reports/ic_diagnosis.json.partial"), ".partial 未被忽略"
