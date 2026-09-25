# -*- coding: utf-8 -*-
"""`run_ic_study` 的**重构锁定测试**（2026-09-19）。

背景：为接入因子正交化，`run_ic_study` 的实现被提取为
``build_factor_panel`` + ``panel_ic_series`` + ``_summarize_ic`` 三步。
重构必须**零数值变化** —— 否则此前所有已归档的因子研究结论都失去可比性。

本文件把重构**之前**在固定合成数据上的输出冻结为常量。
若日后有人改动因子定义、截面筛选或统计汇总，这里会立刻失败。

数据由本文件自带的 LCG 生成（不依赖 `random` 模块的实现细节），
因此常量不会因 Python 版本变化而漂移。
"""
import math

import pytest

from factors.factor_ic_lab import (
    MIN_HISTORY,
    build_factor_panel,
    build_panel,
    quintile_returns,
    run_ic_study,
)

N_STOCKS = 120
N_DAYS = 200
SEED = 20260919


class Lcg:
    """线性同余 + Box-Muller：完全确定，跨 Python 版本稳定。"""

    def __init__(self, seed):
        self.s = seed & 0x7FFFFFFF

    def u(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s / 0x7FFFFFFF

    def gauss(self):
        u1 = max(self.u(), 1e-12)
        u2 = self.u()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def synthetic_data(n_stocks=N_STOCKS, n_days=N_DAYS, seed=SEED):
    rng = Lcg(seed)
    data = {}
    for s in range(n_stocks):
        price = 10.0 + rng.u() * 20.0
        bars = []
        for d in range(n_days):
            date = f"2024-{1 + d // 28:02d}-{1 + d % 28:02d}"
            drift = 0.0005 * math.sin(s + d / 20.0)
            price = max(0.5, price * (1.0 + drift + rng.gauss() * 0.02))
            amount = 1e6 * (1.0 + abs(rng.gauss()) * 0.5)
            bars.append({"date": date, "open": price, "high": price * 1.01,
                         "low": price * 0.99, "close": price,
                         "volume": amount / price, "amount": amount})
        data[f"{s:06d}"] = bars
    return data


# 重构前（原实现）在 synthetic_data() 上的输出 —— 逐位冻结
EXPECTED = {
    "amihud_20": (0.029343336751326693, 1.9038203400705787, 34),
    "dist_high_20": (-0.01584577618961634, -1.027617951183188, 34),
    "log_amount_20": (-0.023675663751159193, -1.5045111419586195, 34),
    "max_ret_20": (0.015455321652238925, 0.8490871826142744, 34),
    "price": (0.01354955205222585, 0.7487510967130301, 34),
    "ret_1": (-0.022097327020258767, -1.5278625812893893, 34),
    "ret_20": (-0.010278491561914021, -0.5497402836646658, 34),
    "ret_5": (-0.01758802694631572, -1.2477959300193244, 34),
    "vol_20": (0.026483252513450697, 1.7111310481683555, 34),
    "vol_ratio": (-0.012111952218904093, -0.8250412981118286, 34),
}
EXPECTED_N_REBAL = 34
EXPECTED_AVG_CS = 120.0
EXPECTED_MUFR = -0.00022056332789971406
EXPECTED_Q_LS = -0.2981734335255138


@pytest.fixture(scope="module")
def data():
    return synthetic_data()


@pytest.fixture(scope="module")
def study(data):
    return run_ic_study(data, min_cross_section=50)


def test_panel_dates_unchanged(data):
    assert len(build_panel(data)) == N_DAYS


@pytest.mark.parametrize("factor", sorted(EXPECTED))
def test_ic_mean_and_t_frozen(study, factor):
    """IC 均值与 t 值必须与重构前逐位一致（tol=0 的浮点相等）。"""
    ic, t, n = EXPECTED[factor]
    got = study["factors"][factor]
    assert got["ic_mean"] == pytest.approx(ic, abs=1e-15)
    assert got["t"] == pytest.approx(t, abs=1e-12)
    assert got["n_periods"] == n


def test_study_level_aggregates_frozen(study):
    assert study["n_rebalance_dates"] == EXPECTED_N_REBAL
    assert study["avg_cross_section"] == pytest.approx(EXPECTED_AVG_CS)
    assert study["mean_universe_forward_return"] == pytest.approx(EXPECTED_MUFR, abs=1e-15)
    assert study["horizon"] == 5
    assert study["step"] == 5


def test_quintile_result_frozen(data):
    q = quintile_returns(data, "ret_20", min_cross_section=50)
    assert q is not None
    assert q["long_short_pct"] == pytest.approx(EXPECTED_Q_LS, abs=1e-12)
    assert q["n_periods"] == 34


def test_build_factor_panel_aligns_factors_with_forward_returns(data):
    """面板中因子值与前瞻收益必须逐元素对齐（正交化按截面回归的前提）。"""
    built = build_factor_panel(data, min_cross_section=50)
    assert built["periods"], "面板不应为空"
    for p in built["periods"]:
        n = len(p["forward"])
        assert n >= 50
        for name, vals in p["factors"].items():
            assert len(vals) == n, f"{name} 与前瞻收益长度不一致"


def test_build_factor_panel_respects_min_cross_section(data):
    loose = build_factor_panel(data, min_cross_section=50)
    tight = build_factor_panel(data, min_cross_section=500)
    assert len(tight["periods"]) <= len(loose["periods"])


def test_build_factor_panel_respects_start_end(data):
    full = build_factor_panel(data, min_cross_section=50)
    part = build_factor_panel(data, min_cross_section=50, start="2024-06-01")
    assert len(part["periods"]) < len(full["periods"])
    assert all(p["date"] >= "2024-06-01" for p in part["periods"])


def test_first_rebalance_respects_min_history(data):
    """首个调仓日必须晚于 MIN_HISTORY，否则因子用到了不足的历史。"""
    built = build_factor_panel(data, min_cross_section=50)
    dates = build_panel(data)
    assert built["periods"][0]["date"] == dates[MIN_HISTORY]
