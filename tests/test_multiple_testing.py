# -*- coding: utf-8 -*-
"""多重检验校正的公式守卫。

数值全部与**独立手工推算**核对过（正态分位数对照标准表、
BH/Bonferroni 对照可手算的 5 元算例），不是对实现的复述。
"""
import pytest

from validation.multiple_testing import (
    benjamini_hochberg,
    bonferroni,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    family_wise_error_rate,
    minimum_track_record_length,
    normal_cdf,
    normal_ppf,
    probabilistic_sharpe_ratio,
    sharpe_moments,
)

# 手算算例：mean=0.01, pstdev=sqrt(2e-4), sr=0.7071, skew=0, kurt=1.7
SAMPLE = [0.02, -0.01, 0.03, 0.01, 0.00]


# ---------------------------------------------------------------------------
# 分布函数
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("p,expected", [
    (0.975, 1.9599639845400545),
    (0.95, 1.6448536269514722),
    (0.025, -1.9599639845400545),
    (0.01, -2.3263478740408408),
    (0.5, 0.0),
])
def test_normal_ppf_matches_standard_table(p, expected):
    assert normal_ppf(p) == pytest.approx(expected, abs=1e-7)


def test_normal_ppf_endpoints_are_undefined():
    """端点对应 ±∞，不可用于算术 —— 必须返回 None 而不是 inf。"""
    assert normal_ppf(0.0) is None
    assert normal_ppf(1.0) is None
    assert normal_ppf(None) is None


def test_normal_ppf_inverts_normal_cdf():
    for x in (-3.0, -1.5, -0.3, 0.0, 0.7, 2.2):
        assert normal_ppf(normal_cdf(x)) == pytest.approx(x, abs=1e-6)


def test_normal_cdf_at_zero_is_half():
    assert normal_cdf(0.0) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 矩
# ---------------------------------------------------------------------------

def test_sharpe_moments_hand_computed_case():
    m = sharpe_moments(SAMPLE)
    assert m is not None
    assert m["n"] == 5
    assert m["mean"] == pytest.approx(0.01)
    assert m["sr"] == pytest.approx(0.7071067811865476)
    assert m["skew"] == pytest.approx(0.0, abs=1e-12)
    assert m["kurt"] == pytest.approx(1.7)   # 非超额峰度，正态为 3


def test_sharpe_moments_rejects_degenerate_input():
    assert sharpe_moments([0.01, 0.01, 0.01, 0.01]) is None   # 标准差为 0
    assert sharpe_moments([0.01, 0.02, 0.03]) is None         # 观测数 < 4
    assert sharpe_moments([]) is None
    assert sharpe_moments([float("nan")] * 10) is None


def test_sharpe_moments_ignores_non_numeric_entries():
    m = sharpe_moments([0.02, None, "x", -0.01, 0.03, 0.01, 0.00])
    assert m is not None and m["n"] == 5


def test_normal_series_has_kurtosis_near_three():
    """用确定性的对称序列验证峰度口径：对称 → 偏度 0。"""
    vals = [-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0]
    m = sharpe_moments(vals)
    assert m is not None
    assert m["skew"] == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 期望最大夏普
# ---------------------------------------------------------------------------

def test_single_trial_has_no_selection_bias():
    assert expected_max_sharpe(1, 0.5) == 0.0


def test_zero_dispersion_has_no_selection_bias():
    assert expected_max_sharpe(100, 0.0) == 0.0


def test_expected_max_sharpe_grows_with_trial_count():
    """试验次数越多，"最好那个"的期望越高 —— 这是 DSR 惩罚的来源。"""
    vals = [expected_max_sharpe(n, 0.04) for n in (2, 10, 100, 1000)]
    nums = [v for v in vals if v is not None]
    assert len(nums) == len(vals)
    assert nums == sorted(nums)
    assert nums[0] < nums[-1]


