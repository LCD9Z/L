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

    依次尝试：PATH → 当前解释器同级的 Scripts/bin 目录 → python -m ruff。
    返回可调用的 argv 前缀列表，找不到则返回 None。
    """
    exe = shutil.which("ruff") or shutil.which("ruff.exe")
    if exe:
        return [exe]
    bindir = os.path.dirname(sys.executable)
    for name in ("ruff", "ruff.exe"):
        cand = os.path.join(bindir, name)
        if os.path.exists(cand):
            return [cand]
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
