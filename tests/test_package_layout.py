# -*- coding: utf-8 -*-
"""目录分层的防回退守卫测试。

背景：仓库曾把 188 个 `.py` 全部平铺在根目录，其中 76 个并非库代码。
1.0 分多轮下沉：测试/脚本 → `tests/` `scripts/`；低耦合库模块家族 → 子包
（pit/tdx/corporate/ashare/factors/reporting/runtime/risk/validation/
stage2/alpha/phase62/regime/tushare_client/notify/router/console，累计根目录 188 → 59）。

这类重构最怕**静默回退**——有人为了省事把模块挪回根目录，或在别处补一个
同名的平铺副本，两套导入路径并存，最后谁都不知道该改哪个文件。
本测试把分层约定固化成断言：

1. 每个子包存在且有 `__init__.py`；
2. 已下沉的模块**不再**出现在根目录（防止平铺副本复活）；
3. 全仓库**不存在**裸的旧顶层导入（``from pit_integrity import ...``）；
4. 子包内的同族引用使用相对导入（``from .pit_event_master import ...``）；
5. 每个子包及其模块都能被真实导入（防止目录建了、import 断了）。

关于第 2/3 条的实现方式：早期版本按**文件名前缀**判定（``pit_`` ``ashare_`` 等），
但 `risk/` 这类包里的模块并无共同前缀（`a_share_risk` / `liquidity` / `risk_engine`），
前缀法会漏检。现改为按**模块名精确匹配**，由 PACKAGES 单一来源推导。
"""
import ast
import importlib
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 子包 -> 该包应包含的模块名（不含 __init__）。这是分层约定的**唯一来源**，
# 其余断言（平铺副本、裸导入、相对导入）全部由此推导，避免多处维护。
PACKAGES = {
    "pit": [
        "pit_integrity", "pit_universe_builder", "pit_event_master",
        "pit_trading_filter", "pit_research_rows", "pit_fundamentals",
    ],
    "tdx": ["tdx_csv_adapter", "tdx_inventory", "tdx_lifecycle"],
    "corporate": ["corporate_actions", "corporate_action_provider", "corporate_action_ingest"],
    "factors": [
        "factor_registry", "factor_gate", "factor_validation",
        "factor_ic_lab", "factor_lab", "factor_blind_test",
    ],
    "ashare": [
        "ashare_market", "ashare_factor_engine", "ashare_cross_section",
        "ashare_event_engine", "ashare_flow_engine", "ashare_universe",
    ],
    "reporting": ["report_generator", "report_markdown", "report_styles"],
    "runtime": ["runtime_env", "runtime_profile"],
    "risk": ["a_share_risk", "risk_engine", "risk_budget", "liquidity", "var_calculator",
             "market_risk_gate", "expert_filter"],
    "validation": [
        "validation_suite", "performance", "phase13_risk", "robustness",
        "strategy_validation", "benchmark", "stress_test", "health_monitor",
        "multiple_testing",
    ],
    "stage2": ["stage2_scoring", "stage2_ablation", "stage2_enrichment"],
    "alpha": ["alpha_experiment", "alpha_survival_lab"],
    "phase62": ["phase62_series", "phase62_tdx_index"],
    "regime": ["regime_backtest_report", "regime_validation", "adx_router"],
    "tushare_client": ["tushare_provider", "tushare_ashare_events"],
    "notify": ["feishu_notifier", "lark_notify"],
    "router": ["provider_router", "quant_skill_router"],
    "fetch": ["transport", "common", "quote", "kline", "news", "cli", "akshare_source",
              "fundamentals_source"],
    "track": ["costs", "schema", "store", "stats"],
    "console": ["display", "teams"],
}

# 已下沉的模块名全集：出现在根目录即为平铺副本复活
MOVED_MODULES = frozenset(m for mods in PACKAGES.values() for m in mods)

SKIP_DIRS = {
    ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "build", "dist", ".venv", "venv", "node_modules", "docs",
}


