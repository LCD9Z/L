# -*- coding: utf-8 -*-
r"""静默失效扫描器（silent-failure scanner）。

## 为什么需要这个

本项目反复出现**同一类缺陷**：**不报错的失效**。

| 已发现的实例 | 表现 |
|------|------|
| `_norm_date` 把 `pd.NaT` 写成字符串 `"NaT"` | 日期字段变成垃圾值，无异常 |
| `load_certified_csv` 白名单漏 `turnover` | 打分函数一个分项**恒为 0** |
| `revisions` 字段 | 因上述 NaT 问题**恒等于 3** |
| `market_regime` 要求「≥2 指数一致」 | 离线只有 1 个指数 → **永远返回 RANGE** |
| `score_history` 的换手率分项 | 加载器丢字段 → 过线率 6.65% vs 应有的 18.71% |

共同点：**CSV 有值、代码有逻辑、中间少一环，所有静态检查都过**。
这类缺陷只能靠**针对性扫描 + 契约断言**防住，靠读代码读不出来。

## 扫描的 5 类模式

1. **`except` 被吞**：异常被静默丢弃，调用方无从得知
2. **数据字段静默默认值**：`x.get(k) or 0` —— 缺失被伪装成"值为 0"
3. **`Optional` 返回未标注**：返回 `None` 但签名没写（调用方容易直接算术）
4. **可疑的恒真/恒假守卫**：比较的字面量阈值与可用数据规模明显不匹配
5. **未使用的数据列**：数据集里有列，但代码从不读

## 用法

::

    python scripts/scan_silent_failures.py            # 全部扫描
    python scripts/scan_silent_failures.py --json out.json
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".workbuddy-ai", "deliverables", "node_modules"}
# 数据/统计脚本里的 `or 0` 多为**展示层兜底**，风险低于核心模块
CORE_HINT_DIRS = ("", "factors", "risk", "pit", "ashare", "alpha", "validation",
                  "reporting", "corporate", "runtime", "regime", "stage2", "track")


def _iter_py(root: Path):
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def _is_test(path: Path) -> bool:
    return path.name.startswith("test_") or "tests" in path.parts


# ---------------------------------------------------------------------------
# ① except 被吞
# ---------------------------------------------------------------------------

def scan_swallowed_exceptions(root: Path) -> List[Dict[str, Any]]:
    out = []
    for p in _iter_py(root):
        if _is_test(p):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = node.body
            # 只有 pass / ... 的 handler = 完全吞掉
            swallowed = (len(body) == 1 and isinstance(body[0], ast.Pass))
            if swallowed:
                out.append({
                    "file": str(p.relative_to(root)),
                    "line": node.lineno,
                    "type": (ast.unparse(node.type) if node.type else "bare except"),
                })
    return out


# ---------------------------------------------------------------------------
# ② 数据字段静默默认值
# ---------------------------------------------------------------------------

_DEFAULT_SENTINELS = {"0", "0.0", "0.00", '""', "''", "[]", "{}", "None", "False"}


def scan_silent_defaults(root: Path) -> List[Dict[str, Any]]:
    out = []
    for p in _iter_py(root):
        if _is_test(p):
            continue
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(p))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            # `X or <sentinel>` —— 缺失/假值被伪装成默认值
            if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or):
                continue
            if len(node.values) < 2:
                continue
            left = node.values[0]
            # 只关心「取字段」这一类：call / subscript / attribute
            is_field = isinstance(left, (ast.Call, ast.Subscript, ast.Attribute))
            if not is_field:
                continue
            tail = node.values[-1]
            try:
                txt = ast.unparse(tail)
            except Exception:
                continue
            if txt in _DEFAULT_SENTINELS:
                out.append({
                    "file": str(p.relative_to(root)),
                    "line": node.lineno,
                    "expr": ast.unparse(node)[:100],
                    "sentinel": txt,
                })
    return out


# ---------------------------------------------------------------------------
# ③ Optional 返回但签名未标注
# ---------------------------------------------------------------------------

def scan_unannotated_optional(root: Path) -> List[Dict[str, Any]]:
    """函数体内存在 `return None`，但签名既无 `Optional` 也无默认 `None` 参数。"""
    out = []
    for p in _iter_py(root):
        if _is_test(p):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            returns_none = any(
                isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
                and n.value.value is None
                for n in ast.walk(fn)
            )
            if not returns_none:
                continue
            ann = ast.unparse(fn.returns) if fn.returns else ""
            if "Optional" in ann or "None" in ann:
                continue
            out.append({"file": str(p.relative_to(root)), "line": fn.lineno,
                        "func": fn.name, "annotation": ann or "(无)"})
    return out


# ---------------------------------------------------------------------------
# ④ 可疑的恒真/恒假守卫（字面量阈值 vs 可用数据规模）
# ---------------------------------------------------------------------------

# (文件模式, 比较运算符, 阈值, 说明) —— 人工登记，针对**已实际发生过**的坑
KNOWN_GUARD_RISKS = [
    {"pattern": "market_regime.py", "expr": "bulls >= 2",
     "risk": "离线数据集只有 1 个指数 → 恒假 → 永远返回 RANGE",
     "status": "已修（单指数降级 + degraded 标记）"},
]


def scan_guards(root: Path) -> List[Dict[str, Any]]:
    out = []
    for entry in KNOWN_GUARD_RISKS:
        p = root / entry["pattern"]
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        if entry["expr"] in src:
            out.append({**entry, "file": entry["pattern"],
                        "line": next((i + 1 for i, ln in enumerate(src.splitlines())
                                      if entry["expr"] in ln), 0)})
    return out


# ---------------------------------------------------------------------------
# ⑤ 数据集列 vs 代码读取（契约检查）
# ---------------------------------------------------------------------------

def scan_unused_dataset_columns(root: Path, dataset: str) -> Dict[str, Any]:
    """列出数据集 CSV 的列，与代码里出现过的列名对照。"""
    sample = Path(dataset) / "stocks"
    if not sample.is_dir():
        return {"available": False, "dataset": dataset}
    csvs = sorted(sample.glob("*.csv"))[:1]
    if not csvs:
        return {"available": False, "dataset": dataset}
    with csvs[0].open(encoding="utf-8", newline="") as fh:
        import csv as _csv
        cols = next(_csv.reader(fh))
    code_text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in _iter_py(root)
        if not _is_test(p))
    unused = [c for c in cols if c not in code_text]
    return {"available": True, "dataset": dataset, "columns": cols,
            "never_referenced": unused}


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="静默失效扫描器")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v3")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    print("=" * 90)
    print("静默失效扫描（本项目反复出现的缺陷类型：**不报错的失效**）")
    print("=" * 90)

    swallowed = scan_swallowed_exceptions(REPO_ROOT)
    defaults = scan_silent_defaults(REPO_ROOT)
    unannotated = scan_unannotated_optional(REPO_ROOT)
    guards = scan_guards(REPO_ROOT)
    cols = scan_unused_dataset_columns(REPO_ROOT, args.dataset)

    print(f"\n① 被吞掉的异常（except: pass）          : {len(swallowed)} 处")
    for r in swallowed:
        print(f"     {r['file']}:{r['line']}  ({r['type']})")

    print(f"\n② 数据字段静默默认值（x or <sentinel>）  : {len(defaults)} 处")
    by_file: Dict[str, int] = {}
    for r in defaults:
        by_file[r["file"]] = by_file.get(r["file"], 0) + 1
    for f, n in sorted(by_file.items(), key=lambda kv: -kv[1])[:10]:
        print(f"     {f}: {n} 处")

    print(f"\n③ 返回 None 但签名未标注 Optional      : {len(unannotated)} 处")
    for r in unannotated[:10]:
        print(f"     {r['file']}:{r['line']}  {r['func']}() -> {r['annotation']}")

    print(f"\n④ 已知的守卫风险（人工登记）            : {len(guards)} 处")
    for r in guards:
        print(f"     {r['file']}:{r['line']}  `{r['expr']}`")
        print(f"       风险：{r['risk']}")
        print(f"       状态：{r['status']}")

    print("\n⑤ 数据集列 vs 代码引用")
    if cols.get("available"):
        print(f"     列：{cols['columns']}")
        if cols["never_referenced"]:
            print(f"     ⚠️ 代码从未引用的列：{cols['never_referenced']}")
        else:
            print("     ✅ 所有列都被代码引用过")
    else:
        print(f"     数据集不可用（{args.dataset}），跳过")

    print("\n" + "=" * 90)
    print("判读")
    print("=" * 90)
    print("  · ① 类（吞异常）：**逐处判断**，并非都是缺陷 —— 数据源不可用时的诚实降级是合理的，")
    print("    但**任何一处都可能让上游缺陷静默**，应确保每处都有注释说明为何可吞。")
    print("  · ② 类（静默默认值）：**数量最多**，风险分级 ——")
    print("    展示/统计层的兜底可接受；**核心模块**（factors/risk/pit/ashare）里的应逐个复核。")
    print("  · ③ 类：签名未标 Optional → 调用方容易直接对 None 做算术（运行时才炸）。")
    print("  · ⑤ 类：**本项目 turnover 缺陷正是这一类**（列有值、代码不读）。")

    if args.json:
        payload = {"swallowed_exceptions": swallowed, "silent_defaults": defaults,
                   "unannotated_optional": unannotated, "guard_risks": guards,
                   "dataset_columns": cols}
        # ⚠️ 必须显式 newline="\n" —— Windows 上 Path.write_text 默认把 \n 转成 \r\n，
        # 会让 tests/test_module_splits.py::test_line_endings_are_lf 失败。
        # （本脚本首版就踩了这个坑，与本报告 §2 讨论的"静默"同类：不报错，但产物不合规。）
        with Path(args.json).open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"\n结果已写入: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
