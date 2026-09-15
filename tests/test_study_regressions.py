# -*- coding: utf-8 -*-
"""两个「静默失效」类缺陷的回归测试。

本项目的红线之一是**不许自欺**：最危险的缺陷不是崩溃，而是
「看起来正常、实际错误」的静默失效。以下两例都属此类，且都已实际发生。

## 缺陷一：等距抽样在旋转下不变（`run_sampling_sensitivity_study`）

原实现用「等距抽样 + 偏移量」：

```python
rotated = codes[offset:] + codes[:offset]
step = len(rotated) / size
return [rotated[int(i * step)] for i in range(size)]
```

当 ``len/size`` 与偏移量成整数倍关系时（1000 只抽 300 只、偏移 200/400/600/800），
抽样网格在旋转下**不变** → 5 个子样本完全相同（对称差恒为 0）。

**后果**：脚本正常跑完，输出「标准差 = 0，离散度完美」—— 一个完全错误
但看起来很漂亮的结论。改用带种子的确定性洗牌后修复。

## 缺陷二：硬编码窗口（`run_tail_exclusion_study`）

成本拖累对照把 `"2024-01-02"` 硬编码进 `next(...)`，当 `--windows` 不含该日期时
抛 `StopIteration`，使整个研究在**最后一步**崩溃 —— 前面几十分钟的计算全部作废。
"""
from __future__ import annotations

import pytest
from run_sampling_sensitivity_study import _take_sample
from run_tail_exclusion_study import _cost_drag_window

#: 复现缺陷一的病态配置：1000 只池、抽 300 只
POOL_SIZE = 1000
SAMPLE_SIZE = 300
#: `run_sampling_sensitivity_study` 的 `--seed-base` 默认值
SEED_BASE = 1000
#: 该研究的 `--n-samples` 默认值
N_SAMPLES = 5


def _pool() -> list[str]:
    return [f"{i:06d}" for i in range(POOL_SIZE)]


def _old_equidistant_sample(codes: list[str], size: int, offset: int) -> set[str]:
    """**已废弃的错误实现**，仅为在测试中复现失效模式而保留。

    这不是可用的抽样函数 —— 保留它是为了让下面的断言能证明
    「若有人改回等距抽样，本测试会失败」。
    """
    rotated = codes[offset:] + codes[:offset]
    step = len(rotated) / size
    return {rotated[int(i * step)] for i in range(size)}


# ---------------------------------------------------------------------------
# 缺陷一
# ---------------------------------------------------------------------------

def test_equidistant_rotation_collapses_subsets_reproducing_the_defect():
    """复现缺陷：等距抽样 + 偏移量在病态比例下产出**完全相同**的子样本。

    这条同时是「上面那条断言不是空转」的证明 —— 若把当前实现换回等距抽样，
    该实现会立刻在这里被抓住。
    """
    codes = _pool()
    step_offset = POOL_SIZE // N_SAMPLES  # 1000 / 5 = 200
    subsets = [
        _old_equidistant_sample(codes, SAMPLE_SIZE, s * step_offset)
        for s in range(N_SAMPLES)
    ]

    assert all(len(s) == SAMPLE_SIZE for s in subsets), "样本大小应正确（缺陷不影响大小）"
    assert all(s == subsets[0] for s in subsets), (
        "未能复现缺陷 —— 若此断言失败，说明该失效模式的前提已变化，"
        "需重新评估下方守卫是否仍然必要"
    )
    # 对称差全为 0 = 五个"独立"子样本其实是同一批股票
    assert all(len(subsets[i] ^ subsets[j]) == 0
               for i in range(N_SAMPLES) for j in range(i + 1, N_SAMPLES))


def test_take_sample_yields_genuinely_independent_subsets():
    """当前实现必须在同一病态配置下给出**真正不同**的子样本。"""
    codes = _pool()
    subsets = [
        set(_take_sample(codes, SAMPLE_SIZE, SEED_BASE + s))
        for s in range(N_SAMPLES)
    ]

    assert all(len(s) == SAMPLE_SIZE for s in subsets)

    for i in range(N_SAMPLES):
        for j in range(i + 1, N_SAMPLES):
            sym_diff = len(subsets[i] ^ subsets[j])
            # 两个 size=300 的集合，对称差 >= 150 意味着重合约 <= 50% ——
            # 实测约 400（重合 ~89/300），余量充足
            assert sym_diff >= SAMPLE_SIZE // 2, (
                f"子样本 {i}/{j} 过于相似（对称差 {sym_diff}）—— "
                "抽样可能退化回等距旋转，离散度将被系统性低估"
            )


def test_take_sample_is_deterministic_and_handles_oversized_request():
    """同种子必须可复现；请求数 >= 池大小时返回整个池（不截断、不报错）。"""
    codes = _pool()

    assert _take_sample(codes, SAMPLE_SIZE, 42) == _take_sample(codes, SAMPLE_SIZE, 42)
    assert _take_sample(codes, SAMPLE_SIZE, 42) != _take_sample(codes, SAMPLE_SIZE, 43)

    assert sorted(_take_sample(codes, POOL_SIZE, 7)) == sorted(codes)
    assert sorted(_take_sample(codes, POOL_SIZE + 10, 7)) == sorted(codes)


# ---------------------------------------------------------------------------
# 缺陷二
# ---------------------------------------------------------------------------

def test_cost_drag_window_follows_the_windows_argument():
    """成本拖累窗口必须来自 `--windows` 实参，而非硬编码日期。

    原实现在此对「不含 2024-01-02 的窗口列表」抛 StopIteration。
    """
    assert _cost_drag_window(["2023-07-03"]) == "2023-07-03"
    assert _cost_drag_window(["2023-07-03", "2024-07-01"]) == "2023-07-03"
    assert _cost_drag_window(["2025-01-02"]) == "2025-01-02"
    # 不含默认窗口的列表同样必须可用 —— 这正是原缺陷的触发条件
    assert _cost_drag_window(["2026-01-05"]) == "2026-01-05"


def test_cost_drag_window_rejects_empty_windows():
    """空窗口列表须显式报错，而不是以 IndexError 的形式在下游冒出。"""
    with pytest.raises(ValueError, match="windows"):
        _cost_drag_window([])
