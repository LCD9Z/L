# -*- coding: utf-8 -*-
"""PREREG_02 执行脚本的单元测试（`scripts/microstructure_ic.py`）。

## 防什么（按严重度排）

1. **前向收益用错价**：`close→close` 与 `T+1 open→close` 在真实数据上差 100~300bp，
   而这正是「旧 IC 是否含前视」的唯一自由变量 ⇒ 必须有测试钉住。
2. **计数闸形同虚设**：动量档 < 30 / 单元格 < 20 时若悄悄放行，
   双排序会在极薄切片上给出噪声当结论 —— 正是 Critic 点名的陷阱。
3. **块自举没生效**：块长退化成 1 时 CI 会变窄，若测试不钉住，
   「算了个自举」就只是装饰（与 PREREG_01 的「验证者=被验证者」同型）。
4. **闸门口径被悄悄放宽**：`gate_status` 的 `passed_with_note` 必须
   **严格卡在实测噪声底之内**，不能变成「差一点也放行」。

所有用例都不读磁盘（除构造的合成数组），跑得动、跑得快。
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))   # 裸名导入同级脚本（mypy 单一模块名）

from microstructure_ic import (  # noqa: E402
    DIRECTION, FAMILY_13, H_MAIN, MIN_BUCKET, MIN_CELL, NEW_FACTORS, OLD_FACTORS,
    PANEL_COLS, _bucket_by_rank, _qr_from_raw, block_bootstrap_means,
    ci_from_means, compute_factors, double_sort_section, forward_return_close,
    forward_return_open, gate_status, year_stability,
)

COL = {n: i for i, n in enumerate(PANEL_COLS)}


def _bars(closes, opens=None, highs=None, lows=None, vol=None, amt=None) -> np.ndarray:
    n = len(closes)
    b = np.zeros((n, 8), dtype=np.float64)
    c = np.asarray(closes, dtype=np.float64)
    b[:, COL["close"]] = c
    b[:, COL["open"]] = c if opens is None else np.asarray(opens, dtype=np.float64)
    b[:, COL["high"]] = c * 1.01 if highs is None else np.asarray(highs, dtype=np.float64)
    b[:, COL["low"]] = c * 0.99 if lows is None else np.asarray(lows, dtype=np.float64)
    b[:, COL["volume"]] = 1000.0 if vol is None else np.asarray(vol, dtype=np.float64)
    b[:, COL["amount"]] = 1.0e6 if amt is None else np.asarray(amt, dtype=np.float64)
    b[:, COL["turnover"]] = 0.01
    b[:, COL["is_st"]] = 0.0
    return b


# ---------------------------------------------------------------------------
# 1 前向收益口径
# ---------------------------------------------------------------------------

def test_forward_return_open_uses_next_open_not_close():
    """T+1 开盘价必须真的被用到（否则等于没改口径）。"""
    closes = [10.0] * 30
    opens = [10.0] * 30
    opens[11] = 20.0                     # 只有 T+1 的开盘被抬到 20
    b = _bars(closes, opens=opens)
    r_open = forward_return_open(b, 10, 5, COL)
    r_close = forward_return_close(b, 10, 5, COL)
    assert r_close == pytest.approx(0.0, abs=1e-12)
    assert r_open == pytest.approx(10.0 / 20.0 - 1.0, rel=1e-12)
    assert r_open != pytest.approx(r_close)


def test_forward_return_nan_when_open_missing():
    """停牌日开盘价为 0 ⇒ 必须返回 NaN，不许填 0、不许顺延。"""
    closes = [10.0] * 30
    opens = [10.0] * 30
    opens[11] = 0.0
    b = _bars(closes, opens=opens)
    assert math.isnan(forward_return_open(b, 10, 5, COL))
    # 越界同样 NaN
    assert math.isnan(forward_return_open(b, 28, 5, COL))


# ---------------------------------------------------------------------------
# 2 因子符号与定义
# ---------------------------------------------------------------------------

def test_factor_family_sizes():
    """13 族 = 3 新 + 10 既有；新因子方向全为 +1（预注册 §1.1）。"""
    assert len(NEW_FACTORS) == 3
    assert len(OLD_FACTORS) == 10
    assert len(FAMILY_13) == 13
    assert set(FAMILY_13) == set(NEW_FACTORS) | set(OLD_FACTORS)
    assert all(DIRECTION[f] == 1 for f in NEW_FACTORS)


def test_gap_smoothness_is_higher_for_smoother_series():
    """GAP = −MA20(|跳空|)/MA20(|日收益|)：越平滑越大（越接近 0）。"""
    n = 40
    smooth_c = 10 + 0.05 * np.arange(n)
    smooth_o = np.r_[10.0, smooth_c[:-1]]          # 开盘=前收 ⇒ 无跳空
    b_smooth = _bars(smooth_c, opens=smooth_o)

    jumpy_o = np.r_[10.0, smooth_c[:-1]] * 1.05     # 每日 5% 跳空
    b_jumpy = _bars(smooth_c, opens=jumpy_o)

    f_s = compute_factors(b_smooth, COL)["gap_smoothness_20d"][-1]
    f_j = compute_factors(b_jumpy, COL)["gap_smoothness_20d"][-1]
    assert f_s == pytest.approx(0.0, abs=1e-9)
    assert f_j < -1.0
    assert f_s > f_j


def test_clv_is_one_at_high_and_minus_one_at_low():
    n = 30
    closes = [10.0] * n
    b_up = _bars(closes, highs=[10.0] * n, lows=[9.0] * n)      # 收在最高
    b_dn = _bars(closes, highs=[11.0] * n, lows=[10.0] * n)     # 收在最低
    assert compute_factors(b_up, COL)["clv_close_location_20d"][-1] == pytest.approx(1.0)
    assert compute_factors(b_dn, COL)["clv_close_location_20d"][-1] == pytest.approx(-1.0)


def test_clv_requires_15_valid_days():
    """H==L 的日子全被跳过 ⇒ 有效天数不足时必须给 NaN，不许用 1/2 天硬撑。"""
    n = 30
    closes = [10.0] * n
    flat = _bars(closes, highs=[10.0] * n, lows=[10.0] * n)     # 全部 H==L
    assert math.isnan(compute_factors(flat, COL)["clv_close_location_20d"][-1])


def test_qr_prefers_price_rise_without_volume():
    """截面 z 分数：价涨量缩的那只 QR 必须更高。"""
    ret5 = np.array([[0.10, 0.10, -0.10]])
    vr = np.array([[0.5, 2.0, 1.0]])
    qr = _qr_from_raw(ret5, vr, min_valid=3)[0]
    assert qr[0] > qr[1]      # 同涨幅，量更小者更高
    assert qr[0] > qr[2]      # 价涨量缩 > 价跌


# ---------------------------------------------------------------------------
# 3 分档与 Double Sort 的计数闸
# ---------------------------------------------------------------------------

def test_bucket_by_rank_gives_k_groups_and_keeps_ties_together():
    x = np.array([1.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    b = _bucket_by_rank(x, 3)
    assert set(b.tolist()) == {0, 1, 2}
    assert b[0] == b[1], "并列值必须落在同一档"


def test_thin_bucket_guard_is_subsumed_by_stricter_guards():
    """「动量档 < 30 ⇒ 整截面 invalid」是 **Critic 追加** 的闸，但它在本设计下**已被更强条件蕴含**：

    * 分档用**秩等分**，三档必然近似等大 ⇒ `n/3 ≥ MIN_BUCKET` 只需 `n ≥ 90`；
    * 而 `MIN_UNIVERSE = 150 ⇒ n/3 ≥ 50 > 30`；
    * 且 `MIN_CELL = 20` 要求每格 ≥20，五组 ⇒ 每档 ≥100，同样强于 30。

    所以真正的约束是 `MIN_CELL`（每档 ≥100），比 30 严 3 倍以上。
    本测试把这个不等式关系钉住：**若将来有人调低 MIN_CELL 或加大 n_mom，
    使 `MIN_CELL × n_fac < MIN_BUCKET`，则 bucket 闸会重新变成活的** —— 那时它必须真的能触发。
    """
    assert MIN_CELL * 5 >= MIN_BUCKET, "MIN_CELL 隐含的档容量必须不弱于 MIN_BUCKET"
    assert MIN_BUCKET <= 150 // 3, "MIN_UNIVERSE 等分三档后必须满足 MIN_BUCKET"

    # 实测：截面太小时先被 universe 闸拦下（不是 bucket 闸）
    rng = np.random.default_rng(7)
    n = 60
    res = double_sort_section(rng.normal(size=n), rng.normal(size=n),
                              rng.normal(size=n))
    assert res["invalid"] is True
    assert res["reason"] == "universe_too_small"

    # 档够厚、格太薄时被 cell 闸拦下（这正是实际会发生的形态）
    n2 = 200                                  # 三档各 66，五组各 13 < 20
    res2 = double_sort_section(rng.normal(size=n2), rng.normal(size=n2),
                               rng.normal(size=n2))
    assert res2["invalid"] is True
    assert res2["reason"] == "cell_too_thin"


def test_double_sort_rejects_thin_cells():
    """档够厚但单元格 < 20 ⇒ invalid（预注册 §3.4 第二道闸）。"""
    n = 900 // 5                             # 三档各 60，五组各 12 < MIN_CELL
    rng = np.random.default_rng(11)
    mom = rng.permutation(n).astype(float)
    fx = rng.permutation(n).astype(float)
    ret = fx.copy()
    res = double_sort_section(fx, mom, ret)
    assert res["invalid"] is True
    assert res["reason"] == "cell_too_thin"


def test_double_sort_finds_monotone_signal():
    """因子与收益完全同序 ⇒ 价差 > 0 且三个动量档的单调性 ρ 全为正。"""
    n = 900
    rng = np.random.default_rng(3)
    mom = rng.permutation(n).astype(float)
    fx = rng.permutation(n).astype(float)
    ret = fx * 1e-4
    res = double_sort_section(fx, mom, ret)
    assert res["invalid"] is False
    assert res["spread"] > 0
    assert all(r > 0.9 for r in res["rhos"] if r is not None)


def test_double_sort_universe_floor():
    rng = np.random.default_rng(5)
    n = 100                                   # < MIN_UNIVERSE(150)
    res = double_sort_section(rng.normal(size=n), rng.normal(size=n),
                              rng.normal(size=n))
    assert res["invalid"] is True
    assert res["reason"] == "universe_too_small"


# ---------------------------------------------------------------------------
# 4 块自举：块长必须真的起作用
# ---------------------------------------------------------------------------

def test_block_bootstrap_ci_widens_with_block_size():
    """强自相关序列上，块长 20 的 CI 必须比块长 1 宽 —— 否则自举没生效。"""
    rng = np.random.default_rng(20261018)
    n = 114
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.85 * x[t - 1] + rng.normal(0, 0.01)
    ci1 = ci_from_means(block_bootstrap_means(x.tolist(), reps=2000, block_size=1,
                                              seed=20261018), 0.05)
    ci20 = ci_from_means(block_bootstrap_means(x.tolist(), reps=2000, block_size=20,
                                               seed=20261018), 0.05)
    assert ci1 is not None and ci20 is not None
    w1 = ci1["upper"] - ci1["lower"]
    w20 = ci20["upper"] - ci20["lower"]
    assert w20 > w1 * 1.5, f"块长 20 的 CI 宽度 {w20:.5f} 未显著宽于块长 1 的 {w1:.5f}"


# ---------------------------------------------------------------------------
# 5 闸门口径
# ---------------------------------------------------------------------------

def _rows(n_pass: int, worst: float = 0.02) -> list:
    """`n_pass` 个在容差内的因子 + (5-n_pass) 个 `worst` 的因子。

    ⚠️ 首版把 `worst` 也标成 pass=True，导致「4/5 且最差 0.02」被算成 4 个通过、
    直接判 `passed` —— 测试本身写错会掩盖闸门被放宽，故此处 `pass` 由 `abs_delta`
    与容差的关系算出，不再手写。
    """
    tol = 0.005
    rows = []
    for i in range(5):
        d = tol if i < n_pass else worst
        rows.append({"abs_delta": d, "pass": d <= tol})
    return rows


def test_gate_status_passes_on_enough_factors():
    assert gate_status(_rows(4), 4) == "passed"
    assert gate_status(_rows(5), 4) == "passed"
    assert gate_status(_rows(3), 4) == "blocked"


def test_gate_status_blocks_when_two_factors_miss():
    """3/5 即使差得再小也必须 blocked —— 判据只看「几个过」。"""
    assert gate_status(_rows(3, worst=0.006), 4) == "blocked"


def test_gate_status_has_no_softening_path():
    """闸是二值的：不存在「差异在噪声底内就放行」的第三档。

    这条守的是**判据自身**：首版真的写了 `passed_with_note`，
    而噪声底（半样本 IC 差）只能说明「差与抽样噪声不可区分」，
    完全不能说明「口径已对齐」。用弱证据软化强判据 = 把闸改成装饰。
    """
    import inspect

    # 裸名：本文件另有多处裸名导入，若这里写 `from scripts import ...`，
    # 同一物理文件会同时被 mypy 记为 `microstructure_ic` 与
    # `scripts.microstructure_ic`，直接报 "Source file found twice"。
    import microstructure_ic as mod
    src = inspect.getsource(mod.gate_status)
    # 去掉 docstring 再查：docstring 里**提到**了被删掉的第三档（说明为什么删），
    # 那不是实现，直接 grep 源码会误判。
    body = src.split('"""')[2] if src.count('"""') >= 2 else src
    assert "passed_with_note" not in body
    assert {gate_status(_rows(n), 4) for n in range(6)} == {"passed", "blocked"}


def test_gate_status_tolerance_is_the_only_measure():
    """`pass` 由调用方按 tol 判定；本函数不重算、不解释、不插值。"""
    rows = [{"abs_delta": 0.004, "pass": True}] * 4 + [{"abs_delta": 0.9, "pass": False}]
    assert gate_status(rows, 4) == "passed"


# ---------------------------------------------------------------------------
# 6 年度稳健
# ---------------------------------------------------------------------------

def test_year_stability_counts_positive_years():
    dates = [f"{y}-06-01" for y in range(2017, 2027)]
    ics = [0.01, 0.01, 0.01, 0.01, 0.01, 0.01, -0.01, -0.01, -0.01, -0.01]
    st = year_stability(dates, ics)
    assert st["n_years"] == 10
    assert st["n_positive_years"] == 6
    assert st["required"] == 6
    assert st["n_positive_years"] >= st["required"]


def test_year_stability_counts_required_as_60pct():
    dates = [f"{y}-06-01" for y in range(2017, 2026)]     # 9 年
    ics = [0.01] * 5 + [-0.01] * 4
    st = year_stability(dates, ics)
    assert st["required"] == 6          # ceil(0.6*9) = 6
    assert st["n_positive_years"] == 5


def test_h_main_is_20():
    """主持有期必须与截面间距一致（否则「非重叠」不成立、n_eff 就不成立）。"""
    assert H_MAIN == 20
