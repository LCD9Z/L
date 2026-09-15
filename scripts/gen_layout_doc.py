# -*- coding: utf-8 -*-
"""从真实仓库状态生成 `DIRECTORY_LAYOUT.md`（目录全景）。

用法::

    python scripts/gen_layout_doc.py            # 写入 DIRECTORY_LAYOUT.md
    python scripts/gen_layout_doc.py --check    # 只校验是否同步（不写文件，供测试/CI 用）
    python scripts/gen_layout_doc.py --stdout   # 打印到标准输出

## 为什么会有这个脚本

`DIRECTORY_LAYOUT.md` 长期处于「文档声明自动生成、但生成器不在仓库里」的状态，
于是它静默漂移：漏掉了后来新增的 `console/` 包、`main.py` 仍写 402 行
（实际已拆为 `console/` 包）、3 个数据准备脚本迁走后仍列在根目录。

本脚本让那句「请勿手工编辑」**成为事实**，并提供 `--check` 把
「文档与真实结构一致」变成可断言的不变量。

## 溯源（2026-09-15）

初版生成器从未入库，只存在于一个会话 scratch 目录
（`…/WorkBuddy/2026-09-13-15-48-32/gen_layout_doc.py`，含硬编码绝对路径）。
本文件是它的**重构版**，口径与原版保持一致，可用原版输出做逐字节对照验证：

    原版输出与本文档的差异应**只有**：
    1. 首部说明（补 `scripts/` 前缀 + 生成/校验命令）
    2. 「分类依据」一行（把含糊的"有多少模块 import 它"改为
       "有多少**根目录**模块 import 它"，与实际实现一致）

新增能力：`--check`（结构漂移检测）、根目录由 `__file__` 推导（不再硬编码）、
跳过目录按**路径段**匹配（原版用子串匹配，`build` 会误伤 `builder*`）。

## 口径（刻意写死，避免歧义）

- **行数**：`len(text.splitlines())`，与 `wc -l` 一致（文件以换行结尾时）。
  注意行数是**生成时刻的快照** —— 任何改动都会让它变化，
  故 `--check` 不比对行数（见文末说明）。
- **入边**：有多少**根目录**模块 import 它（排除自身）。刻意只统计根目录引用者，
  与「出边(根)」同为根目录视角，二者才可对照。
- **出边(根)**：该模块 import 的**根目录**模块数（去重，排除自身）。
- **不计入**：`tests/` 与 `scripts/` 的引用 —— 它们不代表架构耦合。
- **分类**：
  - 「门面 / 入口 / 门禁工具」= :data:`ROOT_ENTRY_MODULES` 显式清单
    （这一分类依据是**用途**而非依赖边，无法从图上推导）；
  - 「高耦合核心」= 其余模块中 `入边 >= 2 or 出边 >= 1`；
  - 「零出边单例」= 剩下的（`入边 <= 1 and 出边 == 0`）。
- **`--check` 只比对结构指纹**（包集合、各包模块集合、根目录模块集合），
  **不比对行数** —— 行数随每次改动变化，纳入门禁会造成无意义的持续红。
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple, TypedDict

ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = ROOT / "DIRECTORY_LAYOUT.md"

#: 不参与「架构」统计的目录：测试与一次性脚本不代表模块耦合
NON_ARCH_DIRS = frozenset({"tests", "scripts"})

#: 归入「门面 / 入口 / 门禁工具」的根目录模块。
#: 显式清单 —— 这一分类靠的是**用途**（对外门面、程序入口、门禁工具），
#: 与依赖边无关，因此无法从 import 图上推导。
ROOT_ENTRY_MODULES: Tuple[str, ...] = (
    "conftest",
    "credential_scan",
    "data_fetcher",
    "main",
    "paper_trading",
    "run_ci",
    "stock_god",
)

#: 总览之后的补充说明（手写知识，脚本原样保留）
EXTRA_NOTES = """\
> 注：`fetch/` 是 `data_fetcher.py` 门面背后的实现包——
> **对外请继续用 `from data_fetcher import ...`**，不要直接依赖 `fetch.*`。\
"""

#: 文档结尾的「为什么这些留在根目录」（手写知识，脚本原样保留）
WHY_AT_ROOT = """\
## 为什么这些留在根目录

