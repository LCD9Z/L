# -*- coding: utf-8 -*-
"""代码冗余审计（**只读**）：AST 归一化重复 + 长函数 + 跨文件同名符号 + 常量重复。

## 为什么需要

「冗余太多吗」不能靠行数拍脑袋。本工具用可复现的机械判据回答四个问题：

1. **完全重复的函数体** —— 标识符归一化（变量名/参数名 → 占位符、剥 docstring）、
   **保留常量**后哈希相同的函数。这是**字节级等价**的复制粘贴，合并风险最低。
2. **同构不同值的函数体** —— 连常量一起归一化。复制后改造参数的痕迹，
   多半可参数化收敛（如 agents_analysts 的 4 个 ``generate_prompt``）。
3. **跨文件同名 helper** —— 同一名字在多文件定义：实现**相同** ⇒ 纯搬运候选；
   实现**有差异** ⇒ **口径漂移风险**（如 ``_num`` 有 10 个实现、3 种语义），
   合并前必须先定标准实现，不能默认「同名即同义」。
4. **模块级常量重复定义** —— 其中「同名同值」是纯重复；「同名不同值」多为
   各研究脚本的**事前参数**（``DEFAULT_WINDOWS`` 等），**不是缺陷、不要合并**
   （集中化会改动已登记实验的参数语义）。

## 纪律

* **只读**：只解析 git 跟踪的 .py，不写任何文件。
* 判定阈值（``min_lines`` 等）集中在函数默认参数里，**调整即改判定标准**，
  须在报告里留痕（见 ``tests/test_code_redundancy_baseline.py`` 的基线守卫）。

## 用法

    python scripts/audit_code_redundancy.py           # 人类可读报告
    python scripts/audit_code_redundancy.py --json    # 机器可读（同一份数据）
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypeVar

#: 精确重复判定的最小函数体行数。调大 = 放过小复制；调小 = 噪音增多。
MIN_LINES_EXACT = 8
#: 同构判定的最小函数体行数（同构判定本身更宽松，阈值须更高以控噪）。
MIN_LINES_ISOMORPHIC = 12
#: 跨文件同名 helper 只统计「短小」函数（> 此值视为业务主体，不列入 helper 候选）。
HELPER_MAX_LINES = 40


# ---------------------------------------------------------------------------
# AST 归一化
# ---------------------------------------------------------------------------
class _Norm(ast.NodeTransformer):
    """标识符归一化 + 剥 docstring；``norm_const=True`` 时常量也归一化。"""

    def __init__(self, norm_const: bool) -> None:
        self.norm_const = norm_const

    def visit_Name(self, node: ast.Name) -> ast.Name:
        self.generic_visit(node)
        node.id = "V"
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        self.generic_visit(node)
        node.arg = "V"
        node.annotation = None
        return node

    def visit_keyword(self, node: ast.keyword) -> ast.keyword:
        self.generic_visit(node)
        if node.arg is not None:
            node.arg = "V"
        return node

    _FnT = TypeVar("_FnT", ast.FunctionDef, ast.AsyncFunctionDef)

    def _normalize_fn(self, node: _FnT) -> _FnT:
        """剥装饰器/返回标注/docstring、函数名归一（FunctionDef 与 AsyncFunctionDef 共用）。"""
        node.decorator_list = []
        node.name = "F"
        node.returns = None
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:]  # 剥 docstring
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        return self._normalize_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        self.generic_visit(node)
        return self._normalize_fn(node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if self.norm_const:
            node.value = "C"
        return node


def norm_dump(fn_node: ast.FunctionDef, norm_const: bool) -> str:
    """函数体归一化后的 AST dump（归一化在**深拷贝**上进行，不污染原树）。"""
    node = copy.deepcopy(fn_node)
    node = _Norm(norm_const).visit(node)
    return ast.dump(node, include_attributes=False)


def iter_functions(tree: ast.AST) -> List[Tuple[str, Any]]:
    """``(限定名, 节点)`` 全量遍历，含类方法与嵌套函数。

    节点类型放宽为 ``Any``：FunctionDef 与 AsyncFunctionDef 在 typeshed 中
    ``end_lineno`` 均为 ``int | None``，调用方（collect）统一做兜底更简单。
    """
    out: List[Tuple[str, Any]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = prefix + child.name
                out.append((qual, child))
                walk(child, qual + ".")
            else:
                walk(child, prefix)

    walk(tree, "")
    return out


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------
def git_py_files(root: Path) -> List[Path]:
    """git 跟踪的 .py（**不含**未跟踪/忽略文件 —— 判定须以入库代码为准）。"""
    proc = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=str(root), capture_output=True, text=True, check=True,
    )
    return sorted(root / f for f in proc.stdout.splitlines() if f.strip())


def _area_of(rel: str) -> str:
    if rel.startswith("tests/"):
        return "tests"
    if rel.startswith("scripts/"):
        return "scripts"
    return "prod"


def collect(root: Path) -> Dict[str, Any]:
    """解析全部受跟踪 .py，返回函数清单 / 常量定义 / 分区统计。

    单文件解析失败**记入 ``parse_errors`` 并继续** —— 一个坏文件不应让全库审计失败；
    但调用方必须检查该字段（静默跳过整个文件才是失效）。
    """
    funcs: List[Dict[str, Any]] = []
    const_names: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    area_stats: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    parse_errors: List[str] = []

    for path in git_py_files(root):
        rel = path.relative_to(root).as_posix()
        area = _area_of(rel)
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            src = path.read_text(encoding="utf-8", errors="replace")
        area_stats[area][0] += 1
        area_stats[area][1] += src.count("\n")
        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError as exc:
            parse_errors.append(f"{rel}:{exc.lineno}: {exc.msg}")
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and (
                        target.id.isupper() or target.id.startswith("_")
                    ):
                        const_names[target.id].append((rel, node.lineno))
        for qual, fn in iter_functions(tree):
            if not fn.body:
                continue
            funcs.append({
                "file": rel,
                "area": area,
                "qual": qual,
                "lineno": fn.lineno,
                "lines": fn.end_lineno - fn.lineno + 1,
                "h_exact": hashlib.sha1(norm_dump(fn, False).encode()).hexdigest()[:12],
                "h_isomorph": hashlib.sha1(norm_dump(fn, True).encode()).hexdigest()[:12],
            })
    return {
        "funcs": funcs,
        "const_names": dict(const_names),
        "area_stats": {k: tuple(v) for k, v in area_stats.items()},
        "parse_errors": parse_errors,
    }


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------
def _dup_groups(funcs: List[Dict[str, Any]], key: str,
                min_lines: int) -> List[List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for f in funcs:
        if f["lines"] >= min_lines:
            groups[f[key]].append(f)
    return sorted(
        (g for g in groups.values() if len(g) >= 2),
        key=lambda g: -sum(x["lines"] for x in g),
    )


def exact_duplicate_groups(funcs: List[Dict[str, Any]],
                           min_lines: int = MIN_LINES_EXACT) -> List[List[Dict[str, Any]]]:
    """完全重复（标识符归一化、保留常量）的函数体组。"""
    return _dup_groups(funcs, "h_exact", min_lines)


def isomorphic_groups(funcs: List[Dict[str, Any]],
                      min_lines: int = MIN_LINES_ISOMORPHIC) -> List[List[Dict[str, Any]]]:
    """同构不同值（常量也归一化）的函数体组。"""
    return _dup_groups(funcs, "h_isomorph", min_lines)


def cross_file_helpers(funcs: List[Dict[str, Any]],
                       max_lines: int = HELPER_MAX_LINES) -> List[Dict[str, Any]]:
    """跨文件同名**短小**函数；标注实现是否相同（口径漂移风险面）。"""
    by_name: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for f in funcs:
        if f["lines"] > max_lines:
            continue
        name = f["qual"].split(".")[-1].split("<")[0]
        by_name[name][f["file"]].append(f)
    out: List[Dict[str, Any]] = []
    for name, per_file in sorted(by_name.items()):
        if len(per_file) < 2:
            continue
        same = len({f["h_exact"] for fs in per_file.values() for f in fs}) == 1
        out.append({
            "name": name,
            "same_impl": same,
            "locations": [(fl, [f["lineno"] for f in fs]) for fl, fs in per_file.items()],
        })
    return out


def constant_dups(const_names: Dict[str, List[Tuple[str, int]]]) -> List[Dict[str, Any]]:
    """在 >=2 个文件中定义的模块级常量（按名字长度过滤掉 ``__all__`` 类噪音）。"""
    out = []
    for name, locs in sorted(const_names.items()):
        if len(locs) >= 2 and len(name) >= 4:
            out.append({"name": name, "locations": locs})
    return out


def longest_functions(funcs: List[Dict[str, Any]], top: int = 20) -> List[Dict[str, Any]]:
    return sorted(funcs, key=lambda f: -f["lines"])[:top]


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def _fmt_group(g: List[Dict[str, Any]]) -> str:
    locs = ", ".join(f"{f['file']}:{f['lineno']}({f['qual']},{f['lines']}行)" for f in g)
    return locs


def render_report(data: Dict[str, Any]) -> str:
    funcs = data["funcs"]
    lines: List[str] = []
    ap = lines.append
    ap("=" * 72)
    ap("一、规模（git 跟踪 .py）")
    for area in ("prod", "scripts", "tests"):
        n_files, n_lines = data["area_stats"].get(area, (0, 0))
        ap(f"  {area:<8} {n_files:>4} 文件 {n_lines:>6} 行")
    tot_f = sum(v[0] for v in data["area_stats"].values())
    tot_l = sum(v[1] for v in data["area_stats"].values())
    ap(f"  {'合计':<8} {tot_f:>4} 文件 {tot_l:>6} 行")
    if data["parse_errors"]:
        ap(f"  ⚠️ 解析失败 {len(data['parse_errors'])} 个文件（未纳入统计，须修复）:")
        for e in data["parse_errors"]:
            ap(f"    - {e}")

    ap("=" * 72)
    ap(f"二、最长函数 Top 20（>{120} 行标 *）")
    for f in longest_functions(funcs):
        flag = "*" if f["lines"] > 120 else " "
        ap(f" {flag}{f['lines']:>4} 行  {f['file']}:{f['lineno']}  {f['qual']}")

    for key, title, min_lines in (
        ("h_exact", "三、完全重复函数体（合并风险最低）", MIN_LINES_EXACT),
        ("h_isomorph", "四、同构不同值函数体（可参数化收敛）", MIN_LINES_ISOMORPHIC),
    ):
        groups = _dup_groups(funcs, key, min_lines)
        saved = sum(sum(x["lines"] for x in g) - max(x["lines"] for x in g) for g in groups)
        ap("=" * 72)
        ap(f"{title}（{len(groups)} 组 · 每组 >= {min_lines} 行 · 每组留一份约省 {saved} 行）")
        for g in groups:
            ap(f"  {_fmt_group(g)}")

    ap("=" * 72)
    ap("五、跨文件同名 helper（同名 ≠ 同义：same=False 的合并前必须先定标准实现）")
    for h in cross_file_helpers(funcs):
        locs = "; ".join(f"{fl}:{','.join(map(str, lns))}" for fl, lns in h["locations"])
        ap(f"  {h['name']:<34} {'[实现相同]' if h['same_impl'] else '[实现有差异]'} {locs}")

    ap("=" * 72)
    ap("六、模块级常量在 >=2 个文件中重复定义（同名同值=纯重复；同名不同值=事前参数，勿合并）")
    for c in constant_dups(data["const_names"]):
        ap(f"  {c['name']:<40} " + "; ".join(f"{fl}:{ln}" for fl, ln in c["locations"]))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="代码冗余审计（只读）")
    parser.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非文本报告")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    data = collect(root)
    if args.json:
        payload = {
            "area_stats": data["area_stats"],
            "parse_errors": data["parse_errors"],
            "exact_duplicate_groups": [
                {"hash": g[0]["h_exact"], "members": _fmt_group(g)} for g in exact_duplicate_groups(data["funcs"])
            ],
            "isomorphic_groups": [
                {"hash": g[0]["h_isomorph"], "members": _fmt_group(g)} for g in isomorphic_groups(data["funcs"])
            ],
            "cross_file_helpers": cross_file_helpers(data["funcs"]),
            "constant_dups": [
                {"name": c["name"], "locations": c["locations"]} for c in constant_dups(data["const_names"])
            ],
            "longest_functions": longest_functions(data["funcs"]),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_report(data))
    return 1 if data["parse_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
