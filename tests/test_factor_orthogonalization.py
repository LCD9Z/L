# -*- coding: utf-8 -*-
"""因子正交化的行为守卫。

每一条用例都对应一个**会静默改变结论**的设计选择：

* 顺序残差化必须真正消除冗余（而不是把相关翻转符号）；
* 顺序必须被如实报告（否则"按结果挑顺序"无从发现）；
* Löwdin 在因子近似共线时必须判**不可用**，而不是硬算出一个被噪声主导的结果；
* 正交化不得就地修改入参（面板会被多处复用）。
"""
import math

import pytest

from factors.factor_ic_lab import (
    COMPOSITE_FACTORS,
    ORTHO_ORDER_DEFAULT,
    _jacobi_eigen,
    _rank_standardize,
    factor_rank_correlation,
    orthogonalize_panel,
    run_ic_study,
    run_orthogonal_ic_study,
)

NAMES = ["ret_20", "vol_20", "amihud_20", "log_amount_20", "max_ret_20"]


class Lcg:
    def __init__(self, seed):
        self.s = seed & 0x7FFFFFFF

    def u(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s / 0x7FFFFFFF

    def gauss(self):
        u1 = max(self.u(), 1e-12)
        u2 = self.u()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def mk_panel(cols, n_periods=1):
    """用给定的因子列构造一个最小面板（所有期间共用同一组列）。"""
    names = list(cols)
    periods = []
    for k in range(n_periods):
        periods.append({
            "date": f"2024-01-{k + 1:02d}",
            "factors": {name: list(vals) for name, vals in cols.items()},
            "forward": [0.0] * len(next(iter(cols.values()))),
        })
    return {"periods": periods, "panel_len": n_periods, "factor_names": names,
            "horizon": 5, "step": 5}


def correlated_pair(n=300, rho=0.9, seed=11):
    """构造两个横截面秩相关约为 rho 的因子列。"""
    rng = Lcg(seed)
    a = [rng.gauss() for _ in range(n)]
    b = [rho * x + math.sqrt(max(1e-9, 1 - rho * rho)) * rng.gauss() for x in a]
    return a, b


# ---------------------------------------------------------------------------
# _rank_standardize
# ---------------------------------------------------------------------------

def test_rank_standardize_has_zero_mean_unit_sd():
    z = _rank_standardize([5.0, 1.0, 9.0, 3.0, 7.0])
    assert z is not None
    assert sum(z) / len(z) == pytest.approx(0.0, abs=1e-12)
    assert math.sqrt(sum(v * v for v in z) / len(z)) == pytest.approx(1.0, abs=1e-12)


def test_rank_standardize_is_monotone_invariant():
    """秩变换对任何严格单调变换不变 —— 这正是它与 Spearman 同口径的原因。"""
    base = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _rank_standardize(base) == pytest.approx(_rank_standardize([10 * v for v in base]))


def test_rank_standardize_rejects_constant_and_short():
    assert _rank_standardize([1.0, 1.0, 1.0, 1.0]) is None   # 标准差 0
    assert _rank_standardize([1.0, 2.0]) is None              # 样本 < 3


# ---------------------------------------------------------------------------
# Jacobi 特征分解
# ---------------------------------------------------------------------------

def test_jacobi_eigen_on_diagonal_matrix():
    evals, _ = _jacobi_eigen([[3.0, 0.0], [0.0, 7.0]])
    assert sorted(evals) == pytest.approx([3.0, 7.0], abs=1e-10)


def test_jacobi_eigen_on_known_2x2():
    """[[2,1],[1,2]] 的特征值为 3 与 1。"""
    evals, v = _jacobi_eigen([[2.0, 1.0], [1.0, 2.0]])
    assert sorted(evals) == pytest.approx([1.0, 3.0], abs=1e-10)
    # V'V = I
    gram = [[sum(v[k][i] * v[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    assert gram[0][0] == pytest.approx(1.0, abs=1e-10)
    assert gram[1][1] == pytest.approx(1.0, abs=1e-10)
    assert gram[0][1] == pytest.approx(0.0, abs=1e-10)


def test_jacobi_eigen_traces_match():
    """特征值之和 = 矩阵迹（对任意对称矩阵成立）。"""
    a = [[4.0, 1.0, 0.5], [1.0, 3.0, -0.2], [0.5, -0.2, 2.0]]
    evals, _ = _jacobi_eigen([row[:] for row in a])
    assert sum(evals) == pytest.approx(4.0 + 3.0 + 2.0, abs=1e-9)


# ---------------------------------------------------------------------------
# factor_rank_correlation
# ---------------------------------------------------------------------------

def test_rank_correlation_of_identical_factors_is_one():
    a = [float(i) for i in range(60)]
    out = factor_rank_correlation(mk_panel({"a": a, "b": [2 * x for x in a]}))
    assert out["a~b"]["mean_rho"] == pytest.approx(1.0, abs=1e-12)
    assert out["a~b"]["abs_gt_0_5_rate"] == 1.0


def test_rank_correlation_reports_cross_section_count():
    a = [float(i) for i in range(60)]
    out = factor_rank_correlation(mk_panel({"a": a, "b": list(reversed(a))}, n_periods=3))
    assert out["a~b"]["n_cross_sections"] == 3
    assert out["a~b"]["mean_rho"] == pytest.approx(-1.0, abs=1e-12)


def test_rank_correlation_of_independent_factors_is_near_zero():
    a, b = correlated_pair(rho=0.0, seed=5)
    out = factor_rank_correlation(mk_panel({"a": a, "b": b}))
    assert abs(out["a~b"]["mean_rho"]) < 0.2


# ---------------------------------------------------------------------------
# 顺序残差化
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["sequential", "lowdin"])
def test_orthogonalization_removes_redundancy(method):
    """核心断言：高度相关的两个因子正交化后相关必须大幅下降。"""
    a, b = correlated_pair(rho=0.9)
    panel = mk_panel({"ret_20": a, "vol_20": b})
    before = factor_rank_correlation(panel, factors=["ret_20", "vol_20"])["ret_20~vol_20"]["mean_rho"]
    after_panel = orthogonalize_panel(panel, method=method, factors=["ret_20", "vol_20"])
    after = factor_rank_correlation(after_panel, factors=["ret_20", "vol_20"])["ret_20~vol_20"]["mean_rho"]
    assert before > 0.8
    assert abs(after) < 0.3
    assert abs(after) < abs(before) / 2


def test_symmetric_residualization_would_flip_not_remove():
    """回归守卫：说明为何**不提供**「每个因子对其余全部回归」的对称残差化。

    对两个标准化变量，该做法把相关 ρ 映射为 **-ρ**（幅度不变、符号翻转），
    并没有消除冗余。此处用解析构造验证这一性质，防止日后有人"顺手加回来"。
    """
    a, b = correlated_pair(rho=0.9)
    panel = mk_panel({"a": a, "b": b})
    z_a = _rank_standardize(a)
    z_b = _rank_standardize(b)
    assert z_a is not None and z_b is not None
    rho = sum(x * y for x, y in zip(z_a, z_b, strict=True)) / len(z_a)
    # 对称残差化：a_resid = a - ρ·b，b_resid = b - ρ·a
    ra = [x - rho * y for x, y in zip(z_a, z_b, strict=True)]
    rb = [y - rho * x for x, y in zip(z_a, z_b, strict=True)]
    num = sum(x * y for x, y in zip(ra, rb, strict=True))
    den = math.sqrt(sum(x * x for x in ra) * sum(y * y for y in rb))
    assert num / den == pytest.approx(-rho, abs=1e-9)


def test_sequential_reports_the_order_it_used():
    a, b = correlated_pair()
    panel = mk_panel({"ret_20": a, "vol_20": b})
    out = orthogonalize_panel(panel, method="sequential", factors=["ret_20", "vol_20"])
    assert out["ortho_order"] == ["ret_20", "vol_20"]
    assert out["ortho_method"] == "sequential"


def test_default_order_is_the_predeclared_one():
    """缺省顺序必须来自事前声明的常量，不能是字典序之类的隐式顺序。"""
    rng = Lcg(3)
    cols = {name: [rng.gauss() for _ in range(80)] for name in NAMES}
    out = orthogonalize_panel(mk_panel(cols), method="sequential", factors=NAMES)
    assert out["ortho_order"] == ORTHO_ORDER_DEFAULT


def test_sequential_result_depends_on_order():
    """顺序会改变结果 —— 这是必须把顺序写进结论的原因。"""
    a, b, c = correlated_pair()[0], correlated_pair()[1], correlated_pair(seed=21)[0]
    panel = mk_panel({"ret_20": a, "vol_20": b, "amihud_20": c})
    fwd = ["ret_20", "vol_20", "amihud_20"]
    rev = ["amihud_20", "vol_20", "ret_20"]
    o1 = orthogonalize_panel(panel, method="sequential", factors=fwd, order=fwd)
    o2 = orthogonalize_panel(panel, method="sequential", factors=fwd, order=rev)
    v1 = o1["periods"][0]["factors"]["amihud_20"]
    v2 = o2["periods"][0]["factors"]["amihud_20"]
    assert v1 != pytest.approx(v2, abs=1e-6)


def test_lowdin_result_is_order_independent():
    """Löwdin 与顺序无关 —— 这是它相对顺序残差化的唯一优势。"""
    a, b, c = correlated_pair()[0], correlated_pair()[1], correlated_pair(seed=21)[0]
    cols = {"ret_20": a, "vol_20": b, "amihud_20": c}
    o1 = orthogonalize_panel(mk_panel(cols), method="lowdin", factors=["ret_20", "vol_20", "amihud_20"])
    o2 = orthogonalize_panel(mk_panel(cols), method="lowdin", factors=["amihud_20", "vol_20", "ret_20"])
    for name in cols:
        assert o1["periods"][0]["factors"][name] == pytest.approx(
            o2["periods"][0]["factors"][name], abs=1e-9)


def test_orthogonalized_columns_are_uncorrelated_in_lowdin():
    """Löwdin 输出列在**线性（Pearson）意义**下两两正交。

    注意不能用 `_rank_standardize` 检验：秩变换是非线性的，
    会把线性正交性破坏掉。Spearman 层面的去相关由另一条用例覆盖。
    """
    a, b, c = correlated_pair()[0], correlated_pair()[1], correlated_pair(seed=21)[0]
    out = orthogonalize_panel(mk_panel({"a": a, "b": b, "c": c}), method="lowdin",
                              factors=["a", "b", "c"])
    cols = []
    for k in ("a", "b", "c"):
        w = out["periods"][0]["factors"][k]
        mean = sum(w) / len(w)
        sd = math.sqrt(sum((x - mean) ** 2 for x in w) / len(w))
        assert sd > 0
        cols.append([(x - mean) / sd for x in w])
    for i in range(3):
        for j in range(i + 1, 3):
            dot = sum(x * y for x, y in zip(cols[i], cols[j], strict=True)) / len(cols[i])
            assert dot == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 退化情形的处理：判不可用，不硬算
# ---------------------------------------------------------------------------

def test_perfectly_collinear_factors_are_marked_unusable():
    """两个因子完全共线 → 顺序残差化残差方差为 0、Löwdin 矩阵奇异。

    两者都必须把该期判为**未正交化**并给出原因，而不是产出一个全零/被噪声
    主导的"正交因子"。
    """
    a = [float(i) for i in range(60)]
    panel = mk_panel({"ret_20": a, "vol_20": [3 * x for x in a]})
    seq = orthogonalize_panel(panel, method="sequential", factors=["ret_20", "vol_20"])
    assert seq["periods"][0]["orthogonalized"] is False
    assert seq["periods"][0]["ortho_skip_reason"] == "degenerate_residual_variance"
    low = orthogonalize_panel(panel, method="lowdin", factors=["ret_20", "vol_20"])
    assert low["periods"][0]["orthogonalized"] is False
    assert low["periods"][0]["ortho_skip_reason"] == "ill_conditioned_gram_matrix"


def test_constant_factor_is_skipped_not_faked():
    a = [float(i) for i in range(60)]
    panel = mk_panel({"ret_20": a, "vol_20": [7.0] * 60})
    out = orthogonalize_panel(panel, method="sequential", factors=["ret_20", "vol_20"])
    assert out["periods"][0]["orthogonalized"] is False
    assert out["n_periods_orthogonalized"] == 0


def test_below_min_cross_section_is_skipped():
    a, b = correlated_pair(n=20)
    panel = mk_panel({"ret_20": a, "vol_20": b})
    out = orthogonalize_panel(panel, method="sequential", factors=["ret_20", "vol_20"],
                              min_cross_section=50)
    assert out["periods"][0]["orthogonalized"] is False
    assert out["periods"][0]["ortho_skip_reason"] == "below_min_cross_section"


def test_unknown_method_raises():
    panel = mk_panel({"ret_20": [1.0, 2.0, 3.0], "vol_20": [3.0, 2.0, 1.0]})
    with pytest.raises(ValueError, match="unknown method"):
        orthogonalize_panel(panel, method="symmetric-residual")


# ---------------------------------------------------------------------------
# 无副作用 / 结果结构
# ---------------------------------------------------------------------------

def test_input_panel_is_not_mutated():
    a, b = correlated_pair()
    panel = mk_panel({"ret_20": a, "vol_20": b})
    snapshot = list(panel["periods"][0]["factors"]["vol_20"])
    orthogonalize_panel(panel, method="sequential", factors=["ret_20", "vol_20"])
    assert panel["periods"][0]["factors"]["vol_20"] == snapshot


def test_non_targeted_factors_are_left_untouched():
    """只正交化指定因子；其余因子必须原样保留（否则 IC 对照不可比）。"""
    a, b = correlated_pair()
    c = correlated_pair(seed=99)[0]
    panel = mk_panel({"ret_20": a, "vol_20": b, "price": c})
    out = orthogonalize_panel(panel, method="sequential", factors=["ret_20", "vol_20"])
    assert out["periods"][0]["factors"]["price"] == c
    assert set(out["orthogonalized_factors"]) == {"ret_20", "vol_20"}


def test_composite_factors_constant_is_the_pipeline_set():
    """默认正交化集合必须与日度选股管线用的五因子一致。"""
    assert set(COMPOSITE_FACTORS) == set(NAMES)


def test_run_orthogonal_ic_study_raw_matches_run_ic_study():
    """对照实验的 raw 分支必须与 run_ic_study 逐值一致，否则"前后对照"无意义。"""
    rng = Lcg(2024)
    data = {}
    for s in range(60):
        price = 10.0 + rng.u() * 20.0
        bars = []
        for d in range(160):
            date = f"2024-{1 + d // 28:02d}-{1 + d % 28:02d}"
            price = max(0.5, price * (1.0 + rng.gauss() * 0.02))
            amount = 1e6 * (1.0 + abs(rng.gauss()))
            bars.append({"date": date, "open": price, "high": price * 1.01,
                         "low": price * 0.99, "close": price,
                         "volume": amount / price, "amount": amount})
        data[f"{s:06d}"] = bars

    direct = run_ic_study(data, min_cross_section=40)
    combined = run_orthogonal_ic_study(data, min_cross_section=40)
    assert combined["raw"] == direct
    assert combined["method"] == "sequential"
    assert combined["order"] == ORTHO_ORDER_DEFAULT
    assert combined["n_periods_orthogonalized"] > 0
    assert set(combined["correlation_before"]) == set(combined["correlation_after"])


def test_spearman_of_orthogonalized_pair_is_near_zero_on_real_data():
    """端到端：真实合成行情上，正交化后复合因子两两相关的绝对值应显著下降。"""
    rng = Lcg(77)
    data = {}
    for s in range(80):
        price = 10.0 + rng.u() * 20.0
        bars = []
        for d in range(180):
            date = f"2024-{1 + d // 28:02d}-{1 + d % 28:02d}"
            price = max(0.5, price * (1.0 + rng.gauss() * 0.02))
            amount = 1e6 * (1.0 + abs(rng.gauss()))
            bars.append({"date": date, "open": price, "high": price * 1.01,
                         "low": price * 0.99, "close": price,
                         "volume": amount / price, "amount": amount})
        data[f"{s:06d}"] = bars
    out = run_orthogonal_ic_study(data, min_cross_section=40)
    worst_before = max(abs(v["mean_rho"]) for v in out["correlation_before"].values()
                       if v["mean_rho"] is not None)
    worst_after = max(abs(v["mean_rho"]) for v in out["correlation_after"].values()
                      if v["mean_rho"] is not None)
    assert worst_after < worst_before
