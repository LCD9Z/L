# -*- coding: utf-8 -*-
"""凭据泄漏扫描（零第三方依赖）。

CI 与本地检查**共用同一实现**。此前工作流里是一段内联 grep，本地无法复用，
两处容易漂移；且只匹配 3 个固定字面量、不覆盖 *.yml / *.toml / *.ini 等文件类型。

两类检查：

1. 赋值型——敏感变量被赋予非占位值。覆盖场景如配置文件、脚本、文档示例。
2. 已知泄漏字面量——历史上真实泄漏过的 token/ID（见 KNOWN_LEAK_LITERALS）。
   即使文件被重命名或移动，字面量仍会被抓到。

设计原则：占位值（空、``<...>``、``$VAR``、``****``、``your_xxx``）一律不算泄漏。
误报会让检查被整体绕过，因此宁可把「明显是模板」的形式显式放行。

用法：
    python credential_scan.py          # 扫描，发现泄漏时退出码 1
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, Tuple

ROOT = Path(__file__).resolve().parent

# --- 扫描范围 -------------------------------------------------------------

SCAN_SUFFIXES = {
    ".py", ".md", ".json", ".jsonl", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".txt", ".sh", ".ps1", ".bat",
}

SKIP_DIRS = {
    ".git", ".github", ".mypy_cache", ".ruff_cache", "__pycache__",
    ".pytest_cache", "build", "dist", "reports", "node_modules",
}

# 扫描器自身不参与扫描：它必然包含敏感键名与已知字面量，否则会自我命中。
SKIP_FILES = {"credential_scan.py"}

# --- 检查项 ---------------------------------------------------------------

#: 需要留意的敏感变量名。变量名本身不是秘密，被赋值成真实值才是。
SENSITIVE_KEYS = (
    "FEISHU_BASE_TOKEN",
    "FEISHU_TABLE_ID",
    "FEISHU_NOTIFY_USER_ID",
    "FEISHU_NOTIFY_CHAT_ID",
    "FEISHU_BASE_URL",
    "ARK_API_KEY",
    "TUSHARE_TOKEN",
    "FEISHU_APP_SECRET",
)

#: 历史上确实泄漏过、且已从仓库清除的字面量。逐段拼接书写，
#: 避免扫描器自身成为新的泄漏源。
KNOWN_LEAK_LITERALS = (
    "LjSlbLUwza" + "IPObsoHq0crrdenSe",
    "tbljEN" + "K3iLyh5z9b",
)

_PLACEHOLDER_CHARS = set("<>{}$%*")
_PLACEHOLDER_PREFIXES = (
    "your", "xxx", "todo", "example", "placeholder", "dummy",
    "fake", "test", "none", "null", "n/a", "changeme",
)

#: 变量名右边的赋值形式。支持三种写法：
#:   ``TOKEN = "v"`` / ``TOKEN: str = "v"`` / ``"TOKEN": "v"``
#: 尾随引号需显式吃掉，否则 JSON 风格的键名会漏报。
_ASSIGN_RE = re.compile(
    r"(?<![\w])(?P<key>" + "|".join(SENSITIVE_KEYS) + r")[\"']?\s*"
    r"(?::\s*[A-Za-z_][A-Za-z0-9_\[\], .|]*?)?"
    r"\s*[=:]\s*"
    r"(?P<val>\"[^\"]*\"|'[^']*'|[^\s,;)\]}]+)"
)
# 形如 ou_xxxx / tblxxx / sk-xxxx 的掩码：去掉前缀后只剩重复占位字符
_MASK_PREFIXES = ("ou_", "tbl", "sk-", "ep-", "bk-")
_MASK_CHARS = set("xX0-_*. ")
# 含中日韩文字的值是「描述」而非真实凭据（如 `你的Token`）
_CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


def _looks_like_mask(v: str) -> bool:
    core = v
    for prefix in _MASK_PREFIXES:
        if core.lower().startswith(prefix):
            core = core[len(prefix):]
            break
    return bool(core) and set(core) <= _MASK_CHARS


def _is_placeholder(value: str) -> bool:
    """判断赋值右侧是否为占位/引用形式（占位不算泄漏）。"""
    v = value.strip().strip("\"'").strip("`")
    if not v:
        return True
    # 模板与变量引用：<your_token> / $FEISHU_BASE_TOKEN / {token} / ****
    if any(ch in _PLACEHOLDER_CHARS for ch in v):
        return True
    # 函数调用或下标取值：os.getenv("X") / cfg["X"]
    if "(" in v or "[" in v:
        return True
    # 描述性文字：`你的Token`
    if _CJK.search(v):
        return True
    # 掩码：ou_xxxxxxxx / tbl0-0-0
    if _looks_like_mask(v):
        return True
    return v.lower().startswith(_PLACEHOLDER_PREFIXES)


def _iter_files() -> Iterator[Path]:
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if path.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts[:-1]):
            continue
        yield path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def scan_assignment_leaks(text: str) -> Iterator[Tuple[int, str, str]]:
    """产出 ``(行号, 变量名, 实际值)``。

    支持三种写法，且都要求「变量名右边紧邻赋值」：

    * ``TOKEN = "v"``
    * ``TOKEN: str = "v"``            —— 带类型标注
    * ``"TOKEN": "v"``                —— JSON 风格

    反例（不应命中，否则把环境变量引用当成泄漏）：
    ``--base-token "$FEISHU_BASE_TOKEN"``、``| FEISHU_TABLE_ID |``。
    """
    for lineno, line in enumerate(text.splitlines(), 1):
        for match in _ASSIGN_RE.finditer(line):
            value = match.group("val")
            if not _is_placeholder(value):
                yield lineno, match.group("key"), value


def scan_known_literals(text: str) -> Iterator[Tuple[int, str]]:
    """产出 ``(行号, 命中的字面量)``。"""
    for lineno, line in enumerate(text.splitlines(), 1):
        for literal in KNOWN_LEAK_LITERALS:
            if literal in line:
                yield lineno, literal


def scan(files: Iterable[Path] | None = None) -> Tuple[list[str], int]:
    """返回 ``(问题描述列表, 已扫描文件数)``。"""
    findings: list[str] = []
    scanned = 0
    for path in (files if files is not None else _iter_files()):
        text = _read_text(path)
        if text is None:
            continue
        scanned += 1
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        for lineno, key, value in scan_assignment_leaks(text):
            findings.append(f"{rel}:{lineno}: {key} 被赋予非占位值 -> {value!r}")
        for lineno, literal in scan_known_literals(text):
            findings.append(f"{rel}:{lineno}: 命中已知泄漏字面量 {literal!r}")
    return findings, scanned


def main() -> int:
    findings, scanned = scan()
    if findings:
        print("[FAIL] 检测到疑似明文凭据：")
        for item in findings:
            print(f"  - {item}")
        print("\n请改用环境变量注入（见 .env.example），不要把真实值写入仓库。")
        return 1
    print(f"凭据扫描通过：已扫描 {scanned} 个文件，未发现明文凭据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
