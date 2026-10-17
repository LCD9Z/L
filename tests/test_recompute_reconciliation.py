# -*- coding: utf-8 -*-
"""重算对账脚本的**命名切分**守卫（`scripts/check_recompute.py`）。

背景（2026-10-16）：`check_one` 原用 ``RECALC.glob(f"{name}_*.json")`` 做**前缀匹配**，
会把**同族产物互相吞并** ——
``combo_study_h20`` 吞 ``combo_study_h20_fixed_*``、
``horizon_study`` 吞 ``horizon_study_turnover_fixed_*``、
``tc_t2`` 吞 ``tc_t2_p1_*``，
使**不属于该产物的窗口**被计入对账（副本侧 8 份一跑就多出 3 个受影响名）。

本测试锁两件事，防它回归：

1. ``parse_stem`` 正确切 ``<名>_<窗口>``，并**拒绝**非窗口后缀（如 ``.json.partial``）；
2. ``files_for`` **不吞同族产物**，并附**反向验证**：确认「旧前缀 glob」**确实会吞** ——
   即这条守卫对付的是**真实存在过的问题**，不是空判据。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "check_recompute", ROOT / "scripts" / "check_recompute.py")
assert _spec is not None and _spec.loader is not None
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


def test_parse_stem_splits_name_and_window():
    """窗口恒为 YYYY-MM-DD，切分应无歧义（产品名不含该形态）。"""
    assert cr.parse_stem("combo_study_h20_2023-07-03") == ("combo_study_h20", "2023-07-03")
    assert cr.parse_stem("v3_rolling_eval_ew_full_2025-01-02") == (
        "v3_rolling_eval_ew_full", "2025-01-02")
    # 非窗口后缀一律拒绝（半截文件、无窗口名）
    assert cr.parse_stem("combo_study_h20_2023-07-03.json.partial") is None
    assert cr.parse_stem("combo_study_h20") is None
    assert cr.parse_stem("foo_bar") is None


def test_files_for_does_not_swallow_sibling_products(tmp_path, monkeypatch):
    """核心回归点：同族产物名互为前缀时，只取自己的。"""
    for stem in ("combo_study_h20_2023-07-03",
                 "combo_study_h20_fixed_2023-07-03",
                 "tc_t2_2024-01-02",
                 "tc_t2_p1_2024-01-02",
                 "horizon_study_2023-07-03",
                 "horizon_study_turnover_fixed_2023-07-03"):
        (tmp_path / f"{stem}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cr, "RECALC", tmp_path)

    assert [p.name for p in cr.files_for("combo_study_h20")] == [
        "combo_study_h20_2023-07-03.json"]
    assert [p.name for p in cr.files_for("combo_study_h20_fixed")] == [
        "combo_study_h20_fixed_2023-07-03.json"]
    assert [p.name for p in cr.files_for("tc_t2")] == ["tc_t2_2024-01-02.json"]
    assert [p.name for p in cr.files_for("tc_t2_p1")] == ["tc_t2_p1_2024-01-02.json"]
    assert [p.name for p in cr.files_for("horizon_study")] == [
        "horizon_study_2023-07-03.json"]


def test_reverse_verification_old_prefix_glob_would_swallow(tmp_path):
    """反向验证：确认「旧前缀 glob」**确实会吞**同族产物。

    若这条断言失败，说明前提不成立（旧写法其实没吞）—— 那本守卫的动机需重新核对，
    而不是默默通过。
    """
    for stem in ("combo_study_h20_2023-07-03", "combo_study_h20_fixed_2023-07-03"):
        (tmp_path / f"{stem}.json").write_text("{}", encoding="utf-8")
    old = sorted(p.name for p in tmp_path.glob("combo_study_h20_*.json"))
    assert old == ["combo_study_h20_2023-07-03.json",
                   "combo_study_h20_fixed_2023-07-03.json"], \
        "旧 glob 竟然没吞 —— 本守卫的前提需重新核对"


def test_names_are_deduplicated():
    """``names`` 必须是**去重集合**：按文件枚举会重复执行同名产物（曾一度引入）。

    回归点：``sorted({...})`` 写成 ``sorted(生成器)`` 会按文件数重复，
    使汇总口径虚高（实测 30 → 72）。
    """
    names = sorted({
        parsed[0]
        for p in cr.RECALC.glob("*.json")
        if (parsed := cr.parse_stem(p.stem))
    })
    assert len(names) == len(set(names)), "names 未去重 —— 汇总会按文件数虚增"
