# -*- coding: utf-8 -*-
"""列出**无直接测试覆盖**的源码模块（HANDOVER §7 第 4 项：剩余 9 个）。

判定口径：tests/ 下任一 test_*.py 中出现该模块的 import（含 `_load('路径.py')`
按路径加载的形式）即视为有覆盖。**只看直接引用，不看间接**——故与覆盖率工具
口径不同，这里要回答的是「改这个模块会不会有测试报警」。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".workbuddy", "tests", "docs", "scripts", "_archive", ".venv",
             "__pycache__", ".git", "node_modules"}


def source_modules() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        parts = set(rel.parts)
        if parts & SKIP_DIRS:
            continue
        if p.name.startswith(("test_", "_")):
            continue
        try:
            n = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            n = -1
        out.append((rel.as_posix(), n))
    return out


def covered_names() -> set[str]:
    cov: set[str] = set()
    for t in (ROOT / "tests").rglob("test_*.py"):
        src = t.read_text(encoding="utf-8", errors="ignore")
        # 常规 import
        for m in re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", src, re.M):
            cov.add(m.split(".")[0])
            cov.add(m)
        # importlib.import_module("x.y")
        for m in re.findall(r"import_module\(\s*[\"']([\w.]+)", src):
            cov.add(m.split(".")[0])
            cov.add(m)
        # _load("path/to/mod.py", ...) 形式
        for m in re.findall(r"_load\(\s*[\"']([^\"']+\.py)", src):
            cov.add(Path(m).stem)
            cov.add(m[:-3].replace("/", "."))
    return cov


def main() -> int:
    mods = source_modules()
    cov = covered_names()
    missing: list[tuple[str, int]] = []
    for rel, n in mods:
        stem = Path(rel).stem
        dotted = rel[:-3].replace("/", ".")
        keys = {stem, dotted, dotted.split(".")[-1], dotted.replace(".", "_")}
        if keys & cov:
            continue
        missing.append((rel, n))

    print(f"源码模块 {len(mods)} · 有覆盖 {len(mods) - len(missing)} "
          f"· **无直接覆盖 {len(missing)}**")
    print()
    for rel, n in sorted(missing, key=lambda x: -x[1]):
        print(f"  {n:>5} 行  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
