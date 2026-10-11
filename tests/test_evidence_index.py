# -*- coding: utf-8 -*-
"""证据索引守卫（`EVIDENCE_INDEX.md` + `.gitignore` 的 `reports/` 策略）。

## 锁住什么

报告里的数字来自 `reports/*.json`。此前 `.gitignore` 整体排除 `reports/`，
于是**报告与证据脱钩** —— 换会话/换人时无法判断数字来源（与「防断线」冲突）。

现策略：跟踪 `reports/*.json`，忽略日志 / `_*` 探针 / `*.partial` / 子目录。

本测试防三类回归：

1. **新增证据但没进索引** → 证据变成无标签散件
2. **`.gitignore` 被改回整体排除** → 证据再次脱钩
3. **临时探针混入跟踪范围** → 噪声入库
"""

from __future__ import annotations

import glob
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "EVIDENCE_INDEX.md"
GITIGNORE = ROOT / ".gitignore"


def _evidence_names() -> list[str]:
    return sorted(
        os.path.basename(p)
        for p in glob.glob(str(ROOT / "reports" / "*.json"))
        if not os.path.basename(p).startswith("_")
    )


def test_index_exists():
    assert INDEX.is_file(), "EVIDENCE_INDEX.md 缺失（运行 scripts/gen_evidence_index.py 生成）"


def test_index_is_auto_generated():
    """索引必须自我声明为自动生成，防止被手改后失去可信度。"""
    text = INDEX.read_text(encoding="utf-8")
    assert "自动生成" in text
    assert "gen_evidence_index.py" in text


def test_index_covers_every_evidence_file():
    """⚠️ 核心守卫：每份证据都必须出现在索引里。"""
    text = INDEX.read_text(encoding="utf-8")
    missing = [n for n in _evidence_names() if f"`{n}`" not in text]
    assert missing == [], f"索引未覆盖以下证据（请重跑 gen_evidence_index.py）: {missing}"


def test_index_has_no_phantom_entries():
    """索引里不应出现磁盘上不存在的文件（防复制粘贴错误）。"""
    text = INDEX.read_text(encoding="utf-8")
    listed = {
        line.split("`")[1]
        for line in text.splitlines()
        if line.startswith("| `") and line.count("`") >= 2
    }
    phantom = sorted(n for n in listed if not (ROOT / "reports" / n).exists())
    assert phantom == [], f"索引含不存在的文件: {phantom}"


def test_gitignore_tracks_evidence_jsons():
    """`.gitignore` 必须保留 `!reports/*.json`（否则证据再次脱钩）。"""
    text = GITIGNORE.read_text(encoding="utf-8")
    assert "!reports/*.json" in text, ".gitignore 丢失证据白名单"


def test_gitignore_ignores_logs_partials_and_scratch():
    text = GITIGNORE.read_text(encoding="utf-8")
    for pat in ("*.log", "*.partial", "reports/_*.json"):
        assert pat in text, f".gitignore 丢失忽略规则 {pat}"


def test_git_actually_tracks_evidence_and_ignores_scratch():
    """用真实 git 复核（无 git / 非仓库则跳过，不误报失败）。"""
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT,
                       capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("非 git 仓库或 git 不可用")

    def ignored(rel: str) -> bool:
        r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT)
        return r.returncode == 0

    assert not ignored("reports/ic_diagnosis.json"), "证据 JSON 被忽略了"
    assert ignored("reports/_ci.log"), "日志未被忽略"
    assert ignored("reports/expert_filter_study.json.partial"), ".partial 未被忽略"
    assert ignored("reports/_turnover_fix_probe.json"), "临时探针未被忽略"
