# -*- coding: utf-8 -*-
"""数据窥探检验家族：PBO via CSCV + SPA + StepM（DATA_SNOOPING_PREREG）。

回答一个问题：**「从很多候选里挑出来的这个最好结果，值不值得信」**。
DSR/PSR（`multiple_testing.py`）校正的是夏普估计的选择偏差；
本模块校正的是另外两族：

* **PBO**（Bailey & López de Prado, 2014）：把序列切 S 块，遍历全部
  C(S, S/2) 种「训练/测试」划分，看「训练集最优配置在测试集的排名」
  是否系统性跌入下半区。PBO = 排名 > 0.5 的比例。
* **SPA**（Hansen, 2005）/**StepM**（Romano & Wolf, 2005）：k 个候选
  策略 vs 基准，用 studentized 自举检验「是否真有任何策略优于基准」，
  StepM 进一步逐策略 stepdown 输出调整 p 值。

## 两个口径陷阱（survey §8.6-②③，本模块的硬规则）

1. **PBO 阈值是 0.05，不是 0.5**：`pbo > alpha`（默认 0.05）即过拟合证据。
2. **输入是 losses（低=好），不是 returns**：`losses[j][t]` = 策略 j 在
   t 期相对基准的**损失**（本项目口径：`-(超额收益)`）。传 returns 会
   把结论整体反转——守卫 `tests/test_data_snooping.py` 的 S-3 用符号
   反转锁定方向。

## 依赖纪律

**纯 stdlib**（math / statistics / itertools / random）。survey 原建议
「用 arch.bootstrap 不自己实现」，但本项目生产代码零第三方依赖且 arch
未安装 ⇒ 自实现；风险由阳性/阴性对照与精确常数（C(16,8)=12,870）覆盖，
未与 arch 逐位对账（没装）——见 VERDICT 的已知局限。
"""
from __future__ import annotations

import itertools
import math
import random
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: StepM/SPA 自举的默认次数与种子（固定 ⇒ 确定性，见判据 S-4）。
DEFAULT_N_BOOT = 1000
DEFAULT_SEED = 20261018

#: CSCV 的默认分块数（Bailey 原文 S=16 ⇒ C(16,8)=12,870 种划分）。
DEFAULT_S_BLOCKS = 16

#: 学生化常量：方差为 0 时的替代尺度（避免 0/0；方向由均值符号决定）。
_EPS_SCALE = 1e-12


class PBOInputError(ValueError):
    """PBO 输入不合法（行不等长 / 块数不整除 / 配置不足）。"""


class SNInputError(ValueError):
    """SPA/StepM 输入不合法（策略不等长 / 样本不足）。"""


# --------------------------------------------------------------------------
# A2：PBO via CSCV
# --------------------------------------------------------------------------

def cscv_combinations(S: int = DEFAULT_S_BLOCKS) -> List[Tuple[Tuple[int, ...], Tuple[int, ...]]]:
    """全部 C(S, S/2) 种「训练/测试」块划分（确定性全枚举，无 RNG）。

    S 必须为正偶数。返回 [(is_blocks, oos_blocks), ...]，元素为块索引元组。
    """
    if S < 2 or S % 2 != 0:
        raise PBOInputError(f"S 必须为正偶数，收到 {S}")
    half = S // 2
    out: List[Tuple[Tuple[int, ...], Tuple[int, ...]]] = []
    for is_bits in itertools.combinations(range(S), half):
        is_set = set(is_bits)
        oos = tuple(i for i in range(S) if i not in is_set)
        out.append((tuple(is_bits), oos))
    return out


def _validate_matrix(matrix: Sequence[Sequence[Any]]) -> List[List[float]]:
    """行等长、可转 float、配置数 ≥ 2。"""
    if len(matrix) < 2:
        raise PBOInputError(f"至少需要 2 个候选配置，收到 {len(matrix)} 行")
    rows: List[List[float]] = []
    n_cols: Optional[int] = None
    for r in matrix:
        vals = [float(x) for x in r]
        if n_cols is None:
            n_cols = len(vals)
        elif len(vals) != n_cols:
            raise PBOInputError("各行长度必须相等（配置 × 时间的对齐矩阵）")
        rows.append(vals)
    assert n_cols is not None
    return rows


def _pbo_from_ranks(ranks: Sequence[float], alpha: float) -> Dict[str, Any]:
    """从相对排名序列汇总 PBO（判据阈值的**唯一**落点，供单测钉死）。

    阈值语义：``pbo = P(rank > 0.5)``，``overfit = pbo > alpha``。
    抽成独立函数是为了让守卫能用合成排名序列精确检验边界
    （0.5 不算越过、0.6 算）——用真实矩阵做不到（排名由数据决定）。
    """
    n_over = sum(1 for r in ranks if r > 0.5)
    pbo = n_over / len(ranks) if ranks else 0.0
    return {
        "pbo": pbo,
        "overfit": pbo > alpha,
        "alpha": alpha,
        "n_combinations": len(ranks),
        "n_over": n_over,
        "rank_mean": statistics.fmean(ranks) if ranks else 0.0,
        "rank_max": max(ranks) if ranks else 0.0,
    }


