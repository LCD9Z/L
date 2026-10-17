# -*- coding: utf-8 -*-
"""`check_recompute.py` 口径拆分守卫（2026-10-17 裁定 C / F）。

锁四件事：
1. 旧侧 `ew_*` 族缺键 + 新侧有外部基准字段 ⇒ 判 **CALIBER**、退出码 0；
2. 旧侧 `ew_*` 缺键但新侧**无** `benchmark_return_pct`/`annualized_excess`
   ⇒ 不构成替换证据，仍判 **V1 失败**（防滥用 CALIBER 销项）；
3. 普通收益键（`total_return_pct`）缺失 ⇒ 仍判 **V1 失败**；
4. `benchmark_return_pct` 上升 ⇒ **不计 V3**，计入「基准替换」。

反向验证（已做）：把 `BENCHMARK_KEYS` 清空并让 `CALIBER_REMOVED_PREFIXES` 为空，
用例 1 会退化为 V1 失败、用例 4 会退化为 V3 异常 ⇒ 本文件失败。
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(module_name: str, rel_path: str):
    """按**文件路径**加载被测模块。

    不用 ``from scripts import ...``：那会让 mypy 把同名文件同时视作
    ``check_recompute`` 与 ``scripts.check_recompute``（"found twice"）而中断检查。
    """
    spec = importlib.util.spec_from_file_location(module_name, ROOT / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


cr = _load("_check_recompute_under_test", "scripts/check_recompute.py")

WIN = "2023-01-03"


def _mk(tmp_path: Path, name: str, old_rec: dict, new_rec: dict):
    """在 tmp_path 下造最小 `reports/<name>.json` + `reports/_recalc/<name>_<win>.json`。"""
    reports = tmp_path / "reports"
    recalc = reports / "_recalc"
    recalc.mkdir(parents=True)
    (reports / f"{name}.json").write_text(
        json.dumps({"windows": [old_rec]}, ensure_ascii=False), encoding="utf-8")
    (recalc / f"{name}_{WIN}.json").write_text(
        json.dumps({"windows": [new_rec]}, ensure_ascii=False), encoding="utf-8")
    return reports, recalc


def test_ew_family_replaced_by_certified_benchmark_is_caliber(tmp_path, monkeypatch):
    """用例 1：`ew_*` → `benchmark_*` 替换 ⇒ CALIBER，退出码 0。"""
    old = {"oos_start": WIN, "total_return_pct": -50.0,
           "ew_benchmark_return_pct": 35.34, "ew_aligned": 894}
    new = {"oos_start": WIN, "total_return_pct": -50.0, "benchmark_return_pct": 40.15}
    _, recalc = _mk(tmp_path, "rolling_x", old, new)
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    monkeypatch.setattr(cr, "RECALC", recalc)

    v1, caliber, _, v3, bench, _ = cr.check_one(
        "rolling_x", False, root=tmp_path, recalc=recalc)
    assert v1 == 0, "ew_* 属口径替换族，不应计 V1 失败"
    assert caliber == 1, "应记为 1 处 CALIBER"
    assert v3 == 0 and bench == 0
    assert cr.main(["--only", "rolling_x"]) == 0


def test_ew_missing_without_benchmark_field_still_fails_v1(tmp_path):
    """用例 2：`ew_*` 缺键但新侧无任何外部基准字段 ⇒ 仍判 V1 失败。"""
    old = {"oos_start": WIN, "total_return_pct": -50.0, "ew_benchmark_return_pct": 35.34}
    new = {"oos_start": WIN, "total_return_pct": -50.0}
    _, recalc = _mk(tmp_path, "rolling_y", old, new)

    v1, caliber, _, _, _, _ = cr.check_one(
        "rolling_y", False, root=tmp_path, recalc=recalc)
    assert v1 == 1, "无基准替换证据时，ew_* 缺键必须计 V1"
    assert caliber == 0


def test_plain_return_key_missing_still_fails_v1(tmp_path):
    """用例 3：普通收益键缺失（非口径替换族）⇒ 仍判 V1 失败。"""
    old = {"oos_start": WIN, "total_return_pct": -50.0, "max_drawdown_pct": 10.0}
    new = {"oos_start": WIN, "max_drawdown_pct": 10.0, "benchmark_return_pct": 40.15}
    _, recalc = _mk(tmp_path, "plain_z", old, new)

    v1, caliber, _, _, _, _ = cr.check_one(
        "plain_z", False, root=tmp_path, recalc=recalc)
    assert v1 == 1
    assert caliber == 0


def test_benchmark_rise_is_not_v3(tmp_path, monkeypatch):
    """用例 4：`benchmark_return_pct` 上升 ⇒ 不计 V3，计入基准替换。"""
    old = {"oos_start": WIN, "benchmark_return_pct": 16.99, "annualized_excess": -0.30}
    new = {"oos_start": WIN, "benchmark_return_pct": 40.15, "annualized_excess": -0.30}
    _, recalc = _mk(tmp_path, "bench_w", old, new)
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    monkeypatch.setattr(cr, "RECALC", recalc)

    v1, _, _, v3, bench, _ = cr.check_one(
        "bench_w", False, root=tmp_path, recalc=recalc)
    assert v3 == 0, "基准上升不是「收益上升」，不得计 V3"
    assert bench == 1
    assert v1 == 0
    assert cr.main(["--only", "bench_w"]) == 0


# ---------------------------------------------------------------------------
# 反向验证（固化）：关掉规则后必须退化为旧行为 —— 证明上面的「通过」不是因为规则失效
# ---------------------------------------------------------------------------

def test_reverse_caliber_rule_off_degrades_to_v1(tmp_path, monkeypatch):
    """关掉 CALIBER 族 ⇒ 用例 1 退化为 V1 失败（证明 CALIBER 归类确有作用）。"""
    monkeypatch.setattr(cr, "CALIBER_REMOVED_PREFIXES", ())
    old = {"oos_start": WIN, "total_return_pct": -50.0,
           "ew_benchmark_return_pct": 35.34, "ew_aligned": 894}
    new = {"oos_start": WIN, "total_return_pct": -50.0, "benchmark_return_pct": 40.15}
    _, recalc = _mk(tmp_path, "rv_cal", old, new)

    v1, caliber, _, _, _, _ = cr.check_one(
        "rv_cal", False, root=tmp_path, recalc=recalc)
    assert v1 == 1, "反向验证失败：关掉 CALIBER 族后仍不报 V1 ⇒ 归类逻辑未生效"
    assert caliber == 0


def test_reverse_benchmark_in_return_keys_degrades_to_v3(tmp_path, monkeypatch):
    """恢复旧逻辑（基准键计入 RETURN_KEYS）⇒ 用例 4 变 V3 误报（证明拆分确有作用）。"""
    monkeypatch.setattr(cr, "BENCHMARK_KEYS", ())
    monkeypatch.setattr(cr, "RETURN_KEYS",
                        cr.RETURN_KEYS + ("benchmark_return_pct",))
    old = {"oos_start": WIN, "benchmark_return_pct": 16.99, "annualized_excess": -0.30}
    new = {"oos_start": WIN, "benchmark_return_pct": 40.15, "annualized_excess": -0.30}
    _, recalc = _mk(tmp_path, "rv_bench", old, new)

    _, _, _, v3, bench, _ = cr.check_one(
        "rv_bench", False, root=tmp_path, recalc=recalc)
    assert v3 == 1, "反向验证失败：旧逻辑下基准上升本应误报为 V3"
    assert bench == 0


# ---------------------------------------------------------------------------
# ATTRIBUTED 白名单（裁定 D）：已归因 D2 的上升不静默、单列；白名单外仍计 V3
# ---------------------------------------------------------------------------

def test_attributed_whitelisted_product_rise_not_v3(tmp_path):
    """白名单产物（已归因 D2）收益上升 ⇒ 计 ATTRIBUTED，不计 V3。"""
    assert "v2_p1" in cr.ATTRIBUTED_TO_BASELINE
    old = {"oos_start": WIN, "total_return_pct": -13.10}
    new = {"oos_start": WIN, "total_return_pct": -9.06}
    _, recalc = _mk(tmp_path, "v2_p1", old, new)

    _, _, _, v3, _, attr = cr.check_one(
        "v2_p1", False, root=tmp_path, recalc=recalc)
    assert attr == 1, "白名单产物上升应单列 ATTRIBUTED"
    assert v3 == 0, "已归因上升不得计 V3"


def test_attributed_non_whitelisted_product_still_v3(tmp_path):
    """白名单外产物收益上升 ⇒ 仍计 V3（防「全部自动归因」）。"""
    assert "brand_new_prod" not in cr.ATTRIBUTED_TO_BASELINE
    old = {"oos_start": WIN, "total_return_pct": -30.0}
    new = {"oos_start": WIN, "total_return_pct": -10.0}
    _, recalc = _mk(tmp_path, "brand_new_prod", old, new)

    _, _, _, v3, _, attr = cr.check_one(
        "brand_new_prod", False, root=tmp_path, recalc=recalc)
    assert v3 == 1, "未登记归因的产物上升必须计 V3"
    assert attr == 0
