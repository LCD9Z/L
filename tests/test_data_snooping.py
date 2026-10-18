# -*- coding: utf-8 -*-
"""数据窥探检验守卫：PBO via CSCV + SPA/StepM（DATA_SNOOPING_PREREG）。

## 锁住什么

P 组（PBO）：
- P-1 精确常数 C(16,8)=12,870 全枚举；
- P-2 已知答案两端：占优矩阵 ⇒ PBO=0；按块交替矩阵 ⇒ 排名>0.5 的
  划分数 == 12,870−4,900（4/4 平局split不计）——解析值，不是拍的；
- P-3 确定性（无 RNG）；
- P-4 阈值口径 alpha=0.05（**不是 0.5**）；
- P-5 零第三方依赖。

S 组（SPA/StepM）：
- S-1 阳性对照：植入已知强信号必须判显著；
- S-2 阴性对照：全零/零均值噪声必须不判显著；
- S-3 方向锁定：符号反转（把 returns 当 losses）结论必须反转；
- S-4 确定性：同种子逐位相同、异种子 p 值邻域有界；
- S-5 真实应用：归档滚动评估矩阵可跑且结构合法；
- S-6 零第三方依赖（同 P-5）。
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from validation.data_snooping import (
    PBOInputError,
    SNInputError,
    cscv_combinations,
    pbo_cscv,
    spa_test,
    stepm_test,
)

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "validation" / "data_snooping.py"

SEED = 20261018  # 模块默认种子（判据 S-4 复算用）


def _positive_control_losses(T: int = 60):
    """固定构造的阳性对照：策略 0 每期稳定跑赢基准 1%，另两个是纯噪声。

    用独立 Random(7) 构造（不用模块默认种子）⇒ 数据与自举种子解耦。
    """
    rng = random.Random(7)
    excess_a = [0.01 + rng.gauss(0, 0.003) for _ in range(T)]
    excess_b = [rng.gauss(0, 0.003) for _ in range(T)]
    excess_c = [rng.gauss(0, 0.003) for _ in range(T)]
    return [[-x for x in excess_a], [-x for x in excess_b], [-x for x in excess_c]]


# --------------------------------------------------------------------------
# P 组
# --------------------------------------------------------------------------

def test_p1_combination_count_is_exact():
    """P-1：C(16,8) == 12,870，且每个划分 8+8、不交、并集完备。"""
    combos = cscv_combinations(16)
    assert len(combos) == math.comb(16, 8) == 12870
    for is_bits, oos_bits in combos[::997]:  # 抽样 13 个做结构断言
        assert len(is_bits) == 8 and len(oos_bits) == 8
        assert set(is_bits) & set(oos_bits) == set()
        assert set(is_bits) | set(oos_bits) == set(range(16))
    with pytest.raises(PBOInputError):
        cscv_combinations(15)  # 奇数块拒绝


def test_p2a_dominant_config_gives_zero_pbo():
    """P-2a：占优配置（训练最优恒为测试最优）⇒ PBO == 0。"""
    matrix = [[1.0] * 32, [0.0] * 32]
    r = pbo_cscv(matrix, S=16)
    assert r["pbo"] == 0.0
    assert r["n_over"] == 0
    assert r["overfit"] is False


def test_p2b_block_alternating_gives_exact_known_answer():
    """P-2b：按块交替矩阵 ⇒ 排名>0.5 的划分数 == 12,870 − C(8,4)²。

    解析：IS 含偶数块数 e≠4 时训练最优必为测试最差（排名 1）；
    e=4 时两边持平（并列，排名 0）。C(8,4)²=4,900 个 4/4 split。
    """
    alt_a = [1.0 if (b // 2) % 2 == 0 else -1.0 for b in range(32)]
    alt_b = [-x for x in alt_a]
    r = pbo_cscv([alt_a, alt_b], S=16)
    assert r["n_over"] == 12870 - 4900
    assert abs(r["pbo"] - (12870 - 4900) / 12870) < 1e-12
    assert sorted(set(r["ranks"])) == [0.0, 1.0]


def test_p3_deterministic():
    """P-3：同输入两次调用逐位相同（含 ranks 全表）。"""
    matrix = [[random.Random(3).gauss(0, 0.01) for _ in range(64)] for _ in range(4)]
    a = pbo_cscv(matrix, S=16)
    b = pbo_cscv(matrix, S=16)
    assert a == b


def test_p4_alpha_threshold_is_005():
    """P-4：默认 alpha=0.05（survey 纠正值，不是 0.5）；双向判据。"""
    assert pbo_cscv([[1.0] * 32, [0.0] * 32])["alpha"] == 0.05
    clean = pbo_cscv([[1.0] * 32, [0.0] * 32])
    assert clean["overfit"] is False
    alt_a = [1.0 if (b // 2) % 2 == 0 else -1.0 for b in range(32)]
    dirty = pbo_cscv([alt_a, [-x for x in alt_a]])
    assert dirty["pbo"] > 0.05 and dirty["overfit"] is True


def test_p4b_threshold_boundary_is_exactly_half():
    """P-4 边界：0.5 不算越过、0.6 算（合成排名钉死阈值语义）。

    真实矩阵做不到这一点——P-2b 的排名只有 0/1 两种值，阈值在
    (0.5, 0.9] 内改动它抓不到（反向验证实证过）。故直接单测计数助手：
    阈值若被改成 > 0.9 或 > 0.4，本测试即红。
    """
    from validation.data_snooping import _pbo_from_ranks
    assert _pbo_from_ranks([0.5] * 10, 0.05)["pbo"] == 0.0
    assert _pbo_from_ranks([0.5] * 10, 0.05)["overfit"] is False
    assert _pbo_from_ranks([0.6] * 10, 0.05)["pbo"] == 1.0
    assert _pbo_from_ranks([0.6] * 10, 0.05)["overfit"] is True
    mixed = _pbo_from_ranks([0.5] * 9 + [0.6], 0.05)
    assert mixed["n_over"] == 1 and mixed["overfit"] is True
    # alpha 边界：pbo == alpha 不算过（严格大于）
    assert _pbo_from_ranks([0.6] * 5 + [0.5] * 5, 0.5)["overfit"] is False


def test_p5_p6_input_validation():
    """P-5：输入不合法必须抛错（行不等长 / 块数不整除 / 配置不足 / 序列过短）。"""
    with pytest.raises(PBOInputError):
        pbo_cscv([[1.0, 2.0], [3.0]])           # 行不等长
    with pytest.raises(PBOInputError):
        pbo_cscv([[1.0] * 30, [0.0] * 30])      # 30 % 16 != 0
    with pytest.raises(PBOInputError):
        pbo_cscv([[1.0] * 32])                  # 只有 1 个配置
    with pytest.raises(PBOInputError):
        pbo_cscv([[1.0] * 8, [0.0] * 8])        # 长度 < S


def test_p6_no_third_party_imports():
    """P-5/S-6：模块源码不得 import numpy/pandas/arch/scipy。"""
    text = MODULE.read_text(encoding="utf-8")
    for banned in ("numpy", "pandas", "arch", "scipy", "statsmodels"):
        assert f"import {banned}" not in text, f"发现第三方依赖 {banned}"


# --------------------------------------------------------------------------
# S 组
# --------------------------------------------------------------------------

def test_s1_positive_control_rejects():
    """S-1：植入已知强信号 ⇒ SPA 与 StepM 均判显著。"""
    losses = _positive_control_losses()
    r = spa_test(losses, alpha=0.05, n_boot=1000, seed=SEED)
    assert r["rejected"] is True
    assert r["p_value"] < 0.05
    assert r["statistic"] > 5  # 强信号的 t 统计量应在数十量级
    r2 = stepm_test(losses, alpha=0.05, n_boot=1000, seed=SEED)
    assert r2["any_rejected"] is True
    assert r2["rejected"][0] is True  # 策略 0（真信号）被逐步拒绝


def test_s2_negative_controls_do_not_reject():
    """S-2：确定性阴性对照必须不判显著。

    两个构造都是**确定性**的（p 精确可算）：
    ① 全零损失 ⇒ t 全 0、自举全 0 ⇒ p == 1.0；
    ② 全常量且全部跑输基准 ⇒ t 全 −inf、自举全 0 ⇒ p == 1.0。

    ⚠️ 不用「零均值噪声」做阴性对照：真零假设下 p 近似均匀分布，
    固定种子也有 ~5% 概率抽中 p<0.05（那是检验**水准**，不是缺陷——
    实测 Random(11) 构造即抽到 p=0.012）。噪声例只做结构冒烟。
    """
    zeros = [[0.0] * 60 for _ in range(3)]
    r = spa_test(zeros, alpha=0.05, n_boot=1000, seed=SEED)
    assert r["p_value"] == 1.0 and r["rejected"] is False
    r2 = stepm_test(zeros, alpha=0.05, n_boot=1000, seed=SEED)
    assert r2["any_rejected"] is False

    const_worse = [[0.01] * 60 for _ in range(3)]  # 全部跑输基准的常量
    r = spa_test(const_worse, alpha=0.05, n_boot=1000, seed=SEED)
    assert r["p_value"] == 1.0 and r["rejected"] is False
    r2 = stepm_test(const_worse, alpha=0.05, n_boot=1000, seed=SEED)
    assert r2["any_rejected"] is False


def test_s2b_noise_case_is_structural_smoke_only():
    """S-2 附注：零均值噪声只验证值域合法（真零假设的 ~5% 水准不写死）。"""
    rng = random.Random(11)
    noise = [[rng.gauss(0, 0.003) for _ in range(60)] for _ in range(3)]
    r = spa_test([[-x for x in row] for row in noise], alpha=0.05,
                 n_boot=1000, seed=SEED)
    assert 0.0 <= r["p_value"] <= 1.0
    assert r["n_strategies"] == 3 and r["n_periods"] == 60


def test_s3_sign_flip_reverses_conclusion():
    """S-3：同一数据符号反转（把 returns 当 losses 传）⇒ 结论必须反转。

    这是 survey §8.6-③ 陷阱的守卫：SPA/StepM 吃 losses 不吃 returns。
    """
    rng = random.Random(7)
    T = 60
    excess_a = [0.01 + rng.gauss(0, 0.003) for _ in range(T)]
    excess_b = [rng.gauss(0, 0.003) for _ in range(T)]
    excess_c = [rng.gauss(0, 0.003) for _ in range(T)]
    losses = [[-x for x in excess_a], [-x for x in excess_b], [-x for x in excess_c]]
    flipped = [list(excess_a), list(excess_b), list(excess_c)]
    ok = spa_test(losses, alpha=0.05, n_boot=1000, seed=SEED)
    bad = spa_test(flipped, alpha=0.05, n_boot=1000, seed=SEED)
    assert ok["rejected"] is True
    assert bad["rejected"] is False


def test_s4_determinism_and_seed_neighborhood():
    """S-4：同种子逐位相同；异种子 p 值邻域有界（噪声对照上验证）。"""
    rng = random.Random(11)
    noise = [[rng.gauss(0, 0.003) for _ in range(60)] for _ in range(3)]
    losses = [[-x for x in row] for row in noise]
    a = spa_test(losses, alpha=0.05, n_boot=1000, seed=SEED)
    b = spa_test(losses, alpha=0.05, n_boot=1000, seed=SEED)
    assert a == b
    c = spa_test(losses, alpha=0.05, n_boot=1000, seed=999)
    assert abs(a["p_value"] - c["p_value"]) <= 0.2, (
        f"异种子 p 值跳动过大: {a['p_value']} vs {c['p_value']}")


def test_s5_real_archived_matrix_runs():
    """S-5：归档滚动评估的 4 配置 × 6 窗口矩阵可跑且结构合法。

    只验证机制跑通与值域；具体数值（不论方向）记入 VERDICT。
    """
    v2 = json.loads((ROOT / "reports" / "v2_rolling_eval_ew.json")
                    .read_text(encoding="utf-8"))["windows"]
    v3 = json.loads((ROOT / "reports" / "v3_rolling_eval_ew_full.json")
                    .read_text(encoding="utf-8"))["windows"]
    # 两侧窗口必须同序对齐（否则拼矩阵是口径错误）
    assert [w["oos_start"] for w in v2] == [w["oos_start"] for w in v3]
    rows = [
        [-w["annualized_excess"] for w in v2],
        [-w["ew_annualized_excess"] for w in v2],
        [-w["annualized_excess"] for w in v3],
        [-w["ew_annualized_excess"] for w in v3],
    ]
    r = spa_test(rows, alpha=0.05, n_boot=1000, seed=SEED)
    assert 0.0 <= r["p_value"] <= 1.0
    assert r["n_strategies"] == 4 and r["n_periods"] == 6
    r2 = stepm_test(rows, alpha=0.05, n_boot=1000, seed=SEED)
    assert set(r2["adjusted_p"]) == {0, 1, 2, 3}
    # 确定性（真实数据上再验一次）
    r3 = spa_test(rows, alpha=0.05, n_boot=1000, seed=SEED)
    assert r == r3


def test_s6_input_validation():
    """S-6：策略不等长 / 样本不足必须抛错。"""
    with pytest.raises(SNInputError):
        spa_test([[0.1, 0.2], [0.3]])
    with pytest.raises(SNInputError):
        stepm_test([[0.1]])
    with pytest.raises(SNInputError):
        spa_test([])