def _iter_py(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def test_repository_root_is_discoverable():
    """锚定 ROOT：README 与 conftest.py 应位于项目根。"""
    assert (ROOT / "conftest.py").is_file(), f"ROOT 定位错误: {ROOT}"
    assert (ROOT / "README.md").is_file(), f"ROOT 定位错误: {ROOT}"


@pytest.mark.parametrize("pkg", sorted(PACKAGES))
def test_package_has_init(pkg):
    """每个子包都必须有 __init__.py，否则会被当成命名空间包而行为漂移。"""
    init = ROOT / pkg / "__init__.py"
    assert init.is_file(), f"缺少 {pkg}/__init__.py"


@pytest.mark.parametrize("pkg", sorted(PACKAGES))
def test_package_init_is_documented(pkg):
    """包文档要说明「这个包管什么 + 共同红线」，否则分层只是把文件换个位置。"""
    init = ROOT / pkg / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"), filename=str(init))
    assert ast.get_docstring(tree), f"{pkg}/__init__.py 缺少包级 docstring"


@pytest.mark.parametrize("pkg", sorted(PACKAGES))
def test_package_contains_expected_modules(pkg):
    """防止模块被误移出包，或包内堆积无关模块。"""
    actual = sorted(p.stem for p in (ROOT / pkg).glob("*.py") if p.stem != "__init__")
    assert actual == sorted(PACKAGES[pkg]), (
        f"{pkg}/ 内容不符预期\n  实际: {actual}\n  预期: {sorted(PACKAGES[pkg])}"
    )


def test_no_flattened_copies_in_root():
    """已下沉的模块不允许在根目录再留一份平铺副本。

    两套导入路径并存是最难查的失效模式：改了包里的文件，
    运行时却可能命中根目录的旧副本，且两者都不会报错。
    """
    offenders = sorted(
        p.name for p in ROOT.glob("*.py") if p.stem in MOVED_MODULES
    )
    assert offenders == [], f"以下模块应位于子包内，不应平铺在根目录: {offenders}"


def test_no_bare_legacy_imports():
    """全仓库不应再有裸的旧顶层导入（``from pit_integrity import ...``）。

    模块一旦下沉为包，裸导入在任何环境都会 ImportError；这里提前兜住，
    避免只在「恰好没被执行的分支」里才暴露。
    """
    names = "|".join(sorted(map(re.escape, MOVED_MODULES), key=len, reverse=True))
    pattern = re.compile(rf"^\s*(?:from|import)\s+({names})\b", re.M)
    offenders = []
    for path in _iter_py(ROOT):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in pattern.finditer(text):
            offenders.append(f"{path.relative_to(ROOT)}: {m.group(0).strip()}")
    assert offenders == [], "发现裸的旧顶层导入:\n" + "\n".join(offenders)


@pytest.mark.parametrize("pkg", sorted(PACKAGES))
def test_intra_package_imports_are_relative(pkg):
    """同族引用用相对导入，使整包可以整体改名/移动而不必改内部 import。"""
    members = set(PACKAGES[pkg])
    offenders = []
    for path in sorted((ROOT / pkg).glob("*.py")):
        if path.stem == "__init__":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module in members:
                    offenders.append(f"{path.name}:{node.lineno}: from {node.module} import ...")
    assert offenders == [], f"{pkg}/ 内应改用相对导入:\n" + "\n".join(offenders)


@pytest.mark.parametrize("pkg", sorted(PACKAGES))
def test_package_is_importable(pkg):
    """子包整体可导入（只导入 __init__，不触发模块级副作用）。"""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    assert importlib.import_module(pkg) is not None


@pytest.mark.parametrize("pkg", sorted(PACKAGES))
def test_package_modules_are_importable(pkg):
    """包内每个模块都能真实导入 —— 目录建了但 import 断了是最常见的假分层。"""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    failed = []
    for mod in PACKAGES[pkg]:
        try:
            importlib.import_module(f"{pkg}.{mod}")
        except ImportError as exc:
            failed.append(f"{pkg}.{mod}: {exc}")
    # 仅第三方可选依赖缺失可容忍；项目自身模块缺失必须报错
    real = [f for f in failed if not _is_third_party(f)]
    assert real == [], "以下包内模块无法导入:\n" + "\n".join(real)


def _is_third_party(msg: str) -> bool:
    """判断 ImportError 是否来自第三方包（如 pandas / tushare）。"""
    m = re.search(r"No module named '([^']+)'", msg)
    if not m:
        return False
    top = m.group(1).split(".")[0]
    return top not in PACKAGES and top not in MOVED_MODULES


def test_agents_family_stays_flat():
    """agents_* 刻意保持平铺：根目录已有门面 agents.py，再建包会同名冲突。

    这条断言把「不做某事」的原因固化下来，避免后来者误以为是遗漏。
    """
    assert (ROOT / "agents.py").is_file(), "agents.py 是门面模块，应保持在根目录"
    assert not (ROOT / "agents").is_dir(), (
        "不应建立 agents/ 包：与根目录 agents.py 同名，导入解析会产生歧义"
    )


def test_scripts_and_tests_directories_exist():
    """第一轮分层的成果同样需要守卫。"""
    assert (ROOT / "scripts").is_dir()
    assert (ROOT / "tests").is_dir()
    gate_tools = {"run_ci.py", "credential_scan.py"}
    missing = [n for n in gate_tools if not (ROOT / n).is_file()]
    assert not missing, f"门禁工具应保留在根目录: {missing}"


def test_no_bare_import_of_package_names():
    """不得对本项目包名做裸 `import <pkg>` —— 那意味着遮蔽了同名第三方模块。

    子包是"模块的命名空间"，`__init__.py` 不重新导出任何东西，因此
    `import <pkg>` 名下拿不到任何有用属性。若代码里出现这种导入，几乎可以
    断定作者本意是**第三方同名模块**，于是发生遮蔽：

        import tushare as ts      # 本意是第三方 tushare 库
        ts.pro_api(token)         # 实际命中本项目的空包 → AttributeError

    该缺陷 pytest 抓不到（惰性导入 + 只在调用时触发），是 mypy 在远端 CI 上
    `Module has no attribute "pro_api"` 报出来的。故固化为守卫。
    """
    offenders = []
    for path in _iter_py(ROOT):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in PACKAGES:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: import {alias.name}"
                        )
    assert offenders == [], (
        "发现对本项目包名的裸 import（疑似遮蔽第三方同名模块）:\n"
        + "\n".join(offenders)
    )


