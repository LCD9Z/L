# -*- coding: utf-8 -*-
"""Python 版本兼容性守卫测试。

背景：项目声明支持 Python >= 3.10，但历史上 `agents.py` / `data_fetcher.py`
曾使用 PEP 701（Python 3.12+）才允许的「f-string 替换字段内复用外层同引号」写法，
导致 3.10 / 3.11 下直接 SyntaxError。本测试防止该问题回归。

检测方式：
  1. 优先用 ruff（`--target-version py310`）做权威语法检查（CI 中可用）；
  2. ruff 不可用时，退化为 tokenize 扫描（仅能在 3.12+ 解释器上做近似检查）。
"""
import glob
import os
import shutil
import subprocess
import sys

import pytest

SOURCE_FILES = sorted(
    f for f in glob.glob("*.py")
    if not f.startswith("test_") and f != "conftest.py"
)


def _find_ruff():
    """定位 ruff 可执行文件。

    依次尝试：PATH → 当前解释器同级的 Scripts/bin 目录 → **隔离 venv**（复用 run_ci 的解析）。
    返回可调用的 argv 前缀列表，找不到则返回 None。

    ⚠️ 2026-10-11 实测：本机 ruff **既不在 PATH、也不在系统解释器同级目录**，
    而 WorkBuddy 把 ruff/mypy 装在隔离 venv
    （`~/.workbuddy*/binaries/python/envs/default/Scripts`）。
    原实现到此返回 `None` → 下面的 py310 权威语法检查**被静默跳过**，
    而 CI 汇总只多一行「跳过 1」、**不会失败** —— 属"不报错的失效"，
    正是本项目最警惕的一类缺陷。故补上隔离 venv 解析。
    """
    exe = shutil.which("ruff") or shutil.which("ruff.exe")
    if exe:
        return [exe]
    bindir = os.path.dirname(sys.executable)
    for name in ("ruff", "ruff.exe"):
        cand = os.path.join(bindir, name)
        if os.path.exists(cand):
            return [cand]
    # 复用 run_ci 的隔离 venv 解析 —— 它已含「跳过已损坏 venv」的校验，
    # 避免两处候选列表各自漂移（cf. 凭据扫描「共用而非内联」的守卫原则）。
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        import run_ci
        found = run_ci._find_tool_exe("ruff")
        if found:
            return [found]
    except (ImportError, AttributeError, OSError):
        pass
    return None


RUFF = _find_ruff()


def test_sources_exist():
    """确保扫描目标非空，避免测试因路径问题变成空跑。"""
    assert len(SOURCE_FILES) > 50, f"源文件数量异常: {len(SOURCE_FILES)}"


@pytest.mark.skipif(RUFF is None, reason="ruff 未安装，跳过权威语法检查")
def test_no_py310_incompatible_syntax_via_ruff():
    """用 ruff 以 py310 为目标检查语法兼容性。"""
    proc = subprocess.run(
        RUFF + ["check", ".", "--target-version", "py310", "--output-format", "concise"],
        capture_output=True, text=True,
    )
    offenders = [
        line for line in (proc.stdout + proc.stderr).splitlines()
        if "invalid-syntax" in line
    ]
    assert offenders == [], (
        "发现 Python 3.10 不兼容语法（可能是 PEP 701 嵌套引号）:\n"
        + "\n".join(offenders)
    )


def test_no_pep701_nested_quote_pattern():
    """兜底：扫描源码中 f-string 替换字段复用外层同引号的模式。

    这是对 PEP 701 的反向守卫 —— 该语法在 3.12+ 合法、在 3.10/3.11 非法。
    采用保守的文本扫描：命中即报错，允许通过注释显式豁免。
    """
    offenders = []
    for path in SOURCE_FILES:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                stripped = line.strip()
                if stripped.startswith("#") or "noqa: pep701" in line:
                    continue
                # f""" ... {expr("...")} ... """ —— 替换字段内出现 " 与三引号定界冲突
                for delim in ('f"""', "f'''"):
                    if delim in line:
                        body = line.split(delim, 1)[1]
                        # 字段内出现两个连续的双/单引号，且与外层定界相同
                        same = '""' if delim == 'f"""' else "''"
                        if same in body and "{" in body and "}" in body:
                            offenders.append(f"{path}:{lineno}: {stripped[:100]}")
    assert offenders == [], (
        "疑似 PEP 701 嵌套同引号写法（Python 3.12+ 专有）:\n" + "\n".join(offenders)
    )


def test_python_version_floor_is_documented():
    """requirements.txt 与 mypy.ini 声明的 Python 版本下限应一致。"""
    with open("requirements.txt", encoding="utf-8") as f:
        req = f.read()
    assert "3.10" in req, "requirements.txt 应声明 Python 版本下限"

    with open("mypy.ini", encoding="utf-8") as f:
        mypy_cfg = f.read()
    assert "python_version = 3.10" in mypy_cfg, "mypy.ini 应与 requirements.txt 口径一致"

    with open("ruff.toml", encoding="utf-8") as f:
        ruff_cfg = f.read()
    assert 'target-version = "py310"' in ruff_cfg, "ruff.toml 应与 requirements.txt 口径一致"


