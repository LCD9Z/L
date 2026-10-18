# -*- coding: utf-8 -*-
r"""生成 `scripts/REGISTRY.md` —— `scripts/` 下每个脚本的**逐份**登记（A2）。

## 为什么需要

`scripts/` 有 81 个脚本，此前只有 `ENTRYPOINTS.md` §6.2 一句
「另 34 个多为一次性工具」，用**命名规则**代替清单：

> 「名字含 `build_` / `migrate_` / `convert_` / `backfill_` 且不在 §二~§五 → 默认一次性」

规则覆盖不到的部分（`run_*` 里到底哪些还在跑？`_audit_l3_tail_gap.py` 是谁在用？）
**全靠猜**。这与 `reports/` 白名单制（新建子目录不登记就静默不入库）是
**同型的静默失效面**：新增脚本不会有任何守卫发现，废弃脚本也不会有人标记。

## 状态判据（可自动重算，不靠人工印象）

| 状态 | 判据 |
|---|---|
| `active` | 满足任一**可执行引用**：① `tests/` 引用；② `scripts/` 外的生产代码引用；③ `run_daily.bat` / `run_ci.py`；④ `ENTRYPOINTS.md` §二–§五 登记（该行未标注「已被…取代」） |
| `deprecated` | 文档**明确**标注「已被…取代」，且无任何可执行引用（见 `DEPRECATED`，每条须附可检索的依据原话） |
| `one-off` | 其余 —— 有 `__main__` 可手工执行，属历史凭据（**不删**，删了会破坏可追溯性） |

⚠️ **「被某份报告提到」不算 `active`** —— 那只能证明当年跑过一次，不代表现在会跑。
所以判据只看「代码/测试/运行配置/正式清单」四类硬引用，不看散文提及。

## 用法

::

    python scripts/gen_scripts_registry.py            # 重写 scripts/REGISTRY.md
    python scripts/gen_scripts_registry.py --check    # 只比对不写；不一致退出码 1

守卫 `tests/test_scripts_registry.py` 直接 import 本模块的 :func:`collect` 重算，
**不跑 subprocess** —— 避免「环境缺命令伪装成断言失败」（2026-10-17 教训）。
"""
from __future__ import annotations

import ast
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
REGISTRY_PATH = SCRIPTS_DIR / "REGISTRY.md"

STATUS_ACTIVE = "active"
STATUS_ONEOFF = "one-off"
STATUS_DEPRECATED = "deprecated"
STATUSES: Tuple[str, ...] = (STATUS_ACTIVE, STATUS_ONEOFF, STATUS_DEPRECATED)

#: 明确被取代的脚本 → ``(文档相对路径, 必须在该文档中含脚本名的那一行出现的子串)``。
#: 只允许有文档明文依据的进这里；「我觉得没人用了」不构成依据。
#: 守卫 ``test_deprecated_basis_is_searchable`` 会真的去那篇文档里检索该子串。
DEPRECATED: Dict[str, Tuple[str, str]] = {
    "fetch_baostock_klines.py": ("ENTRYPOINTS.md", "已被上者取代"),
}

#: 允许没有 `__main__` 守卫的文件（纯 helper，以 `_` 前缀命名）
_HELPER_PREFIX = "_"


# ---------------------------------------------------------------------------
# 语料
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _test_texts() -> Tuple[Tuple[str, str], ...]:
    out = []
    for p in sorted((ROOT / "tests").rglob("*.py")):
        out.append((p.relative_to(ROOT).as_posix(), p.read_text(encoding="utf-8", errors="ignore")))
    return tuple(out)


@lru_cache(maxsize=1)
def _prod_texts() -> Tuple[Tuple[str, str], ...]:
    """`scripts/` 与 `tests/` 之外的 py —— 即会被生产/库代码调用的部分。"""
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        parts = p.relative_to(ROOT).parts
        if ".git" in parts or "__pycache__" in parts:
            continue
        if parts[0] in ("scripts", "tests"):
            continue
        out.append((p.relative_to(ROOT).as_posix(), p.read_text(encoding="utf-8", errors="ignore")))
    return tuple(out)


