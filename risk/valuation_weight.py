# -*- coding: utf-8 -*-
r"""估值分档 → 仓位权重调节器（把 `pb`/`pe_ttm` 从「排序因子」升级为「权重」）。

## 为什么做这个

2026-09-30 专家圆桌审查中，**估值分析师**指出：

> 「系统**只称 PE 的分子，从没算过分母** —— 它排序的是动量/波动/规模（PE 那一侧），
> 从不计算盈利（EPS 那一侧）。」

并给出处方（原文）：

> 「**最该补的不是「再加一个因子」，而是把 `pb`/`pe_ttm` 从「排序因子」升级成
> 「仓位权重调节器」** —— 同样的信号，估值在下轨的给高权重、在上轨的给低权重甚至不建仓。」

**为什么这条路比"再加因子"更可能有效**：`pb`/`pe_ttm` 是项目**仅有的两个通过
BH+Bonferroni 双校正**的因子，且**与三个价量维度低相关** → 提供一路**正交**的权重来源。

## 与既有机制的差异（关键）

| | `candidate_filter` | `position_scaler` | **`weight_func`（本模块）** |
|---|---|---|---|
| 粒度 | 逐股 | 逐日 | **逐股** |
| 语义 | 买/不买 | 整体买多少 | **个股买多少（相对权重）** |
| 用途 | 排除风险特征 | 降敞口 | **把估值当权重** |

## 事前登记（跑前固定，不得依据结果调整）

| 项 | 设定 |
|----|------|
| 估值指标 | `pe_ttm`（主）—— 项目双校正因子之一 |
| 分档 | 按**当日候选池内横截面分位**：下轨 `<0.33` / 中 `0.33~0.67` / 上轨 `>0.67` |
| 权重 | 下轨 **1.5** / 中 **1.0** / 上轨 **0.5** |
| 缺失 | **1.0（不干预）** —— 与 `market_risk_gate` 的「缺失即不干预」一致 |
| PIT | 用 `PitFundamentals.factors_as_of(code, day, price)`，价格取**当日收盘** |

## 性能

`weight_func` 在回测热路径**逐股逐日**调用 → 本模块**预计算查表**，
返回的函数只做 dict 查找，**零 I/O、零计算**。
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from data_contracts import to_float_or_none as _num  # noqa: F401 — 唯一标准实现（CODE_REDUNDANCY_AUDIT P1）

# ---- 事前固定的分档与权重 ----
LOW_PCT = 0.33
HIGH_PCT = 0.67
W_LOW = 1.5      # 估值下轨 → 高权重
W_MID = 1.0
W_HIGH = 0.5     # 估值上轨 → 低权重
DEFAULT_METRIC = "pe_ttm"


def build_valuation_weight(
    dataset_dir: str,
    data: Dict[str, List[Dict[str, Any]]],
    *,
    metric: str = DEFAULT_METRIC,
    rebalance_days: Optional[Sequence[str]] = None,
    min_cross_section: int = 20,
) -> Tuple[Callable[[str, List[Dict[str, Any]], str], float], Dict[str, Any]]:
    r"""预计算逐（日，股）估值权重。

    :param dataset_dir: v3 数据集目录（需含 ``fundamentals.jsonl`` / ``disclosure_dates.jsonl``）
    :param data: ``{code: bars}``，bar 需含 ``date`` / ``close``（用于算 PE 的分子）
    :param metric: ``"pe_ttm"`` 或 ``"pb"``
    :param rebalance_days: 需要权重的交易日；``None`` = 全部（**慢**，建议传调仓日）
    :param min_cross_section: 当日有效估值数低于此值 → **不做分档**（缺失即不干预）

    :return: ``(weight_func, stats)``；``weight_func(code, hist, day) -> float``。
    """
    from pit.pit_fundamentals import PitFundamentals, load_disclosures, load_records

    fp = os.path.join(dataset_dir, "fundamentals.jsonl")
    dp = os.path.join(dataset_dir, "disclosure_dates.jsonl")
    records = load_records(fp)
    disclosures = load_disclosures(dp) if os.path.exists(dp) else {}
    pit = PitFundamentals(records, disclosures)

    close_by: Dict[str, Dict[str, float]] = {
        c: {str(b["date"]): float(b["close"])
            for b in bars if b.get("date") and b.get("close") is not None}
        for c, bars in data.items()
    }
    if rebalance_days is None:
        all_days: set = set()
        for m in close_by.values():
            all_days.update(m)
        days: List[str] = sorted(all_days)
    else:
        days = [str(d) for d in rebalance_days]

    table: Dict[str, Dict[str, float]] = {}
    n_low = n_mid = n_high = 0
    for day in days:
        vals: List[Tuple[str, float]] = []
        for code, cm in close_by.items():
            px = cm.get(day)
            if px is None or px <= 0:
                continue
            f = pit.factors_as_of(code, day, price=px)
            v = _num(f.get(metric))
            if v is not None and v > 0:
                vals.append((code, v))
        if len(vals) < min_cross_section:
            continue
        vals.sort(key=lambda t: t[1])
        n = len(vals)
        lo_cut = int(n * LOW_PCT)
        hi_cut = int(n * HIGH_PCT)
        day_w: Dict[str, float] = {}
        for idx, (code, _v) in enumerate(vals):
            if idx < lo_cut:
                day_w[code] = W_LOW
                n_low += 1
            elif idx >= hi_cut:
                day_w[code] = W_HIGH
                n_high += 1
            else:
                day_w[code] = W_MID
                n_mid += 1
        table[day] = day_w

    def weight_func(code: str, hist: List[Dict[str, Any]], day: str) -> float:
        # 热路径：只做查表。缺权重 → 1.0（不干预，不猜）
        return table.get(str(day), {}).get(code, W_MID)

    stats = {
        "metric": metric,
        "days_covered": len(table),
        "n_low": n_low, "n_mid": n_mid, "n_high": n_high,
        "weights": {"low": W_LOW, "mid": W_MID, "high": W_HIGH},
        "cut_points": {"low_pct": LOW_PCT, "high_pct": HIGH_PCT},
        "coverage": (pit.coverage(sorted(data), days[-1]) if days else None),
    }
    return weight_func, stats