def pbo_cscv(matrix: Sequence[Sequence[Any]],
             S: int = DEFAULT_S_BLOCKS,
             alpha: float = 0.05) -> Dict[str, Any]:
    """PBO：训练最优配置在测试集跌入下半区的概率。

    参数
    ----
    matrix : 配置 × 时间的收益矩阵（行=候选配置，列=按时间排序）。
    S : 等分块数（默认 16 ⇒ C(16,8)=12,870 种划分）。
    alpha : 过拟合判定阈值（默认 **0.05**，不是 0.5——survey §8.6-②）。

    返回
    ----
    ``{pbo, overfit, alpha, n_combinations, n_over, rank_mean, rank_max,
      S, n_periods, n_configs, ranks}``

    * ``pbo`` ∈ [0,1]：相对排名 > 0.5 的划分占比。
    * ``overfit``：``pbo > alpha``（过拟合证据）。
    * ``ranks``：每个划分的相对排名（调试/审计用）。
    """
    rows = _validate_matrix(matrix)
    n_configs = len(rows)
    n_periods = len(rows[0])
    if n_periods < S:
        raise PBOInputError(f"序列长度 {n_periods} < 分块数 {S}，无法 CSCV")
    if n_periods % S != 0:
        raise PBOInputError(f"序列长度 {n_periods} 不能被 S={S} 整除（块内需等长）")

    block_len = n_periods // S
    # 每行按块聚合：block_means[j][b] = 第 j 个配置第 b 块的均值
    block_means: List[List[float]] = []
    for row in rows:
        per_block = [statistics.fmean(row[b * block_len:(b + 1) * block_len])
                     for b in range(S)]
        block_means.append(per_block)

    combos = cscv_combinations(S)
    ranks: List[float] = []
    for is_bits, oos_bits in combos:
        is_means = [statistics.fmean([block_means[j][b] for b in is_bits])
                    for j in range(n_configs)]
        oos_means = [statistics.fmean([block_means[j][b] for b in oos_bits])
                     for j in range(n_configs)]
        best = max(range(n_configs), key=lambda j: is_means[j])
        # 相对排名：测试集中**优于**训练最优的配置占比（0=它仍最优，1=它最差）
        n_better = sum(1 for j in range(n_configs) if oos_means[j] > oos_means[best])
        ranks.append(n_better / (n_configs - 1))

    summary = _pbo_from_ranks(ranks, alpha)
    summary.update({
        "n_combinations": len(combos),
        "S": S,
        "n_periods": n_periods,
        "n_configs": n_configs,
        "ranks": ranks,
    })
    return summary

# --------------------------------------------------------------------------
# A3：SPA / StepM（输入口径：losses，低=好）
# --------------------------------------------------------------------------

def _validate_losses(losses: Sequence[Sequence[Any]]) -> List[List[float]]:
    """策略等长、可转 float、至少 1 个策略、长度 ≥ 2。"""
    if len(losses) < 1:
        raise SNInputError("至少需要 1 个策略")
    rows: List[List[float]] = []
    n_cols: Optional[int] = None
    for r in losses:
        vals = [float(x) for x in r]
        if n_cols is None:
            n_cols = len(vals)
        elif len(vals) != n_cols:
            raise SNInputError("各策略损失序列必须等长（对齐的时间指数）")
        rows.append(vals)
    assert n_cols is not None
    if n_cols < 2:
        raise SNInputError(f"每策略至少 2 期，收到 {n_cols}")
    return rows


def _studentized_t(d_bar: float, s: float, n: int) -> float:
    """sqrt(n)·d̄/s；s≈0 时按均值符号给 ±inf（0 ⇒ 0）。"""
    if s <= _EPS_SCALE:
        if d_bar > 0:
            return math.inf
        if d_bar < 0:
            return -math.inf
        return 0.0
    return math.sqrt(n) * d_bar / s


def _bootstrap_indices(rng: random.Random, n: int) -> List[int]:
    """iid 自举：整段重采样 T 个时间指数（所有策略共用同一组指数，
    保留横截面相依——这是 SPA/StepM 的标准做法）。"""
    return [rng.randrange(n) for _ in range(n)]


