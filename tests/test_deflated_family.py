# -*- coding: utf-8 -*-
"""``deflated_family`` 的单元测试 + 「接线生效」守卫。

对应 `DSR_IC_FAMILY_PREREG.md` 判据 A-3 / A-4。

本文件的数值判据全部来自**事前固定的口径**（预注册 §3.1），
不是对实现的复述：例如「单试验时 dsr 必须等于 psr」是一条可独立
验证的数学事实（n_trials=1 ⇒ E[max SR]=0 ⇒ 基准相同）。
"""
import ast
import pathlib
import random
from typing import Dict

import pytest

from validation.multiple_testing import (
    deflated_family,
    normal_cdf,
    sharpe_moments,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 合成序列（固定种子 ⇒ 确定性；本项目不依赖随机性通过测试）
# ---------------------------------------------------------------------------

def _series(ir: float, n: int, seed: int):
    """近似 N(ir, 1) 的逐期序列（IC 口径：单期、非年化）。"""
    rng = random.Random(seed)
    return [ir + rng.gauss(0.0, 1.0) for _ in range(n)]


# ---------------------------------------------------------------------------
# C1~C5 口径边界
# ---------------------------------------------------------------------------

def test_single_trial_dsr_equals_psr():
    """C2/C4：只有 1 次试验时没有选择偏差 ⇒ E[max SR]=0 ⇒ dsr 必须等于 psr。"""
    r = deflated_family({"only": _series(0.30, 250, seed=11)})
    t = r["trials"]["only"]
    assert r["n_trials"] == 1
    assert r["expected_max_sr"] == 0.0
    assert r["selection_bias_corrected"] is False
    assert t["dsr"] == pytest.approx(t["psr"], abs=1e-12)


def test_zero_variance_disables_correction():
    """C3/C5：族内各试验 sr 完全相同时没有选择偏差，必须显式声明未校正。"""
    a = _series(0.25, 200, seed=21)
    b = list(a)                       # 同一序列 ⇒ sr 相同 ⇒ 方差 0
    r = deflated_family({"a": a, "b": b})
    assert r["n_trials"] == 2
    assert r["sr_variance"] == 0.0
    assert r["expected_max_sr"] == 0.0
    assert r["selection_bias_corrected"] is False
    assert any("未校正选择偏差" in n for n in r["notes"])


def test_selection_bias_lowers_dsr_below_psr():
    """C4：一族有离散度时，E[max SR] > 0，且至少一个试验的 dsr < psr。"""
    fam = {f"n{i}": _series(0.0, 250, seed=500 + i) for i in range(30)}
    r = deflated_family(fam)
    assert r["n_trials"] == 30
    assert r["sr_variance"] > 0
    assert r["expected_max_sr"] > 0
    assert r["selection_bias_corrected"] is True
    lowered = [k for k, t in r["trials"].items()
               if isinstance(t["dsr"], float) and isinstance(t["psr"], float)
               and t["dsr"] < t["psr"] - 1e-9]
    assert lowered, "没有任何试验被选择偏差压低 —— E[max SR] 没起作用"


def test_invalid_series_excluded_from_n_trials():
    """C2：算不出矩的序列不算「试过」，n_submitted 与 n_trials 必须分列。"""
    fam = {
        "ok1": _series(0.2, 100, seed=31),
        "ok2": _series(-0.1, 100, seed=32),
        "too_short": [0.1, 0.2],          # < 4 个观测 ⇒ sharpe_moments 返回 None
        "zero_sd": [0.5] * 50,            # sd = 0 ⇒ None
    }
    r = deflated_family(fam)
    assert r["n_submitted"] == 4
    assert r["n_trials"] == 2
    assert "too_short" not in r["trials"]
    assert "zero_sd" not in r["trials"]


def test_empty_family_is_reported_not_crashed():
    """空族必须返回 error，而不是抛异常或返回看起来正常的数据。"""
    r = deflated_family({})
    assert r.get("error") == "empty_family"
    assert r["n_trials"] == 0
    assert r["trials"] == {}


def test_strongly_negative_ir_gets_near_zero_dsr():
    """负 ICIR 的 dsr 必须接近 0（不能被读成「证据」）。"""
    r = deflated_family({"neg": _series(-0.45, 250, seed=41)})
    t = r["trials"]["neg"]
    assert t["sr"] < -0.3
    assert t["psr"] < 1e-6
    assert t["dsr"] < 1e-6


def test_alpha_tightens_min_trl():
    """alpha 越小，MinTRL 要求的观测数必须越多（单调性）。"""
    s = _series(0.20, 120, seed=51)
    loose = deflated_family({"x": s}, alpha=0.05)["trials"]["x"]
    tight = deflated_family({"x": s}, alpha=0.01)["trials"]["x"]
    assert tight["min_trl_required"] > loose["min_trl_required"]


def test_notes_always_declare_limitations():
    """L1~L3：局限必须随结果一起返回，调用方无法「忘记」声明。"""
    r = deflated_family({"x": _series(0.2, 100, seed=61)})
    joined = "\n".join(r["notes"])
    for kw in ("独立", "噪声", "非年化"):
        assert kw in joined, f"notes 缺少局限声明：{kw}"


def test_min_trl_against_deflated_benchmark_is_stricter():
    """C4：以 E[max SR] 为基准的 MinTRL 必须 ≥ 以 0 为基准的 MinTRL。"""
    fam = {f"n{i}": _series(0.0, 250, seed=700 + i) for i in range(20)}
    fam["best_guess"] = _series(0.35, 250, seed=799)
    r = deflated_family(fam)
    assert r["expected_max_sr"] > 0
    t = r["trials"]["best_guess"]
    assert t["min_trl_required"] >= t["min_trl_vs_zero_required"]


# ---------------------------------------------------------------------------
# A-3：接线生效（不是「函数存在」）
# ---------------------------------------------------------------------------

def _called_names(node) -> set:
    """收集某 AST 子树里所有被调用的函数名（Name 或 Attribute）。"""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def _imported_from(tree, module_suffix: str) -> set:
    out: set = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").endswith(module_suffix):
            out.update(a.name for a in n.names)
    return out


def test_a3_deflated_family_is_wired_into_production():
    """A-3：`deflated_family` 必须被**生产脚本**引用并调用。

    这条判据的来历：2026-10-18 发现 DSR/PSR/MinTRL「已实现」却只有
    `tests/` 在调用，而 pytest 全绿。**函数存在不等于能力生效。**
    """
    script = ROOT / "scripts" / "run_fundamental_factor_study.py"
    assert script.is_file(), f"找不到生产脚本 {script}"
    assert "tests" not in script.parts, "调用方落在 tests/ 下不算生效"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    assert "deflated_family" in _imported_from(tree, "multiple_testing"), \
        "生产脚本没有从 validation.multiple_testing 导入 deflated_family"
    assert "deflated_family" in _called_names(tree), \
        "生产脚本导入了但没有调用 deflated_family"


def test_a3_family_entry_calls_all_three_corrections():
    """A-3（续）：入口函数内部必须真的调用三个底层校正，链路不能断。"""
    mod = ROOT / "validation" / "multiple_testing.py"
    tree = ast.parse(mod.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "deflated_family"), None)
    assert fn is not None, "validation/multiple_testing.py 里没有 deflated_family"
    inner = _called_names(fn)
    for name in ("deflated_sharpe_ratio", "probabilistic_sharpe_ratio",
                 "minimum_track_record_length"):
        assert name in inner, f"deflated_family 没有调用 {name} —— 链路断了"


