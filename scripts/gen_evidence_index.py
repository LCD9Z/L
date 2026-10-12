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
# ⚠️ 适配（主干）：索引在 reports/ 下，非仓库根目录（副本在根目录）
INDEX = REPORTS / "EVIDENCE_INDEX.md"

#: 索引文件的表头锚点（守卫测试据此定位表格）
TABLE_HEADER = "| 证据文件 | 字节 | sha256 | 引用它的报告 | 生成脚本 |"


def evidence_files() -> List[str]:
    """被跟踪的证据 JSON（排除 `_` 前缀的临时探针）。

    ⚠️ 适配（主干，2026-10-12）两处：

    1. **主干证据分布在子目录**（`reports/cross_decade/`、`reports/delisted/`），
       而副本只在根目录 → 改为按相对路径扫描。
    2. **改用 `git ls-files` 而非磁盘 glob** —— P008 §5.1 要求
       「索引条数 == tracked 证据数」。实测磁盘 glob 得 84 份、
       tracked 为 81 份（差 3 份为磁盘上未跟踪的文件）。
       索引的语义是「**入库的证据**」，故以 git 为准。
       若 git 不可用，回退到磁盘扫描。
    """
    rels: List[str] = []
    try:
        import subprocess
        out = subprocess.run(
            ["git", "ls-files", "reports/*.json"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                line = line.strip().replace("\\", "/")
                if not line.startswith("reports/") or not line.endswith(".json"):
                    continue
                rel = line[len("reports/"):]
                # ⚠️ 不排除 `_` 前缀 —— 项目规则是「**已跟踪 = 证据快照**」。
                # 实测有 3 份带 `_` 的被 tracked（`_intermediate/VERDICT_partial.json`
                # 等），它们**既然入库就是证据**（其中 VERDICT_partial 是"H-CD 判定沿革"
                # 的历史凭据）。排除它们会使索引条数（78）≠ tracked（81），
                # 违反 P008 §5.1 的验收标准。
                rels.append(rel)
    except Exception:                                # noqa: BLE001
        rels = []
    if not rels:
        # 回退：磁盘扫描（git 不可用时）。同样不排除 （见上）
        for p in REPORTS.rglob("*.json"):
            rels.append(p.relative_to(REPORTS).as_posix())
    return sorted(set(rels))


def _sha256_12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def citing_reports(name: str) -> List[str]:
    """哪些 .md 报告引用了该证据文件。

    ⚠️ 适配（主干）：`name` 现为**相对路径**（如 `cross_decade/W1.json`），
    而报告里多写**裸文件名**（`W1.json`）→ 用 basename 匹配，
    否则子目录证据的「引用报告」列会全空。
    """
    base_name = os.path.basename(name)
    out: List[str] = []
    # ⚠️ 适配（主干）：报告不只在根目录，`reports/` 下也有 9 份
    candidates = sorted(glob.glob(str(ROOT / "*.md"))) + sorted(
        glob.glob(str(REPORTS / "**" / "*.md"), recursive=True)
    )
    for p in candidates:
        base = os.path.basename(p)
        if base in ("README.md", "EVIDENCE_INDEX.md"):
            continue
        try:
            text = Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if base_name in text or name in text:
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            if rel not in out:
                out.append(rel)
    return out


def generating_scripts(name: str) -> List[str]:
    """哪些脚本提到该文件名（多为 `--out` 缺省或文档串）。"""
    base_name = os.path.basename(name)
    out: List[str] = []
    for p in sorted(glob.glob(str(ROOT / "scripts" / "*.py"))) + sorted(
        glob.glob(str(ROOT / "scripts" / "**" / "*.py"), recursive=True)
    ) + sorted(glob.glob(str(ROOT / "*.py"))):
        base = os.path.basename(p)
        try:
            text = Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if base_name in text or name in text:
            if base not in out:
                out.append(base)
    return out


def _preserved_preamble() -> List[str]:
    """保留主干原有的「为什么有这个文件」历史说明段（P008 §4.3）。

    该段记录了 2026-10-02 独立审计发现的动因（`.gitignore` 曾忽略整个 `reports/`
    → 2026-09-19 后全部实验原始 JSON 从未入库）。**自动生成不得覆盖它** ——
    否则会丢掉「这个索引为什么存在」的历史。

    ⚠️ 适配（主干）：副本无此段，是主干独有内容。
    """
    if not INDEX.exists():
        return []
    try:
        text = INDEX.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if "为什么有这个文件" in ln), None)
    if start is None:
        return []
    # 从「为什么有这个文件」所在行开始，向下收集到**下一个 `---` / `##` 标题**为止。
    # ⚠️ 初版从标题行往下、遇空行即 break → 只提取到 1 行就丢掉了整段
    #   （2026-10-12 实测覆盖了主干的历史说明段，靠备份才发现）。
    block: List[str] = []
    for ln in lines[start:]:
        if ln.strip().startswith("---") or ln.startswith("## "):
            break
        block.append(ln)
    while block and block[-1].strip() == "":
        block.pop()
    return block + [""]


def build_index() -> str:
    files = evidence_files()
    lines: List[str] = [
        "# 证据索引（EVIDENCE_INDEX）",
        "",
        "> **自动生成** —— 由 `scripts/gen_evidence_index.py` 产出，**请勿手改**。",
        "> 重新生成：`python scripts/gen_evidence_index.py`",
        "",
    ]
    # P008 §4.3：主干独有的历史说明段必须保留
    pre = _preserved_preamble()
    if pre:
        lines += pre
    lines += [
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