def test_expected_max_sharpe_scales_with_dispersion():
    a = expected_max_sharpe(100, 0.01)
    b = expected_max_sharpe(100, 0.04)
    assert a is not None and b is not None
    assert b == pytest.approx(2 * a)   # sqrt(V) 线性


# ---------------------------------------------------------------------------
# PSR / DSR
# ---------------------------------------------------------------------------

def test_psr_matches_hand_computation():
    """z = SR·sqrt(n-1)/sqrt(1 - γ3·SR + ((γ4-1)/4)·SR²) = 1.356127"""
    out = probabilistic_sharpe_ratio(SAMPLE)
    assert out is not None
    assert out["z"] == pytest.approx(1.3561270072416207, abs=1e-9)
    assert out["psr"] == pytest.approx(0.9124706193856337, abs=1e-9)


def test_psr_none_when_sample_too_small():
    assert probabilistic_sharpe_ratio([0.01, 0.02, 0.03]) is None


def test_dsr_equals_psr_when_no_selection():
    """只试了 1 次（或无离散度）→ 没有选择偏差 → DSR 必须退化为 PSR。"""
    dsr = deflated_sharpe_ratio(SAMPLE, n_trials=1, sr_variance=0.0)
    psr = probabilistic_sharpe_ratio(SAMPLE)
    assert dsr is not None and psr is not None
    assert dsr["dsr"] == pytest.approx(psr["psr"])


def _dsr(n_trials: int) -> float:
    out = deflated_sharpe_ratio(SAMPLE, n_trials, 0.04)
    assert out is not None
    return float(out["dsr"])


def test_dsr_is_penalised_by_trial_count():
    """试的次数越多，同一个回测结果的 DSR 越低 —— 模块存在的全部理由。"""
    vals = [_dsr(n) for n in (1, 10, 100, 1000)]
    assert vals == sorted(vals, reverse=True)
    assert vals[0] > vals[-1]


def test_dsr_never_exceeds_psr():
    for n in (2, 50, 500):
        d = deflated_sharpe_ratio(SAMPLE, n, 0.04)
        assert d is not None
        assert d["dsr"] <= d["psr"] + 1e-12


def test_dsr_reports_the_threshold_it_used():
    d = deflated_sharpe_ratio(SAMPLE, n_trials=100, sr_variance=0.04, benchmark_sr=0.5)
    assert d is not None
    assert d["threshold_sr"] == pytest.approx(max(0.5, d["expected_max_sr"]))


# ---------------------------------------------------------------------------
# MinTRL
# ---------------------------------------------------------------------------

def test_mintrl_hand_computed_case():
    """var_term=1.0875, z=1.6449, excess=0.7071 → 1 + 1.0875*(1.6449/0.7071)² = 6.8846"""
    out = minimum_track_record_length(SAMPLE)
    assert out is not None
    assert out["required"] == pytest.approx(6.884556999651149, abs=1e-9)
    assert out["sufficient"] is False          # 只有 5 个观测
    assert out["required_years"] == pytest.approx(6.884556999651149 / 252)


def test_mintrl_flags_insufficient_sample_instead_of_guessing():
    """样本不足时必须说"不够"，不能给一个勉强能看的数字。"""
    long_series = [0.001] * 60 + [-0.0005] * 60   # 120 个观测
    out = minimum_track_record_length(long_series)
    assert out is not None
    assert out["available"] == 120
    assert isinstance(out["sufficient"], bool)


def test_mintrl_undefined_when_sr_not_above_benchmark():
    out = minimum_track_record_length(SAMPLE, benchmark_sr=5.0)
    assert out is not None
    assert out["required"] is None
    assert out["sufficient"] is False
    assert out["reason"] == "observed_sr_not_above_benchmark"


def test_mintrl_shrinks_as_effect_size_grows():
    """效应越大，需要的样本越少 —— 方向性守卫。"""
    weak = minimum_track_record_length([0.0002, -0.0001] * 60)
    strong = minimum_track_record_length([0.02, -0.01] * 60)
    assert weak is not None and strong is not None
    assert strong["required"] < weak["required"]


