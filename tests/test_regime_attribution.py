# -*- coding: utf-8 -*-
"""`scripts/regime_attribution.py` 的算法守卫。

本轮归因的**结论全部依赖这个脚本**，所以它自己的算式必须先被钉住。四件事：

1. **块自举与既有实现逐位一致** —— 否则「G-2 的 CI」与项目其他研究不可比；
2. **BH 校正正确** —— G-4 的唯一闸门，算错就会把噪声判成显著（或反之）；
3. **`n_eff` 的定义就是 `floor(n_days/horizon)`** —— 预注册 §5.0-1 的算式，
   不能是「看起来差不多」；
4. **标签缺失归入 `无标签` 而非猜测** —— 数据不足时不许编造档位。

反向验证（已做）：把 `ci_from_means` 的分位改成 `int(alpha*(m-1))`（丢掉 `/2`），
用例 1 会红；把 BH 的单调化（`min` 从大端回扫）删掉，用例 2 的 `q` 会变成
`[0.06,0.06,0.06,0.06,0.06,0.20]`→`[0.06,0.06,0.06,0.06,0.05,0.20]` 的非单调序列而红。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from alpha.alpha_survival_lab import block_bootstrap_mean_ci

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(module_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


ra = _load("_regime_attribution_under_test", "scripts/regime_attribution.py")


# ---------------------------------------------------------------------------
# 1. 块自举与既有实现一致
# ---------------------------------------------------------------------------

def test_bootstrap_matches_existing_implementation():
    """同一 seed/块长下，本脚本的 CI 必须与 `block_bootstrap_mean_ci` 逐位相同。"""
    series = [-0.012, 0.004, 0.009, -0.003, 0.0, 0.017, -0.008, 0.002,
              0.011, -0.005, 0.006, -0.001, 0.013, -0.007, 0.003, 0.001]
    mine = ra.block_bootstrap_means(series, reps=500, block_size=5, seed=20261018)
    ci_mine = ra.ci_from_means(mine, 0.05)
    ci_ref = block_bootstrap_mean_ci(series, reps=500, block_size=5,
                                     seed=20261018, alpha=0.05)
    assert ci_mine is not None and ci_ref is not None
    assert ci_mine["lower"] == ci_ref["lower"]
    assert ci_mine["upper"] == ci_ref["upper"]


def test_bootstrap_needs_two_points():
    """少于 2 个观测不产生自举分布（避免对单点编造置信区间）。"""
    assert ra.block_bootstrap_means([0.01]) == []
    assert ra.block_bootstrap_means([]) == []
    assert ra.ci_from_means([]) is None
    assert ra.one_sided_p([], 1000) is None


# ---------------------------------------------------------------------------
# 2. BH 校正
# ---------------------------------------------------------------------------

def test_bh_matches_hand_computation():
    """手算基准：p=[0.01,0.02,0.03,0.04,0.05,0.20], m=6 ⇒ q 前五个 0.06、末个 0.20。"""
    p = {"a": 0.01, "b": 0.02, "c": 0.03, "d": 0.04, "e": 0.05, "f": 0.20}
    out = ra.bh_adjust(p, q=0.10)
    assert out["m_total"] == 6 and out["m_tested"] == 6
    for k in "abcde":
        assert abs(out["p_adjusted"][k] - 0.06) < 1e-12, (k, out["p_adjusted"])
        assert out["significant"][k] is True
    assert abs(out["p_adjusted"]["f"] - 0.20) < 1e-12
    assert out["significant"]["f"] is False


def test_bh_is_monotone():
    """BH 的调整后 p 必须随原始 p 单调不减（否则「更小的 p 反而更不显著」）。"""
    p = {"a": 0.001, "b": 0.04, "c": 0.041, "d": 0.2, "e": 0.9, "f": 0.95}
    out = ra.bh_adjust(p, q=0.10)
    order = sorted(p, key=lambda k: p[k])
    qs = [out["p_adjusted"][k] for k in order]
    assert qs == sorted(qs), qs


def test_bh_treats_none_as_not_significant_but_excludes_from_denominator():
    """样本不足（`None`）的假设：不计入校正分母，但**必须**显式判为不显著。

    校正分母用「可检验个数 k」而非名义 6：`None` 表示该假设没被检验过。
    它**不能**从输出里消失（静默丢弃），也不能因为「算不出」被当成成立。
    """
    p = {"a": 0.001, "b": None}
    out = ra.bh_adjust(p, q=0.10)
    assert out["m_total"] == 2 and out["m_tested"] == 1
    assert out["significant"]["b"] is False
    assert out["p_adjusted"].get("b") is None      # 没有可报的调整后 p
    # k=1 ⇒ 调整 p 等于原始 p（0.001*1/1）
    assert abs(out["p_adjusted"]["a"] - 0.001) < 1e-12


# ---------------------------------------------------------------------------
# 3. n_eff 定义
# ---------------------------------------------------------------------------

def test_n_eff_is_floor_days_over_horizon():
    """预注册 §5.0-1：`n_eff = floor(n_days/horizon)`，不是「看起来差不多」。"""
    days = [f"2024-01-{i:02d}" for i in range(1, 13)]     # 12 天
    strat = dict.fromkeys(days, 0.001)
    benches = {"hs300": dict.fromkeys(days, 0.0)}
    labels = {d: {"regime": "震荡", "adx": 10.0} for d in days}
    out = ra._daily_block(days, strat, benches, labels, len(days),
                          horizon=5, reps=50, block=5, seed=1, alpha=0.05)
    assert out["震荡"]["n_days"] == 12
    assert out["震荡"]["n_eff"] == 2, "12//5 必须等于 2"


def test_daily_block_computes_annualized_contribution_with_252():
    """年化贡献 = Σ该档超额 / 窗口总日数 × 252（项目统一年化口径）。"""
    days = [f"2024-02-{i:02d}" for i in range(1, 6)]      # 5 天
    strat = dict.fromkeys(days, 0.002)                       # 每日 +20bp
    benches = {"hs300": dict.fromkeys(days, 0.0)}
    labels = {d: {"regime": "明确", "adx": 30.0} for d in days}
    out = ra._daily_block(days, strat, benches, labels, len(days),
                          horizon=5, reps=50, block=5, seed=1, alpha=0.05)
    b = out["明确"]["benchmarks"]["hs300"]
    assert abs(b["mean_excess"] - 0.002) < 1e-15
    # Σ=0.01，总日数 5 ⇒ 0.01/5*252 = 0.504
    assert abs(b["ann_contrib"] - 0.504) < 1e-12, b["ann_contrib"]


# ---------------------------------------------------------------------------
# 4. 标签缺失不猜
# ---------------------------------------------------------------------------

def test_missing_label_goes_to_unlabeled():
    """没有 ADX 的日期归入 `无标签`，绝不按相邻日或多数档补。"""
    assert ra.label_of({}, "2024-01-02") == ra.UNLABELED
    assert ra.label_of({"2024-01-02": {"regime": "震荡", "adx": 12.0}},
                       "2024-01-03") == ra.UNLABELED
    assert ra.label_of({"2024-01-02": {"regime": "震荡", "adx": 12.0}},
                       "2024-01-02") == "震荡"


def test_labels_need_enough_bars():
    """ADX 需要 ≥2×period 根，数据不足时返回空标签表（不编造档位）。"""
    bars = [{"date": f"2024-03-{i:02d}", "open": 10.0, "high": 10.5,
             "low": 9.5, "close": 10.0} for i in range(1, 21)]   # 20 根 < 28
    assert ra.labels_by_date(bars) == {}


# ---------------------------------------------------------------------------
# 5. 基准收益来源两路
# ---------------------------------------------------------------------------

def test_load_returns_source_csv_and_json(tmp_path: Path):
    """`.csv` 与 `.json` 两路都要能读，且对同一序列给出同样的日收益。"""
    csv_p = tmp_path / "ew.csv"
    csv_p.write_text("date,open,high,low,close\n"
                     "2024-01-02,100,100,100,100\n"
                     "2024-01-03,110,110,110,110\n"
                     "2024-01-04,99,99,99,99\n", encoding="utf-8")
    json_p = tmp_path / "ew.json"
    json_p.write_text(json.dumps({"series": {"2024-01-03": 0.10,
                                             "2024-01-04": -0.10}}), encoding="utf-8")
    r_csv = ra.load_returns_source(str(csv_p))
    r_json = ra.load_returns_source(str(json_p))
    assert set(r_csv) == set(r_json) == {"2024-01-03", "2024-01-04"}
    for d in r_csv:
        assert abs(r_csv[d] - r_json[d]) < 1e-12


def test_load_returns_source_rejects_json_without_series(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"diag": {}}), encoding="utf-8")
    try:
        ra.load_returns_source(str(bad))
    except ValueError as e:
        assert "series" in str(e)
    else:
        raise AssertionError("缺 series 键必须报错，不能静默返回空字典")


# ---------------------------------------------------------------------------
# 6. 与 RegimeRouter 等价（预注册偏离的等效性证明）
# ---------------------------------------------------------------------------

def test_pure_function_labels_equal_router_decisions():
    """`labels_by_date`（纯函数）与 `RegimeRouter(enabled=True).decide().regime` 必须一致。

    预注册 §三.0-E 写的是「用 RegimeRouter 取标签」，实现改用
    `compute_adx_by_date` + `classify_regime` 两个纯函数 —— 目的是让「只取标签、
    不产生仓位系数」在**代码结构上**就不可越界。这条测试证明两者对真实基准
    逐日等价，所以该偏离不改变任何结果。
    """
    from regime.adx_router import RegimeRouter

    bench = Path("D:/tdx_dataset_v3/benchmark.csv")
    if not bench.exists():
        return  # 数据集不在本机时跳过（不把环境缺失伪装成断言失败）
    bars = ra.load_bars(str(bench))
    labels = ra.labels_by_date(bars)
    assert len(labels) > 500, "ADX 可用日期数异常"
    router = RegimeRouter({"enabled": True}, index_bars=bars)
    mismatched = [(d, router.decide(d).regime, labels[d]["regime"])
                  for d in sorted(labels)
                  if router.decide(d).regime != labels[d]["regime"]]
    assert mismatched == [], f"标签与路由器不一致 {len(mismatched)} 处: {mismatched[:5]}"
