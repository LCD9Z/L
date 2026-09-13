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
from typing import Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent


def _run(cmd: List[str]) -> int:
    print(f"  $ {' '.join(cmd)}", flush=True)
    env = dict(os.environ)
    # 与 CI 环境保持一致：关闭数据源限流，避免用例被限速拖慢
    env.setdefault("FETCH_RATE_PER_SEC", "0")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("LOG_LEVEL", "WARNING")
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    return proc.returncode


def _module(module: str, args: List[str]) -> int:
    return _run([sys.executable, "-m", module, *args])


def step_syntax() -> int:
    """全部 .py 编译检查（等价于 CI 的 py_compile 步骤，但不落 .pyc）。"""
    failed: List[str] = []
    files = sorted(ROOT.glob("*.py"))
    for path in files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            failed.append(f"{path.name}:{exc.lineno}: {exc.msg}")
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


def step_compat() -> int:
    return _module("pytest", ["test_python_compat.py", "-q"])


def step_pytest() -> int:
    return _module("pytest", ["-q"])


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
