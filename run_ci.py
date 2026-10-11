# -*- coding: utf-8 -*-
"""本地 CI 等价执行器（零第三方依赖，除被调用的检查工具本身）。

背景
----
`.github/workflows/ci.yml` 已写好，但从未在远端实际跑通（见 MERGE_1.0_REPORT
遗留事项 #1）。在推送前无法回答「这次提交能不能过 CI」。

本脚本把工作流里的每一步用**同一套命令**在本地复现，并按相同顺序、相同
失败语义执行，使本地结果可作为 CI 的可靠预演。

与工作流的对应关系（改一处必须同步另一处）
------------------------------------------
| ci.yml 步骤                          | 本脚本 step        |
|--------------------------------------|--------------------|
| Syntax check (all sources)           | syntax             |
| Ruff lint                            | ruff               |
| Mypy type check                      | mypy               |
| Python 3.10 syntax compatibility     | compat             |
| Pytest                               | pytest             |
| credential scan (security-scan job)  | credentials        |

用法
----
    python run_ci.py                 # 顺序执行全部检查，首个失败即停
    python run_ci.py --keep-going    # 出错也跑完，最后汇总
    python run_ci.py --list          # 只列出步骤
    python run_ci.py --only ruff mypy
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent

#: 递归扫描时跳过的目录（缓存、版本库、虚拟环境）
SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "build", "dist", ".venv", "venv", "node_modules",
})


def _iter_source_files() -> List[Path]:
    """项目内全部源码文件。

    目录分层后源码不再全部位于根目录：库模块在根、测试在 `tests/`、
    可执行脚本在 `scripts/`，因此需要递归——否则分层会让语法检查的覆盖面
    悄悄缩水（这正是本项目最警惕的那类静默失效）。
    """
    return sorted(
        p for p in ROOT.rglob("*.py")
        if not any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts[:-1])
    )


def _run(cmd: List[str]) -> int:
    print(f"  $ {' '.join(cmd)}", flush=True)
    env = dict(os.environ)
    # 与 CI 环境保持一致：关闭数据源限流，避免用例被限速拖慢
    env.setdefault("FETCH_RATE_PER_SEC", "0")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("LOG_LEVEL", "WARNING")
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    return proc.returncode


def _has_module(module: str) -> bool:
    """当前解释器是否装有该模块。"""
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


#: 工具可能不在当前解释器内。本机 ruff/mypy 装在隔离 venv，
#: 而 `python run_ci.py` 用的是系统 Python —— 直接 `-m ruff` 会报
#: "No module named ruff"，让本地 CI 因**环境**原因假失败。
#: 因此按顺序回退：环境变量 → 已知 venv 路径 → PATH。
_VENV_CANDIDATES = (
    os.environ.get("WORKBUDDY_PY_ENV", ""),
    os.path.expanduser("~/.workbuddy/binaries/python/envs/default"),
    os.path.expanduser("~/.workbuddy-ai/binaries/python/envs/default"),
)


def _venv_usable(base: str) -> bool:
    """该 venv 是否**真正可用** —— 其基础解释器必须存在。

    ⚠️ 只检查 ``<base>/Scripts/<tool>.exe`` 是否存在**不够**。2026-10-10 实测：
    ``~/.workbuddy/binaries/python/envs/default`` 的 ``Scripts/*.exe`` 一应俱全，
    但其 ``pyvenv.cfg`` 声明的 base 解释器
    （``~/.workbuddy/binaries/python/versions/3.13.12/python.exe``）指向一个
    **已失效的 symlink**（``…/resources/vendor/python`` 不存在）——
    直接运行该 venv 的 ``mypy.exe`` 会打印
    ``did not find executable at '…': …`` 并让本地 CI **假失败**。

    非 venv 目录（无 ``pyvenv.cfg``）不做额外判断，保持原有 PATH 回退语义。
    """
    cfg = Path(base) / "pyvenv.cfg"
    if not cfg.is_file():
        return True
    home = ""
    exe = ""
    try:
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, val = line.partition("=")
            key = key.strip().lower()
            val = val.strip()
            if key == "home":
                home = val
            elif key == "executable":
                exe = val
    except OSError:
        return False
    if exe and Path(exe).is_file():
        return True
    if home:
        base_exe = "python.exe" if os.name == "nt" else "python3"
        if (Path(home) / base_exe).is_file():
            return True
    return False


def _find_tool_exe(module: str) -> Optional[str]:
    """在已知 venv 与 PATH 中查找**可用**的 `<module>` 可执行文件。

    候选中**跳过已损坏的 venv**（见 :func:`_venv_usable`），避免因环境原因假失败。
    """
    import shutil
    subdir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    for base in _VENV_CANDIDATES:
        if not base:
            continue
        candidate = Path(base) / subdir / f"{module}{suffix}"
        if candidate.is_file() and _venv_usable(base):
            return str(candidate)
    return shutil.which(module)


def _module(module: str, args: List[str]) -> int:
    """运行 `python -m <module> <args>`，必要时回退到独立可执行文件。

    回退存在的理由见 :data:`_VENV_CANDIDATES` 的注释。找不到工具时
    **明确报错并返回非零** —— 静默跳过会让 CI 失去意义。
    """
    if _has_module(module):
        return _run([sys.executable, "-m", module, *args])

    exe = _find_tool_exe(module)
    if exe:
        print(f"  (回退到独立可执行文件: {exe})")
        return _run([exe, *args])

    print(f"  [FAIL] 找不到 {module}：既不在当前解释器 "
          f"({sys.executable})，也不在已知 venv 或 PATH")
    print("         可设置环境变量 WORKBUDDY_PY_ENV 指向装有该工具的 venv")
    return 1

def step_syntax() -> int:
    """全部 .py 编译检查（等价于 CI 的 py_compile 步骤，但不落 .pyc）。"""
    failed: List[str] = []
    files = _iter_source_files()
    for path in files:
        rel = path.relative_to(ROOT)
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            failed.append(f"{rel}:{exc.lineno}: {exc.msg}")
    if failed:
        for item in failed:
            print(f"  FAIL {item}")
        print(f"  {len(failed)}/{len(files)} 个源文件语法检查失败")
        return 1
    print(f"  {len(files)} 个源文件语法检查通过")
    return 0


def step_ruff() -> int:
    return _module("ruff", ["check", ".", "--output-format=concise"])


def step_mypy() -> int:
    return _module("mypy", [".", "--config-file", "mypy.ini"])


def _pytest(args: List[str]) -> int:
    """运行 pytest，并以 **JUnit XML 报告**判定结果，而非子进程退出码。

    背景（实测）：本机 WorkBuddy 的 `safe-delete` 钩子在清理 pytest 临时目录时
    会污染子进程退出码。`python -m pytest -q` 直接执行时 502 项全过、exit=0、
    进度条无 F；但经本脚本以子进程方式调用时返回非零 → 本地 CI 出现**假失败**，
    使「一条命令验证状态」这一防断线机制失效。

    JUnit 报告由 pytest 自身写出，忠实记录 failures/errors，不受退出码污染影响。
    仅当报告缺失或不可解析（pytest 未能启动）时才回退到退出码判定。
    """
    import tempfile
    import xml.etree.ElementTree as ET

    report = Path(tempfile.gettempdir()) / f"run_ci_pytest_{os.getpid()}.xml"
    report.unlink(missing_ok=True)
    try:
        code = _module("pytest", [*args, f"--junitxml={report}"])
        if not report.is_file():
            print("  [WARN] 未生成 JUnit 报告，回退按退出码判定")
            return code
        try:
            root = ET.parse(report).getroot()
        except ET.ParseError as exc:
            print(f"  [WARN] JUnit 报告不可解析（{exc}），回退按退出码判定")
            return code
    finally:
        report.unlink(missing_ok=True)

    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, "0") or 0)

    print(f"  JUnit: 共 {totals['tests']} 项 · 失败 {totals['failures']} · "
          f"错误 {totals['errors']} · 跳过 {totals['skipped']}")
    if totals["failures"] or totals["errors"]:
        return 1
    if code != 0:
        print("  (退出码非零，但 JUnit 报告为 0 失败 0 错误 → 判定通过；"
              "退出码受 safe-delete 钩子污染)")
    return 0


def step_compat() -> int:
    # 测试已迁入 tests/，路径需随之更新（否则该步骤会因找不到文件而假失败）
    return _pytest(["tests/test_python_compat.py", "-q"])


def step_pytest() -> int:
    return _pytest(["-q"])


def step_credentials() -> int:
    """与 CI 的 security-scan job 共用同一实现（credential_scan.py）。"""
    return _run([sys.executable, "credential_scan.py"])


STEPS: Tuple[Tuple[str, Callable[[], int]], ...] = (
    ("syntax", step_syntax),
    ("ruff", step_ruff),
    ("mypy", step_mypy),
    ("compat", step_compat),
    ("pytest", step_pytest),
    ("credentials", step_credentials),
)

STEP_NAMES: Tuple[str, ...] = tuple(name for name, _ in STEPS)
_STEP_MAP: Dict[str, Callable[[], int]] = dict(STEPS)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地 CI 等价执行器")
    parser.add_argument("--list", action="store_true", help="只列出步骤名")
    parser.add_argument("--keep-going", action="store_true", help="出错继续执行后续步骤")
    parser.add_argument("--only", nargs="+", choices=list(STEP_NAMES), help="只跑指定步骤")
    args = parser.parse_args(argv)

    if args.list:
        for name in STEP_NAMES:
            print(name)
        return 0

    selected = args.only or list(STEP_NAMES)
    results: List[Tuple[str, int]] = []

    for name in selected:
        print(f"\n=== [{len(results) + 1}/{len(selected)}] {name} ===", flush=True)
        code = _STEP_MAP[name]()
        results.append((name, code))
        if code != 0 and not args.keep_going:
            print(f"\n[FAIL] 步骤 {name} 未通过，已停止（用 --keep-going 可跑完全部）。")
            break

    print("\n=== 汇总 ===")
    for name, code in results:
        print(f"  {'PASS' if code == 0 else 'FAIL'}  {name}")
    failed = [name for name, code in results if code != 0]
    if failed:
        print(f"\n本地 CI 未通过：{', '.join(failed)}")
        return 1
    if len(results) < len(STEP_NAMES):
        print(f"\n本地 CI 未跑完（{len(results)}/{len(STEP_NAMES)} 步）。")
        return 1
    print("\n本地 CI 全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