def test_sharpe_corrections_have_callers_outside_tests():
    """「能力已实现 ≠ 能力在生效」的常驻守卫。

    等价于（但不依赖外部命令）::

        grep -rn "<函数名>" --include=*.py . | grep -v "^./tests/"

    ⚠️ 不能用 `grep -v test` 排除测试——`multiple_testing.py` 文件名含
    ``testing``，会被一起滤掉（2026-10-18 踩过）。
    """
    targets = ("deflated_sharpe_ratio", "probabilistic_sharpe_ratio",
               "minimum_track_record_length", "expected_max_sharpe")
    callers: Dict[str, set] = {t: set() for t in targets}
    for py in sorted(ROOT.rglob("*.py")):
        if ".git" in py.parts or "__pycache__" in py.parts:
            continue
        if py.parent.name == "tests":
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        names = _called_names(tree)
        for t in targets:
            if t in names:
                callers[t].add(py)
    for t in targets:
        assert callers[t], (
            f"{t} 仍无 tests/ 之外的调用方 —— 夏普比率校正未在生产生效")


def test_normal_approximation_used_by_positive_control_is_sane():
    """自检：阳性对照里用的正态近似必须与模块 CDF 一致（防止判据本身错）。"""
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert normal_cdf(1.959963985) == pytest.approx(0.975, abs=1e-6)
    m = sharpe_moments(_series(0.3, 250, seed=71))
    assert m is not None
    assert m["sr"] > 0
    assert m["n"] == 250