# ---------------------------------------------------------------------------
# BH-FDR / Bonferroni
# ---------------------------------------------------------------------------

def test_bh_hand_computed_case():
    """阈值 i/m·α = .01/.02/.03/.04/.05 → k=4；调整后 p = [.005,.05,.05,.05,.5]"""
    out = benjamini_hochberg([0.001, 0.02, 0.03, 0.04, 0.5], alpha=0.05)
    assert out["m"] == 5
    assert out["k"] == 4
    assert out["threshold"] == pytest.approx(0.04)
    adj = [r["p_adjusted"] for r in out["results"]]
    assert adj == pytest.approx([0.005, 0.05, 0.05, 0.05, 0.5])
    assert [r["rejected"] for r in out["results"]] == [True, True, True, True, False]


def test_bh_preserves_input_order():
    out = benjamini_hochberg([0.5, 0.001, 0.02, 0.03, 0.04], alpha=0.05)
    assert [r["p"] for r in out["results"]] == [0.5, 0.001, 0.02, 0.03, 0.04]
    assert out["results"][0]["rejected"] is False
    assert out["results"][1]["rejected"] is True


def test_bh_treats_none_as_untested():
    out = benjamini_hochberg([0.01, None, 0.5], alpha=0.05)
    assert out["m"] == 2
    assert out["results"][1] is None
    assert out["k"] == 1


def test_bh_all_none():
    out = benjamini_hochberg([None, None], alpha=0.05)
    assert out["m"] == 0 and out["k"] == 0 and out["threshold"] is None
    assert out["results"] == [None, None]


def test_bh_adjusted_pvalues_are_monotone_in_rank():
    out = benjamini_hochberg([0.04, 0.001, 0.03, 0.02, 0.5], alpha=0.05)
    ranked = sorted((r for r in out["results"] if r), key=lambda r: r["p"])
    adj = [r["p_adjusted"] for r in ranked]
    assert adj == sorted(adj)
    assert all(a <= 1.0 for a in adj)


def test_bonferroni_hand_computed_case():
    out = bonferroni([0.001, 0.02, 0.03, 0.04, 0.5], alpha=0.05)
    assert out["threshold"] == pytest.approx(0.01)
    assert out["k"] == 1
    assert [r["p_adjusted"] for r in out["results"]] == pytest.approx([0.005, 0.1, 0.15, 0.2, 1.0])


def test_bonferroni_is_stricter_than_bh():
    ps = [0.001, 0.012, 0.02, 0.03, 0.04]
    assert bonferroni(ps)["k"] <= benjamini_hochberg(ps)["k"]


def test_rejections_are_prefix_of_sorted_pvalues():
    """BH/Bonferroni 的拒绝集合必须是最小 p 值的前缀（不是任意子集）。"""
    ps = [0.004, 0.031, 0.009, 0.2, 0.05, 0.0001]
    for out in (benjamini_hochberg(ps), bonferroni(ps)):
        ranked = sorted((r for r in out["results"] if r), key=lambda r: r["p"])
        flags = [r["rejected"] for r in ranked]
        assert flags == sorted(flags, reverse=True)


# ---------------------------------------------------------------------------
# 族错误率（用于向读者解释"不校正会怎样"）
# ---------------------------------------------------------------------------

def test_family_wise_error_rate_known_values():
    assert family_wise_error_rate(0) == pytest.approx(0.0)
    assert family_wise_error_rate(1) == pytest.approx(0.05)
    assert family_wise_error_rate(30) == pytest.approx(1 - 0.95 ** 30)
    assert family_wise_error_rate(30) == pytest.approx(0.7853612360570628)


def test_family_wise_error_rate_is_monotone():
    vals = [family_wise_error_rate(m) for m in (1, 5, 10, 30, 100)]
    nums = [v for v in vals if v is not None]
    assert len(nums) == len(vals)
    assert nums == sorted(nums)
    assert nums[-1] > 0.99
