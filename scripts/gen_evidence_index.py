# -*- coding: utf-8 -*-
"""生成 `EVIDENCE_INDEX.md`：把「报告引用的证据 JSON」编成可核对的索引。

## 为什么需要

``reports/`` 里的 JSON 是**回测产物**，报告里的数字全部来自它们。
但此前 ``.gitignore`` 把整个 ``reports/`` 排除了 —— 于是**报告与证据脱钩**：
换会话/换人时无法判断「这个数字怎么来的、能不能重跑出来」。

现策略（见 ``.gitignore`` 注释）：

* **跟踪** ``reports/*.json``（证据快照，含可复现的输入参数与结果）
* **忽略** 日志、``_*`` 临时探针、``*.partial`` 中间产物、子目录

本脚本负责把「跟踪了什么」写成人类可读的索引，避免证据变成**无标签的散件**。

用法::

    python scripts/gen_evidence_index.py            # 生成
    python scripts/gen_evidence_index.py --check    # 校验（供守卫测试调用）
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import os
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
INDEX = ROOT / "EVIDENCE_INDEX.md"

#: 索引文件的表头锚点（守卫测试据此定位表格）
TABLE_HEADER = "| 证据文件 | 字节 | sha256 | 引用它的报告 | 生成脚本 |"


def evidence_files() -> List[str]:
    """被跟踪的证据 JSON（排除 `_` 前缀的临时探针）。"""
    names = [
        os.path.basename(p)
        for p in glob.glob(str(REPORTS / "*.json"))
        if not os.path.basename(p).startswith("_")
    ]
    return sorted(names)


def _sha256_12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def citing_reports(name: str) -> List[str]:
    """哪些 .md 报告引用了该证据文件。"""
    out: List[str] = []
    for p in sorted(glob.glob(str(ROOT / "*.md"))):
        base = os.path.basename(p)
        if base in ("README.md", "EVIDENCE_INDEX.md"):
            continue
        try:
            text = Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if name in text:
            out.append(base)
    return out


def generating_scripts(name: str) -> List[str]:
    """哪些脚本提到该文件名（多为 `--out` 缺省或文档串）。"""
    out: List[str] = []
    for p in sorted(glob.glob(str(ROOT / "scripts" / "*.py"))) + sorted(
        glob.glob(str(ROOT / "*.py"))
    ):
        base = os.path.basename(p)
        try:
            text = Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if name in text:
            out.append(base)
    return out


def build_index() -> str:
    files = evidence_files()
    lines: List[str] = [
        "# 证据索引（EVIDENCE_INDEX）",
        "",
        "> **自动生成** —— 由 `scripts/gen_evidence_index.py` 产出，**请勿手改**。",
        "> 重新生成：`python scripts/gen_evidence_index.py`",
        "",
        "## 这份索引解决什么",
        "",
        "报告里的每个数字都来自 `reports/*.json`。这些文件此前被 `.gitignore` 整体排除，",
        "导致**报告与证据脱钩** —— 换会话/换人时无法判断「这个数字怎么来的」。",
        "",
        "现策略：**跟踪 `reports/*.json`**（证据快照），忽略日志 / `_*` 临时探针 /",
        "`*.partial` 中间产物 / 子目录。判定规则 —— **未跟踪的 = 可重生成的中间产物；",
        "已跟踪的 = 证据快照**。",
        "",
        "## ⚠️ 读法（三点）",
        "",
        "1. **sha256 仅供核对，不作门禁** —— 数据更新后重跑会改变哈希，属正常。",
        "   需要核验时用 `python scripts/gen_evidence_index.py --check`。",
        "2. **「生成脚本」列为 `—` 不等于无法复现** —— 多数脚本把输出路径作为 `--out` 参数，",
        "   文件名不出现在代码里。此时以**引用它的报告**中的命令行为准。",
        "3. **同一份证据可能被多份报告引用** —— 这属正常（如 `five_factor_ab_v2.json` 被 4 份引用）。",
        "",
        f"**当前跟踪 {len(files)} 份证据。**",
        "",
        "---",
        "",
        TABLE_HEADER,
        "|------|-----:|--------|------|------|",
    ]
    for name in files:
        p = REPORTS / name
        size = p.stat().st_size if p.exists() else 0
        digest = _sha256_12(p) if p.exists() else "—"
        cites = citing_reports(name)
        scripts = generating_scripts(name)
        cite_s = "<br>".join(cites) if cites else "（暂无报告直接引用）"
        scr_s = "<br>".join(f"`{s}`" for s in scripts[:3]) if scripts else "—"
        lines.append(f"| `{name}` | {size:,} | `{digest}` | {cite_s} | {scr_s} |")

    lines += [
        "",
        "---",
        "",
        "## 未被任何报告直接引用的证据",
        "",
        "以下文件已跟踪但暂无报告直接引用 —— 可能是**中间产物**或**脚本内部消费**。",
        "保留它们是为可复现性；若确认无用，应移出 `reports/` 或加 `_` 前缀使其被忽略。",
        "",
    ]
    orphans = [n for n in files if not citing_reports(n)]
    if orphans:
        for n in orphans:
            lines.append(f"- `{n}`")
    else:
        lines.append("（无）")

    lines += [
        "",
        "---",
        "",
        "**声明**：本索引只描述「哪些证据被跟踪」，**不构成任何策略有效性判断**。",
        "**本文件不构成投资建议。**",
        "",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="生成/校验 EVIDENCE_INDEX.md")
    ap.add_argument("--check", action="store_true", help="只校验覆盖度，不写文件")
    args = ap.parse_args(argv)

    files = evidence_files()
    if args.check:
        if not INDEX.exists():
            print(f"FAIL 索引不存在: {INDEX}")
            return 2
        text = INDEX.read_text(encoding="utf-8")
        missing = [n for n in files if f"`{n}`" not in text]
        if missing:
            print(f"FAIL 索引缺 {len(missing)} 项: {missing[:5]}")
            return 2
        print(f"OK 索引覆盖 {len(files)} 份证据")
        return 0

    INDEX.write_text(build_index(), encoding="utf-8", newline="\n")
    print(f"已写 {INDEX}（{len(files)} 份证据）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
