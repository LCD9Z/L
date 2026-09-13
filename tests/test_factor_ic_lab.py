# -*- coding: utf-8 -*-
"""横截面因子 IC 引擎测试。

重点：统计正确性 + **无未来函数**（这是因子研究最容易出错的地方）。
"""
import math

import pytest

from factors.factor_ic_lab import (
    FACTOR_LABELS,
    PRIOR_SIGN,
    _rank,
    _winsorize,
    build_panel,
    compute_factors,
    forward_return,
    quintile_returns,
    run_ic_study,
    spearman,
)


def _bars(closes, amounts=None, volumes=None, highs=None):
    """由收盘价序列构造 bar 列表。"""
    n = len(closes)
    amounts = amounts or [1e8] * n
    volumes = volumes or [1e5] * n
    highs = highs or closes
    return [
        {"date": f"2026-01-{k+1:02d}" if k < 31 else f"2026-02-{k-30:02d}",
         "open": closes[k], "high": highs[k], "low": closes[k],
         "close": closes[k], "volume": volumes[k], "amount": amounts[k]}
        for k in range(n)
    ]


# ---------------------------------------------------------------------------
# 秩与秩相关
# ---------------------------------------------------------------------------

def test_rank_handles_ties_with_average():
    assert _rank([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_perfect_positive():
    assert spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1.0)


def test_spearman_perfect_negative():
    assert spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_is_rank_based_not_value_based():
    """秩相关只看排序 —— 这是它能抗除权跳空离群值的原因。"""
    a = spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    b = spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 99999])
    assert a == pytest.approx(b), "秩相关不应受离群值幅度影响"


def test_spearman_returns_none_on_degenerate_input():
    assert spearman([1, 2, 3], [1, 2, 3]) is None        # 样本过少
    assert spearman([1, 1, 1, 1, 1], [1, 2, 3, 4, 5]) is None   # 方差为 0


# ---------------------------------------------------------------------------
# 无未来函数（最关键）
# ---------------------------------------------------------------------------

def test_compute_factors_ignores_future_bars():
    """在第 i 根计算的因子，不得受第 i 根之后数据的影响。"""
    closes = [10.0 + k * 0.1 for k in range(60)]
    bars = _bars(closes)
    i = 40
    base = compute_factors(bars, i)

    # 篡改 i 之后的所有价格
    tampered = _bars(closes)
    for k in range(i + 1, len(tampered)):
        tampered[k]["close"] = 9999.0
        tampered[k]["high"] = 9999.0
        tampered[k]["amount"] = 1e12
        tampered[k]["volume"] = 1e9

    after = compute_factors(tampered, i)
    assert base is not None and after is not None
    for name in base:
        assert base[name] == pytest.approx(after[name]), f"因子 {name} 使用了未来数据"


def test_compute_factors_needs_min_history():
    assert compute_factors(_bars([10.0] * 10), 5) is None


def test_forward_return_uses_future_only():
    bars = _bars([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0])
    # i=0, horizon=5 → 取 bars[5] = 15.0
    assert forward_return(bars, 0, 5) == pytest.approx(15.0 / 10.0 - 1)
    assert forward_return(bars, 1, 5) == pytest.approx(16.0 / 11.0 - 1)
    assert forward_return(bars, 3, 5) is None      # 数据不足


# ---------------------------------------------------------------------------
# 因子数值
# ---------------------------------------------------------------------------

def test_factor_values_are_correct():
    closes = [10.0 * (1.01 ** k) for k in range(40)]     # 每日 +1%
    bars = _bars(closes)
    f = compute_factors(bars, 39)
    assert f is not None
    assert f["ret_1"] == pytest.approx(0.01, abs=1e-6)
    assert f["ret_5"] == pytest.approx(1.01 ** 5 - 1, abs=1e-6)
    assert f["ret_20"] == pytest.approx(1.01 ** 20 - 1, abs=1e-6)
    assert f["price"] == pytest.approx(closes[39])


def test_vol_ratio_detects_volume_expansion():
    n = 40
    vols = [1e5] * (n - 5) + [5e5] * 5          # 最近 5 日放量 5 倍
    f = compute_factors(_bars([10.0] * n, volumes=vols), n - 1)
    assert f is not None
    assert f["vol_ratio"] > 1.5