1. **门面（`data_fetcher.py` / `agents.py`）**：实现已下沉到 `fetch/` 等包，
   门面保留是为让既有 `from X import ...` 全部不变。
2. **高耦合核心**：依赖边密集，强行入包只会把「根目录的耦合」搬成
   「跨包的耦合」，净收益为负（项目红线：划包先看依赖边，再看名字）。
3. **零出边单例**：彼此没有依赖边，按名字硬凑成包属于「名义分组」，
   会制造虚假内聚——与本项目『不许自欺』的原则相悖。
4. **`run_ci.py` / `credential_scan.py` / `conftest.py`**：门禁与 pytest 配置，
   文档与测试均按顶层路径引用，刻意留在根目录。\
"""


def _iter_py(root: Path) -> List[Path]:
    """递归收集仓库内的 `.py`（跳过缓存与版本库目录）。"""
    skip = {"__pycache__", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
    out: List[Path] = []
    for path in root.rglob("*.py"):
        if any(part in skip for part in path.relative_to(root).parts):
            continue
        out.append(path)
    return sorted(out)


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def _module_docstring(path: Path) -> str:
    """取模块级 docstring（已 dedent + strip），无则返回空串。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return ""
    return (ast.get_docstring(tree) or "").strip()


def _imported_tops(path: Path) -> Set[str]:
    """该文件 import 的顶层模块名集合（含相对导入的解析结果）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return set()

    # 相对导入需换算层级：`from .x import y` 在本项目中一律指向同包
    pkg_parts = path.relative_to(ROOT).parts[:-1]

    tops: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                tops.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对导入
                base = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                if node.module:
                    base = (*base, *node.module.split("."))
                if base:
                    tops.add(base[0])
                continue
            if node.module:
                tops.add(node.module.split(".")[0])
    return tops


def discover_packages() -> List[str]:
    """子包 = 含 `__init__.py` 的顶层目录（`tests/` `scripts/` 无 `__init__`）。"""
    return sorted(
        p.name
        for p in ROOT.iterdir()
        if p.is_dir() and (p / "__init__.py").is_file() and p.name not in NON_ARCH_DIRS
    )


def _package_modules(pkg: str) -> List[str]:
    return sorted(p.stem for p in (ROOT / pkg).glob("*.py") if p.stem != "__init__")


def build_graph() -> Tuple[Dict[str, int], Dict[str, int]]:
    """返回 `(入边, 出边)` 两个字典，键为**根目录模块名**。

    口径（与本文档历次发布版本一致，勿轻改 —— 改了会让历史数字失去可比性）：

    - **入边**：有多少**根目录**模块 import 它（排除自身）。
      刻意只统计根目录引用者 —— 该列衡量的是「根目录对它的依赖程度」，
      与「出边(根)」同为根目录视角，二者才可对照。
    - **出边(根)**：该模块 import 的**根目录**模块数（去重，排除自身）。

    注：`tests/` 与 `scripts/` 的引用不计入 —— 它们不代表架构耦合。
    """
    root_modules = {p.stem for p in ROOT.glob("*.py")}
    arch_files = [
        p
        for p in _iter_py(ROOT)
        if not any(part in NON_ARCH_DIRS for part in p.relative_to(ROOT).parts[:-1])
    ]

    in_edges: Dict[str, int] = dict.fromkeys(root_modules, 0)
    out_edges: Dict[str, int] = {}

    for path in arch_files:
        tops = _imported_tops(path)
        if path.parent == ROOT:
            # 出边：根目录模块 → 它依赖的根目录模块
            out_edges[path.stem] = len(tops & root_modules - {path.stem})
            # 入边：只由**根目录**模块贡献（见 docstring 口径说明）
            for name in tops & root_modules:
                if name != path.stem:
                    in_edges[name] += 1

    return in_edges, out_edges


def _bucket(name: str, in_edges: Dict[str, int], out_edges: Dict[str, int]) -> str:
    if name in ROOT_ENTRY_MODULES:
        return "entry"
    if in_edges.get(name, 0) >= 2 or out_edges.get(name, 0) >= 1:
        return "core"
    return "leaf"


class LayoutFingerprint(TypedDict):
    """结构指纹：只描述「有哪些包、每个包有哪些模块」，不含行数。"""

    packages: List[str]
    package_modules: Dict[str, List[str]]
    root_modules: List[str]


def structural_fingerprint() -> LayoutFingerprint:
    """结构指纹：`--check` 只比对这部分，不比对行数。"""
    pkgs = discover_packages()
    return {
        "packages": pkgs,
        "package_modules": {p: _package_modules(p) for p in pkgs},
        "root_modules": sorted(p.stem for p in ROOT.glob("*.py")),
    }


def render() -> str:
    pkgs = discover_packages()
    in_edges, out_edges = build_graph()

    pkg_module_count = 0
    pkg_line_total = 0
    blocks: List[str] = []

    for pkg in pkgs:
        modules = _package_modules(pkg)
        lines = {m: _line_count(ROOT / pkg / f"{m}.py") for m in modules}
        total = sum(lines.values())
        pkg_module_count += len(modules)
        pkg_line_total += total

        doc = _module_docstring(ROOT / pkg / "__init__.py")
        duty = doc.splitlines()[0].strip() if doc else "（未写包级说明）"

        rows = "\n".join(f"| `{pkg}/{m}.py` | {lines[m]:,} |" for m in modules)
        block = f"### `{pkg}/`　（{len(modules)} 模块，约 {total:,} 行）\n\n"
        block += f"**职责**：{duty}\n\n"
        if doc:
            block += (
                "<details><summary>包级说明与红线（点击展开）</summary>\n\n"
                f"```\n{doc}\n```\n\n</details>\n\n"
            )
        block += f"| 模块 | 行数 |\n|------|-----:|\n{rows}\n"
        blocks.append(block)

    root_modules = sorted(p.stem for p in ROOT.glob("*.py"))
    root_line_total = sum(_line_count(ROOT / f"{m}.py") for m in root_modules)

    buckets: Dict[str, List[str]] = {"entry": [], "core": [], "leaf": []}
    for name in root_modules:
        buckets[_bucket(name, in_edges, out_edges)].append(name)

    titles = {
        "entry": ("门面 / 入口 / 门禁工具", "### 门面 / 入口 / 门禁工具"),
        "core": ("高耦合核心（被多处依赖或依赖多处）", "### 高耦合核心（被多处依赖或依赖多处）"),
        "leaf": ("零出边单例（不成族，刻意留根）", "### 零出边单例（不成族，刻意留根）"),
    }
    root_blocks: List[str] = []
    for key in ("entry", "core", "leaf"):
        _, heading = titles[key]
        rows = "\n".join(
            f"| `{m}.py` | {_line_count(ROOT / f'{m}.py'):,} | "
            f"{in_edges.get(m, 0)} | {out_edges.get(m, 0)} |"
            for m in buckets[key]
        )
        root_blocks.append(
            f"{heading}\n\n"
            "| 模块 | 行数 | 入边 | 出边(根) |\n"
            "|------|-----:|-----:|--------:|\n"
            f"{rows}\n"
        )

    header = (
        "# 目录全景（分层后）\n\n"
        "> 本文件由 `scripts/gen_layout_doc.py` **从真实仓库状态自动生成**，请勿手工编辑；\n"
        "> 每次移动模块后重新生成即可，避免文档与实际结构漂移。\n"
        "> 生成命令：`python scripts/gen_layout_doc.py`　校验：`python scripts/gen_layout_doc.py --check`\n\n"
        "## 总览\n\n"
        "| 指标 | 值 |\n"
        "|------|----|\n"
        f"| 子包数 | **{len(pkgs)}** |\n"
        f"| 已入包模块 | **{pkg_module_count}**（约 {pkg_line_total:,} 行） |\n"
        f"| 根目录 `.py` | **{len(root_modules)}**（约 {root_line_total:,} 行） |\n"
        "| 分层前（起点） | 188 个平铺在根目录，零子目录 |\n"
        "| `tests/` / `scripts/` | 第一轮迁出 |\n\n"
        f"{EXTRA_NOTES}\n\n"
        "## 子包\n\n"
    )

    return (
        header
        + "\n".join(blocks)
        + "\n## 根目录剩余模块\n\n"
        + "分类依据：`出边(根)`=该模块 import 的根目录其他模块数；"
        + "`入边`=有多少**根目录**模块 import 它。\n"
        + "（`tests/` 与 `scripts/` 的引用不计入；行数为生成时刻快照。）\n\n"
        + "\n".join(root_blocks)
        + "\n"
        + WHY_AT_ROOT
        + "\n"
    )


def _extract_fingerprint_from_doc(text: str) -> LayoutFingerprint:
    """从既有文档反推结构指纹，用于 `--check` 比对。"""
    packages: List[str] = []
    package_modules: Dict[str, List[str]] = {}
    current: str | None = None
    root_modules: List[str] = []
    in_root_section = False

    for line in text.splitlines():
        if line.startswith("### `") and "/`" in line:
            pkg = line.split("`", 2)[1].rstrip("/")
            packages.append(pkg)
            package_modules[pkg] = []
            current = pkg
            in_root_section = False
            continue
        if line.startswith("## 根目录剩余模块"):
            in_root_section = True
            current = None
            continue
        if line.startswith("## 为什么这些留在根目录"):
            in_root_section = False
            continue
        if line.startswith("| `"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not cells:
                continue
            target = cells[0].strip("`")
            if current and "/" in target and target.startswith(current + "/"):
                package_modules[current].append(Path(target).stem)
            elif in_root_section and target.endswith(".py") and "/" not in target:
                root_modules.append(Path(target).stem)

    return {
        "packages": sorted(packages),
        "package_modules": {k: sorted(v) for k, v in package_modules.items()},
        "root_modules": sorted(root_modules),
    }


def _describe_diff(
    expected: LayoutFingerprint, actual: LayoutFingerprint
) -> List[str]:
    msgs: List[str] = []
    exp_pkgs, act_pkgs = expected["packages"], actual["packages"]
    if exp_pkgs != act_pkgs:
        only_doc = sorted(set(act_pkgs) - set(exp_pkgs))
        only_real = sorted(set(exp_pkgs) - set(act_pkgs))
        if only_doc:
            msgs.append(f"文档中多出（仓库已无）的子包: {only_doc}")
        if only_real:
            msgs.append(f"仓库有但文档缺失的子包: {only_real}")

    exp_pm = expected["package_modules"]
    act_pm = actual["package_modules"]
    for pkg in sorted(set(exp_pm) & set(act_pm)):
        if exp_pm[pkg] != act_pm[pkg]:
            msgs.append(
                f"`{pkg}/` 模块不一致：文档多 {sorted(set(act_pm[pkg]) - set(exp_pm[pkg]))}，"
                f"文档缺 {sorted(set(exp_pm[pkg]) - set(act_pm[pkg]))}"
            )

    if expected["root_modules"] != actual["root_modules"]:
        msgs.append(
            "根目录模块不一致：文档多 "
            f"{sorted(set(actual['root_modules']) - set(expected['root_modules']))}，"
            "文档缺 "
            f"{sorted(set(expected['root_modules']) - set(actual['root_modules']))}"
        )
    return msgs


def check_sync() -> List[str]:
    """返回文档与仓库结构的差异清单（空列表 = 已同步）。

    供 `--check` 与守卫测试共用，避免两处各写一套比对逻辑。
    """
    if not DOC_PATH.is_file():
        return [f"缺少 {DOC_PATH.name}，请运行: python scripts/gen_layout_doc.py"]
    expected = structural_fingerprint()
    actual = _extract_fingerprint_from_doc(DOC_PATH.read_text(encoding="utf-8"))
    return _describe_diff(expected, actual)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成 / 校验 DIRECTORY_LAYOUT.md")
    ap.add_argument("--check", action="store_true", help="只校验是否同步，不写文件")
    ap.add_argument("--stdout", action="store_true", help="打印到标准输出")
    args = ap.parse_args(argv)

    if args.check:
        diffs = check_sync()
        if diffs:
            print("!! DIRECTORY_LAYOUT.md 与仓库结构不同步：")
            for msg in diffs:
                print(f"   - {msg}")
            print("   修复：python scripts/gen_layout_doc.py")
            return 1
        print("DIRECTORY_LAYOUT.md 与仓库结构一致。")
        return 0

    text = render()
    if args.stdout:
        sys.stdout.write(text)
        return 0
    DOC_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"已生成 {DOC_PATH.name}（{len(text.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