#: 数据准备 / 运维类脚本的命名前缀 —— 这类脚本一律入 `scripts/`。
#: 根目录只保留四类：库代码、门面模块、程序入口、门禁工具。
SCRIPTS_ONLY_PREFIXES = ("build_", "repair_", "fetch_", "merge_", "enumerate_", "rerun_")

#: 允许留在根目录的基础设施工具（门禁 / 凭据扫描，非一次性脚本）
ROOT_TOOL_ALLOWLIST = frozenset({"run_ci.py", "credential_scan.py"})

#: 已确认归属 scripts/ 的数据准备脚本（防止被误删或回迁）
KNOWN_DATA_PREP_SCRIPTS = (
    "build_tdx_dataset.py",
    "fetch_corporate_actions.py",
    "repair_tdx_metadata.py",
)


def test_data_prep_scripts_live_in_scripts_dir():
    """数据准备类脚本不得散落在根目录。

    背景：`build_tdx_dataset.py` / `fetch_corporate_actions.py` /
    `repair_tdx_metadata.py` 曾长期留在根目录，违反「非库脚本入 scripts/」约定。
    这类脚本在 README、研究报告与**其他脚本的错误提示**中被反复引用，
    位置漂移会让命令示例失效 —— 已实际发生：`ADJUSTED_FACTOR_REPORT.md`
    写的是 `scripts/fetch_corporate_actions.py`，而文件当时却在根目录。

    守卫按**命名前缀**识别而非硬编码文件名，因此新增同类脚本同样受约束。
    """
    offenders = [
        p.name
        for p in ROOT.glob("*.py")
        if p.name.startswith(SCRIPTS_ONLY_PREFIXES) and p.name not in ROOT_TOOL_ALLOWLIST
    ]
    assert offenders == [], (
        "以下数据准备/运维类脚本应位于 scripts/，不应留在根目录: "
        f"{offenders}（若确属基础设施工具，请加入 ROOT_TOOL_ALLOWLIST 并说明理由）"
    )


def test_known_data_prep_scripts_are_under_scripts_dir():
    """三个已知数据准备脚本必须位于 scripts/，且不得在根目录留有副本。"""
    missing = [n for n in KNOWN_DATA_PREP_SCRIPTS if not (ROOT / "scripts" / n).is_file()]
    assert not missing, f"以下脚本缺失于 scripts/: {missing}"

    duplicated = [n for n in KNOWN_DATA_PREP_SCRIPTS if (ROOT / n).is_file()]
    assert not duplicated, f"以下脚本在根目录出现平铺副本: {duplicated}"