def test_dist_high_is_non_positive():
    """距高点距离必须 <= 0（收盘不可能高于区间最高价）。"""
    closes = [10.0, 12.0, 11.0, 10.5, 9.0] * 8
    highs = [c + 0.5 for c in closes]
    f = compute_factors(_bars(closes, highs=highs), len(closes) - 1)
    assert f is not None
    assert f["dist_high_20"] <= 0


def test_factors_all_present_and_finite():
    closes = [10.0 + math.sin(k / 3) for k in range(50)]
    f = compute_factors(_bars(closes), 49)
    assert f is not None
    assert set(f) == set(FACTOR_LABELS)
    assert all(math.isfinite(v) for v in f.values())


# ---------------------------------------------------------------------------
# IC 检验
# ---------------------------------------------------------------------------

def test_ic_study_detects_known_reversal():
    """构造一个明确的横截面反转结构：本期涨得多的，下期跌得多。

    若引擎正确，ret_5 的 IC 应显著为负。
    """
    data = {}
    n_days, n_codes = 200, 60
    for c in range(n_codes):
        closes = []
        for t in range(n_days):
            # 交替：偶数日涨、奇数日跌，形成强反转
            base = 10.0 + c * 0.1
            closes.append(base * (1 + (0.02 if t % 2 == 0 else -0.02) * (1 + c / 100)))
        data[f"{c:06d}"] = _bars(closes)

    res = run_ic_study(data, horizon=5, step=5, min_cross_section=30)
    assert res["n_rebalance_dates"] > 10
    assert res["factors"]["ret_5"]["ic_mean"] < 0, "未能检出反转结构"


def test_ic_study_returns_all_factors():
    data = {f"{c:06d}": _bars([10.0 + c * 0.01 + k * 0.05 for k in range(120)])
            for c in range(40)}
    res = run_ic_study(data, horizon=5, step=5, min_cross_section=20)
    for k in FACTOR_LABELS:
        assert k in res["factors"]


def test_ic_study_requires_min_cross_section():
    """截面过小时应跳过该期，而不是产出噪声。"""
    data = {f"{c:06d}": _bars([10.0 + k * 0.05 for k in range(120)]) for c in range(5)}
    res = run_ic_study(data, min_cross_section=50)
    assert res["n_rebalance_dates"] == 0


# ---------------------------------------------------------------------------
# 分位组
# ---------------------------------------------------------------------------

def test_quintile_returns_shapes():
    data = {f"{c:06d}": _bars([10.0 * (1 + 0.001 * c) ** k for k in range(150)])
            for c in range(100)}
    q = quintile_returns(data, "ret_20", min_cross_section=50)
    assert q is not None
    assert len(q["group_mean_returns"]) == 5
    assert q["n_periods"] > 0


def test_winsorize_clips_extremes():
    vals = [1.0] * 50 + [1e9]
    out = _winsorize(vals)
    assert max(out) < 1e9


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def test_build_panel_is_sorted_union():
    data = {
        "a": [{"date": "2026-01-02"}, {"date": "2026-01-05"}],
        "b": [{"date": "2026-01-01"}, {"date": "2026-01-05"}],
    }
    assert build_panel(data) == ["2026-01-01", "2026-01-02", "2026-01-05"]


def test_prior_signs_match_hypotheses():
    """先验方向必须与报告中的假设一致（防止后续被悄悄改动）。"""
    assert PRIOR_SIGN["ret_5"] == -1, "H1 短期反转预期 IC<0"
    assert PRIOR_SIGN["ret_20"] == -1, "H2 中期反转预期 IC<0"
    assert PRIOR_SIGN["vol_ratio"] == -1, "H3 换手异象预期 IC<0"
    assert PRIOR_SIGN["vol_20"] == -1, "H4 低波动异象预期 IC<0"
    assert PRIOR_SIGN["max_ret_20"] == -1, "H5 MAX 效应预期 IC<0"
    assert PRIOR_SIGN["amihud_20"] == +1, "H6 非流动性溢价预期 IC>0"
    assert PRIOR_SIGN["log_amount_20"] == -1, "H7 规模效应预期 IC<0"
