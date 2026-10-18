# -*- coding: utf-8 -*-
"""基准元数据路径解析守卫（缺陷 #20）。

数据集里两种命名习惯**并存**：

- `benchmark.csv`     → `benchmark.metadata.json`（去扩展名）
- `benchmark_ew.csv`  → `benchmark_ew.csv.metadata.json`（保留 .csv）

`run_tdx_rolling_eval.py` 曾把默认值硬编码成 `bench + ".metadata.json"`，对沪深300
得到不存在的 `benchmark.csv.metadata.json` ⇒ 审计报 `metadata_missing` ⇒ preflight
`LIMITED_OR_FAIL`，**默认参数下直接跑不起来**。危险之处在于：

- 报错是一行 `阻断项 1 个: ['benchmark']`，看不出是**路径拼错**；
- 若加 `--skip-audit` 则会**静默绕过**，问题完全不可见。

本文件锁住「两种命名都要能找到」，否则缺陷会被下一次重构再次引入。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(module_name: str, rel_path: str):
    """按文件路径加载被测模块（与 test_check_recompute_caliber.py 同法，避免 mypy 重名）。"""
    spec = importlib.util.spec_from_file_location(module_name, ROOT / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_m = _load("_run_tdx_rolling_eval_under_test", "scripts/run_tdx_rolling_eval.py")
_resolve = _m._resolve_bench_meta


def _touch(p: Path) -> Path:
    p.write_text("{}", encoding="utf-8")
    return p


def test_stem_naming_hs300(tmp_path: Path):
    """沪深300：只有 `benchmark.metadata.json` ⇒ 必须找到它。"""
    bench = tmp_path / "benchmark.csv"
    _touch(bench)
    _touch(tmp_path / "benchmark.metadata.json")
    got = _resolve(str(bench))
    assert Path(got) == tmp_path / "benchmark.metadata.json", got


def test_suffix_naming_ew(tmp_path: Path):
    """等权：只有 `benchmark_ew.csv.metadata.json` ⇒ 也必须找到它。"""
    bench = tmp_path / "benchmark_ew.csv"
    _touch(bench)
    _touch(tmp_path / "benchmark_ew.csv.metadata.json")
    got = _resolve(str(bench))
    assert Path(got) == tmp_path / "benchmark_ew.csv.metadata.json", got


def test_stem_wins_when_both_exist(tmp_path: Path):
    """两种都存在时优先去扩展名形式（与个股 `<code>.metadata.json` 约定一致）。"""
    bench = tmp_path / "b.csv"
    _touch(bench)
    _touch(tmp_path / "b.metadata.json")
    _touch(tmp_path / "b.csv.metadata.json")
    assert Path(_resolve(str(bench))) == tmp_path / "b.metadata.json"


def test_fallback_when_neither_exists(tmp_path: Path):
    """都不存在 ⇒ 返回去扩展名形式（而不是不存在的 `.csv.metadata.json`），
    让审计如实报 `metadata_missing`，而不是报一个无从追查的路径。"""
    bench = tmp_path / "nope.csv"
    _touch(bench)
    got = _resolve(str(bench))
    assert got.endswith("nope.metadata.json"), got


def test_explicit_wins(tmp_path: Path):
    """`--benchmark-meta` 显式给出时不得被探测逻辑覆盖。"""
    bench = tmp_path / "benchmark.csv"
    _touch(bench)
    _touch(tmp_path / "benchmark.metadata.json")
    explicit = str(tmp_path / "custom_meta.json")
    assert _resolve(str(bench), explicit) == explicit


def test_real_dataset_paths_resolve():
    """真实数据集上的回归：v3 的沪深300 基准元数据必须解析到一个**存在**的文件。"""
    ds = Path("D:/tdx_dataset_v3")
    if not ds.exists():
        return  # 环境无关：数据集不在本机时跳过（不把环境缺失伪装成断言失败）
    bench = ds / "benchmark.csv"
    if not bench.exists():
        return
    got = Path(_resolve(str(bench)))
    assert got.exists(), f"解析出的元数据不存在: {got}"