# ---------------------------------------------------------------------------
# mypy exclude 的路径段语义
# ---------------------------------------------------------------------------

def _mypy_exclude_pattern() -> str:
    import configparser

    parser = configparser.ConfigParser()
    parser.read("mypy.ini", encoding="utf-8")
    return parser["mypy"]["exclude"]


def test_mypy_exclude_does_not_swallow_source_files():
    """mypy 的 exclude 必须按**路径段**匹配，不能命中文件名子串。

    历史缺陷：未锚定的 `build` 片段使 `scripts/build_tdx_dataset.py` 与
    `pit_universe_builder.py` 被静默排除在类型检查之外
    （目录模式报 186 个文件，而根目录实际有 188 个 .py）。
    整个模块逃过类型检查是静默失效，因此这里显式守卫。
    """
    import re

    pattern = re.compile(_mypy_exclude_pattern())
    real_sources = [
        "scripts/build_tdx_dataset.py",
        "pit_universe_builder.py",
        "distance_metric.py",
        "rebuild_cache.py",
    ]
    for name in real_sources:
        assert not pattern.search(name), f"{name} 被 mypy exclude 误伤，将不被检查"


def test_mypy_exclude_still_skips_generated_directories():
    """反向守卫：同名目录仍须被排除（否则缓存/构建产物会进入检查）。"""
    import re

    pattern = re.compile(_mypy_exclude_pattern())
    excluded_paths = [
        "build/thing.py",
        "dist/thing.py",
        "__pycache__/thing.py",
        ".mypy_cache/thing.py",
        "a/b/dist/thing.py",
    ]
    for path in excluded_paths:
        assert pattern.search(path), f"{path} 应被 mypy exclude 排除"


def test_mypy_directory_mode_covers_every_source_file():
    """根目录所有 .py 都应落在 exclude 之外（与目录模式的覆盖数一致）。"""
    import re
    from pathlib import Path

    pattern = re.compile(_mypy_exclude_pattern())
    skipped = [p.name for p in Path(".").glob("*.py") if pattern.search(p.name)]
    assert skipped == [], f"以下源文件被 mypy exclude 静默跳过: {skipped}"


# ---------------------------------------------------------------------------
# ruff 解析守卫（2026-10-11 的静默降级）
# ---------------------------------------------------------------------------
#
# 背景：本机 ruff 既不在 PATH、也不在系统解释器同级目录，而 WorkBuddy 把它装在
# 隔离 venv。原 `_find_ruff()` 返回 None → 上面的 py310 权威语法检查被
# **静默跳过**（CI 只多一行「跳过 1」，仍然 PASS）。以下两条锁住该行为。

def _isolated_venv_ruff() -> str | None:
    """本机隔离 venv 里的 ruff 路径（存在才返回）。"""
    sub = "Scripts" if os.name == "nt" else "bin"
    for base in (os.path.expanduser("~/.workbuddy/binaries/python/envs/default"),
                 os.path.expanduser("~/.workbuddy-ai/binaries/python/envs/default")):
        for name in ("ruff", "ruff.exe"):
            cand = os.path.join(base, sub, name)
            if os.path.exists(cand):
                return cand
    return None


def test_ruff_resolution_uses_isolated_venv_when_present():
    """⚠️ 隔离 venv 里有 ruff 时，解析**必须**成功 —— 否则权威检查被静默跳过。

    这是环境自适应断言：本机没有 ruff 时跳过（保持原有的优雅降级），
    但只要 ruff 就在隔离 venv 里，解析失败就必须**大声失败**，而不是默默少跑一项检查。
    """
    venv_ruff = _isolated_venv_ruff()
    if venv_ruff is None:
        pytest.skip("本机隔离 venv 未安装 ruff")
    assert RUFF is not None, (
        f"隔离 venv 有 ruff（{venv_ruff}）但解析失败 → "
        f"test_no_py310_incompatible_syntax_via_ruff 会被静默跳过")


def test_find_ruff_falls_back_to_venv_candidates(tmp_path, monkeypatch):
    """PATH 与解释器同级都没有 ruff 时，必须继续在隔离 venv 里找。"""
    sub = "Scripts" if os.name == "nt" else "bin"
    venv = tmp_path / "venv"
    (venv / sub).mkdir(parents=True)
    fake = venv / sub / ("ruff.exe" if os.name == "nt" else "ruff")
    fake.write_text("", encoding="utf-8")

    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    import run_ci
    monkeypatch.setattr(run_ci, "_VENV_CANDIDATES", (str(venv),))

    assert _find_ruff() == [str(fake)]


def test_find_ruff_returns_none_when_nowhere(tmp_path, monkeypatch):
    """处处都没有 ruff 时返回 None（保持原有优雅降级语义，不得抛异常）。"""
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    import run_ci
    monkeypatch.setattr(run_ci, "_VENV_CANDIDATES", (str(tmp_path / "nope"),))

    assert _find_ruff() is None