def _spa_core(losses: List[List[float]],
              n_boot: int,
              seed: int) -> Dict[str, Any]:
    """SPA 主过程（studentized，iid 自举）。

    内部约定 d = −losses（**正=优于基准**，即超额方向）；
    H0：没有任何策略优于基准（d̄_j ≤ 0 ∀j）。
    统计量 V = max_j √T·d̄_j/s_j（studentized）。

    **近期中心化口径（本实现的明确选择）**：每条序列**各自去均值**
    （White Reality Check 式），自举 max 统计量。理由与边界：
    复合零假设「所有 d̄_j ≤ 0」的 LFC 是全部为 0，各自去均值正是它的
    无偏自举估计 ⇒ **保守但有效**；Hansen (2005) 的 consistent SPA 变体
    用「减最优者均值」的中心化（以选中身份为条件），功效略有不同。
    本实现选保守口径并把公式写死在此，供复核者逐行对照；未与
    `arch.bootstrap.SPA` 逐位对账（arch 未安装）——见 VERDICT 已知局限。
    """
    n = len(losses)
    T = len(losses[0])
    # d = −losses：超额方向（正=好）
    d_rows = [[-x for x in row] for row in losses]
    d_bar = [statistics.fmean(row) for row in d_rows]
    s = [statistics.stdev(row) if T >= 2 else 0.0 for row in d_rows]
    t_obs = [_studentized_t(d_bar[j], s[j], T) for j in range(n)]
    v_obs = max(t_obs)

    # 近期中心化：各自去均值（LFC：全部摆到 0 边界）
    centered = [[d_rows[j][t] - d_bar[j] for t in range(T)] for j in range(n)]

    rng = random.Random(seed)
    exceed = 0
    v_boot: List[float] = []
    for _ in range(n_boot):
        idx = _bootstrap_indices(rng, T)
        t_boot = []
        for j in range(n):
            sample = [centered[j][t] for t in idx]
            d_b = statistics.fmean(sample)
            s_b = statistics.stdev(sample) if T >= 2 else 0.0
            t_boot.append(_studentized_t(d_b, s_b, T))
        v_b = max(t_boot)
        v_boot.append(v_b)
        if v_b >= v_obs:
            exceed += 1
    p_value = exceed / n_boot
    return {
        "statistic": v_obs,
        "p_value": p_value,
        "n_strategies": n,
        "n_periods": T,
        "n_boot": n_boot,
        "seed": seed,
        "t_stats": t_obs,
        "mean_d": d_bar,
        "v_boot_max": max(v_boot) if v_boot else None,
    }


def spa_test(losses: Sequence[Sequence[Any]],
             alpha: float = 0.05,
             n_boot: int = DEFAULT_N_BOOT,
             seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    """SPA（Hansen 2005）：H0 = 没有任何策略优于基准。

    参数
    ----
    losses : 策略 × 时间的**损失**矩阵（低=好；本项目口径 = −超额收益）。
    alpha : 显著性水平（默认 0.05）。
    n_boot / seed : 自举次数与种子（固定 ⇒ 确定性）。

    返回 ``{statistic, p_value, rejected, alpha, n_strategies, n_periods,
    n_boot, seed, t_stats, mean_d, v_boot_max}``。
    ``rejected = p_value < alpha`` ⇒ 有证据表明至少一个策略优于基准。
    """
    rows = _validate_losses(losses)
    core = _spa_core(rows, n_boot, seed)
    core["alpha"] = alpha
    core["rejected"] = core["p_value"] < alpha
    return core


def stepm_test(losses: Sequence[Sequence[Any]],
               alpha: float = 0.05,
               n_boot: int = DEFAULT_N_BOOT,
               seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    """StepM（Romano & Wolf 2005）：逐策略 stepdown，FWER 控制。

    流程：按 t 统计量降序，每步对**剩余子集**做自举 max 分布调整；
    一旦某步不拒绝，其后全部不拒绝。返回逐策略调整 p 与是否拒绝。

    输入口径与 `spa_test` 相同（losses，低=好）。
    """
    rows = _validate_losses(losses)
    n = len(rows)
    T = len(rows[0])
    d_rows = [[-x for x in row] for row in losses]
    d_bar = [statistics.fmean(row) for row in d_rows]
    s = [statistics.stdev(row) if T >= 2 else 0.0 for row in d_rows]
    t_obs = [_studentized_t(d_bar[j], s[j], T) for j in range(n)]

    order = sorted(range(n), key=lambda j: t_obs[j], reverse=True)
    remaining = list(order)
    adjusted_p: Dict[int, float] = {}
    rejected: Dict[int, bool] = {}
    stop = False
    for j in order:
        if stop or not remaining:
            adjusted_p[j] = 1.0
            rejected[j] = False
            continue
        # 剩余子集的观测 max
        t_sub_max = max(t_obs[k] for k in remaining)
        # 子集近期中心化：各自去均值（与 SPA 同口径，见 _spa_core 文档）
        centered = {k: [d_rows[k][t] - d_bar[k] for t in range(T)]
                    for k in remaining}
        rng = random.Random(seed)
        exceed = 0
        for _ in range(n_boot):
            idx = _bootstrap_indices(rng, T)
            t_boot = []
            for k in remaining:
                sample = [centered[k][t] for t in idx]
                d_b = statistics.fmean(sample)
                s_b = statistics.stdev(sample) if T >= 2 else 0.0
                t_boot.append(_studentized_t(d_b, s_b, T))
            if max(t_boot) >= t_sub_max:
                exceed += 1
        p_adj = exceed / n_boot
        adjusted_p[j] = p_adj
        rejected[j] = p_adj < alpha
        if not rejected[j]:
            stop = True  # stepdown：此后全部不拒绝
        remaining = [k for k in remaining if k != j]

    return {
        "alpha": alpha,
        "n_strategies": n,
        "n_periods": T,
        "n_boot": n_boot,
        "seed": seed,
        "t_stats": t_obs,
        "order": order,
        "adjusted_p": adjusted_p,
        "rejected": rejected,
        "any_rejected": any(rejected.values()),
    }