@lru_cache(maxsize=1)
def _runtime_texts() -> Tuple[Tuple[str, str], ...]:
    out = []
    for name in ("run_daily.bat", "run_ci.py", "pytest.ini"):
        p = ROOT / name
        if p.is_file():
            out.append((name, p.read_text(encoding="utf-8", errors="ignore")))
    return tuple(out)


@lru_cache(maxsize=1)
def _entrypoints_section() -> str:
    """`ENTRYPOINTS.md` §二–§五（正式/研究/诊断/取数）—— **不含** §六「一次性」。

    ⚠️ 行级剔除：标注「已被…取代」的行**不算 active 证据**。
    `fetch_baostock_klines.py` 就在 §五 里，但那一行明写「已被上者取代」——
    若不剔除，它会被误判为 `active`，「已废弃」就永远无人标记。
    """
    p = ROOT / "ENTRYPOINTS.md"
    if not p.is_file():
        return ""
    text = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"## 二、.*?(?=\n## 六、)", text, re.S)
    if not m:
        return ""
    kept = [ln for ln in m.group(0).splitlines()
            if not re.search(r"已被.{0,16}取代", ln)]
    return "\n".join(kept)


def _hits(stem: str, texts) -> List[str]:
    pat = re.compile(r"(?<![\w])" + re.escape(stem) + r"(?![\w])")
    return [name for name, body in texts if pat.search(body)]


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------

def _has_main_guard(tree: ast.Module) -> bool:
    return any(isinstance(node, ast.If) and "__main__" in ast.dump(node)
               for node in tree.body)


def _first_line(tree: ast.Module) -> str:
    doc = (ast.get_docstring(tree) or "").strip()
    return doc.split("\n")[0].strip() if doc else ""


def _evidence(stem: str) -> List[str]:
    ev: List[str] = []
    ev += _hits(stem, _test_texts())
    ev += _hits(stem, _prod_texts())
    ev += _hits(stem, _runtime_texts())
    if _hits(stem, (("ENTRYPOINTS.md", _entrypoints_section()),)):
        ev.append("ENTRYPOINTS.md")
    # 去重保序
    seen = set()
    return [x for x in ev if not (x in seen or seen.add(x))]


def collect() -> List[Dict[str, Any]]:
    """采集每个脚本的登记字段。返回按文件名升序的列表。"""
    rows: List[Dict[str, Any]] = []
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        name = path.name
        src = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(src)
            purpose = _first_line(tree)
            guard = _has_main_guard(tree)
        except SyntaxError:                                   # pragma: no cover
            purpose = "<语法错误，无法解析>"
            guard = False
        ev = _evidence(path.stem)
        dep = DEPRECATED.get(name)
        if dep and not ev:
            status = STATUS_DEPRECATED
        elif ev:
            status = STATUS_ACTIVE
        else:
            status = STATUS_ONEOFF
        rows.append({
            "script": name,
            "purpose": purpose or "—（无 docstring）",
            "guard": guard,
            "entry": (f"`python scripts/{name}`" if guard
                      else ("—（helper 模块，供 import）"
                            if name.startswith(_HELPER_PREFIX)
                            else "**无 `__main__`，import 即执行**")),
            "evidence": ev,
            "status": status,
            "deprecated_basis": (f"{dep[0]}：{dep[1]}" if dep else ""),
            "bytes": path.stat().st_size,
        })
    return rows


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def _cell(s: str) -> str:
    return s.replace("|", r"\|").replace("\n", " ")


def _evidence_cell(ev: List[str], limit: int = 3) -> str:
    if not ev:
        return "—（无可执行引用）"
    shown = "、".join(f"`{x}`" for x in ev[:limit])
    if len(ev) > limit:
        shown += f" +{len(ev) - limit}"
    return shown


