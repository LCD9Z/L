# -*- coding: utf-8 -*-
"""run_ci（本地 CI 等价执行器）的测试。

重点是**漂移守护**：run_ci.py 与 .github/workflows/ci.yml 是对同一套检查的
两份声明。任何一份改了而另一份没跟上，本地预演就不再能代表 CI 结果——
那正是「CI 未在远端跑通」这一遗留事项的核心风险。
"""
import os

import pytest

import run_ci

WORKFLOW_PATH = run_ci.ROOT / ".github" / "workflows" / "ci.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


# --- 步骤注册 -------------------------------------------------------------

def test_step_names_and_order_are_stable():
    assert run_ci.STEP_NAMES == ("syntax", "ruff", "mypy", "compat", "pytest", "credentials")


def test_every_step_is_callable():
    for name, fn in run_ci.STEPS:
        assert callable(fn), f"步骤 {name} 不可调用"


def test_list_flag_prints_all_steps(capsys):
    assert run_ci.main(["--list"]) == 0
    printed = capsys.readouterr().out.split()
    assert printed == list(run_ci.STEP_NAMES)


def test_unknown_step_name_is_rejected():
    with pytest.raises(SystemExit):
        run_ci.main(["--only", "does-not-exist"])


# --- 语法检查步骤（不依赖外部工具，可直接跑） -----------------------------

def test_syntax_step_passes_on_repository():
    assert run_ci.step_syntax() == 0


def test_syntax_step_detects_broken_file(tmp_path, monkeypatch):
    """阳性对照：语法错误必须被抓住，否则该步骤形同虚设。"""
    bad = tmp_path / "broken.py"
    bad.write_text("def f(:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(run_ci, "ROOT", tmp_path)
    assert run_ci.step_syntax() == 1


# --- 漂移守护 -------------------------------------------------------------

def test_workflow_file_exists():
    assert WORKFLOW_PATH.exists(), "CI 工作流缺失，本地等价执行器失去参照"


def test_workflow_declares_every_check_run_ci_performs():
    """本地跑的每一项检查都必须在工作流里出现（否则本地比 CI 更严，属误报）。"""
    text = _workflow_text()
    for marker in (
        "ruff check",
        "mypy . --config-file mypy.ini",
        "pytest tests/test_python_compat.py",
        "credential_scan.py",
        "py_compile",
    ):
        assert marker in text, f"工作流缺少本地 CI 会执行的检查：{marker}"


def test_ci_has_no_check_that_local_runner_misses():
    """反向守护：工作流里不应出现本地执行器没覆盖的检查工具。"""
    text = _workflow_text()
    for tool in ("flake8", "black --check", "isort --check", "bandit"):
        assert tool not in text, f"工作流使用了本地执行器未覆盖的工具：{tool}"


def test_credential_scan_is_shared_not_inlined():
    """凭据扫描必须共用 credential_scan.py，不得在 YAML 里内联另一份实现。"""
    text = _workflow_text()
    assert "python credential_scan.py" in text
    assert "\n          grep " not in text, "凭据扫描不应再依赖内联命令"


def test_credentials_step_passes_on_repository():
    """本地执行器调用的扫描器必须对当前仓库返回 0。"""
    assert run_ci.step_credentials() == 0


def test_run_ci_targets_project_root():
    assert (run_ci.ROOT / "requirements.txt").exists()
    assert (run_ci.ROOT / "run_ci.py").exists()


# --- 工具回退：跳过已损坏的 venv（2026-10-11 环境回归的守卫） -------------
#
# 背景：本机 `~/.workbuddy/binaries/python/envs/default` 的 Scripts/*.exe 齐全，
# 但其 pyvenv.cfg 声明的 base 解释器指向**失效的 symlink**，运行该 venv 的
# mypy.exe 会打印 "did not find executable at ..." 并让本地 CI 假失败。
# 只检查可执行文件存在是不够的 —— 必须校验 venv 的基础解释器。

def _write_venv(base, *, home: str, exe: str) -> None:
    (base / "pyvenv.cfg").write_text(
        f"home = {home}\nexecutable = {exe}\n", encoding="utf-8")


def test_venv_usable_treats_plain_dir_as_usable(tmp_path):
    """非 venv 目录不做额外判断 —— 保持原有 PATH 回退语义。"""
    assert run_ci._venv_usable(str(tmp_path)) is True


def test_venv_usable_accepts_venv_with_existing_base_interpreter(tmp_path):
    base = tmp_path / "good"
    base.mkdir()
    py = tmp_path / "python.exe"
    py.write_text("", encoding="utf-8")
    _write_venv(base, home=str(tmp_path), exe=str(py))
    assert run_ci._venv_usable(str(base)) is True


def test_venv_usable_rejects_venv_with_missing_base_interpreter(tmp_path):
    """⚠️ 核心守卫：base 解释器不存在时必须判为不可用。"""
    base = tmp_path / "broken"
    base.mkdir()
    missing = tmp_path / "nope" / "python.exe"
    _write_venv(base, home=str(tmp_path / "nope"), exe=str(missing))
    assert run_ci._venv_usable(str(base)) is False


def test_find_tool_exe_skips_broken_venv(tmp_path, monkeypatch):
    """候选顺序里坏 venv 在前时，必须继续找到后面可用的那个。"""
    subdir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""

    broken = tmp_path / "broken"
    (broken / subdir).mkdir(parents=True)
    (broken / subdir / f"mypy{suffix}").write_text("", encoding="utf-8")
    _write_venv(broken, home=str(tmp_path / "nope"),
                exe=str(tmp_path / "nope" / "python.exe"))

    good = tmp_path / "good"
    (good / subdir).mkdir(parents=True)
    tool = good / subdir / f"mypy{suffix}"
    tool.write_text("", encoding="utf-8")
    py = tmp_path / "python.exe"
    py.write_text("", encoding="utf-8")
    _write_venv(good, home=str(tmp_path), exe=str(py))

    monkeypatch.setattr(run_ci, "_VENV_CANDIDATES", (str(broken), str(good)))
    assert run_ci._find_tool_exe("mypy") == str(tool)