def render(rows: List[Dict[str, Any]]) -> str:
    n = len(rows)
    cnt = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    no_guard = [r["script"] for r in rows if not r["guard"]]
    orphans = [r["script"] for r in rows if not r["evidence"]]

    lines: List[str] = []
    lines.append("# `scripts/` 脚本注册表（SCRIPT REGISTRY）")
    lines.append("")
    lines.append("> **由 `scripts/gen_scripts_registry.py` 生成，不要手改。**")
    lines.append("> 改了脚本或引用关系后跑一次 `python scripts/gen_scripts_registry.py`；")
    lines.append("> 守卫 `tests/test_scripts_registry.py` 会重算判据并比对，不一致即失败。")
    lines.append("")
    lines.append(f"**总数 {n}**　·　"
                 f"`active` {cnt[STATUS_ACTIVE]}　·　"
                 f"`one-off` {cnt[STATUS_ONEOFF]}　·　"
                 f"`deprecated` {cnt[STATUS_DEPRECATED]}")
    lines.append("")
    lines.append("## 一、状态判据（可自动重算）")
    lines.append("")
    lines.append("| 状态 | 判据 |")
    lines.append("|---|---|")
    lines.append("| `active` | 满足任一**可执行引用**：① `tests/`；② `scripts/` 外的生产代码；"
                 "③ `run_daily.bat` / `run_ci.py` / `pytest.ini`；"
                 "④ `ENTRYPOINTS.md` §二–§五 登记 |")
    lines.append("| `deprecated` | 文档**明文**标注「已被…取代」，且无可执行引用 |")
    lines.append("| `one-off` | 其余 —— 有 `__main__` 可手工执行，属历史凭据 |")
    lines.append("")
    lines.append("⚠️ **「被某份报告提到」不算 `active`** —— 只能证明当年跑过一次。")
    lines.append("")
    lines.append("## 二、逐份登记")
    lines.append("")
    lines.append("| # | 脚本 | 职责 | 入口 | 被谁调用 | 状态 |")
    lines.append("|---:|------|------|------|----------|------|")
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | `{r['script']}` | {_cell(r['purpose'])} | {_cell(r['entry'])} | "
            f"{_cell(_evidence_cell(r['evidence']))} | `{r['status']}` |")
    lines.append("")
    lines.append("## 三、治理结论")
    lines.append("")
    lines.append(f"- **无 `__main__` 守卫**：{len(no_guard)} 个"
                 + (f" —— {', '.join('`'+x+'`' for x in no_guard)}" if no_guard else "（全部合规）"))
    lines.append(f"- **零可执行引用**（既无测试、无生产代码、不在正式清单）：{len(orphans)} 个")
    if orphans:
        lines.append("")
        lines.append("  " + "、".join(f"`{x}`" for x in orphans))
    lines.append("")
    lines.append("> `one-off` / 零引用**不等于该删** —— 它们是历史凭据，删掉会破坏可追溯性。")
    lines.append("> 本节的作用是让「谁在用」从**猜**变成**查**。")
    lines.append("")
    lines.append("## 四、新增脚本的纪律")
    lines.append("")
    lines.append("1. 新建 `scripts/*.py` 后**必须**重跑生成器，否则守卫失败（防「悄悄加一个脚本」）；")
    lines.append("2. 若它是正式入口/研究入口，同步登记到 `ENTRYPOINTS.md` 对应章节；")
    lines.append("3. 若它已被取代，加进本模块的 `DEPRECATED` 表并**附可检索的依据原话**；")
    lines.append("4. 纯 helper 用 `_` 前缀（允许无 `__main__`），否则必须有 `__main__` 守卫。")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: List[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check = "--check" in args
    rows = collect()
    text = render(rows)
    if check:
        old = REGISTRY_PATH.read_text(encoding="utf-8") if REGISTRY_PATH.is_file() else ""
        if old != text:
            print("REGISTRY.md 与脚本现状不一致 —— 请跑：python scripts/gen_scripts_registry.py")
            return 1
        print(f"REGISTRY.md 与脚本现状一致（{len(rows)} 个脚本）")
        return 0
    with open(REGISTRY_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"已写入 {REGISTRY_PATH.relative_to(ROOT)}（{len(rows)} 个脚本）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
