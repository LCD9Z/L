# -*- coding: utf-8 -*-
"""五因子引擎（冻结口径，与 lost/pipeline 及 v2 研究逐字一致）。

五因子方向（事前冻结，证据见 v2_factor_study.json，全部 t≥5）：

    ret20    20 日动量           方向 -1（中期反转）
    vol20    20 日波动率         方向 -1（低波动异象）
    amihud20 20 日非流动性       方向 +1（非流动性溢价）
    loga20   20 日均成交额对数   方向 -1（规模/流动性）
    maxret20 20 日最大单日涨幅   方向 -1（MAX/博彩偏好）

流动性门槛：liq20 = mean(amount,20) >= 1e8。

注意：TDX 原生 `.day` 为**不复权原始价**，ret20 会受到除权跳空污染；
本引擎如实计算，不修正，结论仅作工程验证与初步观察（见 README）。
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional

DIRECTIONS = {"ret20": -1, "vol20": -1, "amihud20": 1, "loga20": -1, "maxret20": -1}
LIQ_MIN = 100_000_000.0          # 20 日均成交额 ≥ 1 亿


def compute_factors(bars: List[Dict[str, float]]) -> Optional[Dict[str, float]]:
    """从升序 bar 列表计算五因子。数据不足或流动性不足返回 None。"""
    closes = [b["close"] for b in bars]
    amounts = [b["amount"] for b in bars]
    n = len(closes)
    if n < 22 or closes[-21] <= 0:
        return None
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, n)]
    if len(rets) < 20:
        return None
    liq20 = sum(amounts[-20:]) / 20.0
    if liq20 < LIQ_MIN:
        return None
    amihud = [abs(rets[k]) / amounts[k + 1] for k in range(len(rets))
              if amounts[k + 1] > 0]
    if len(amihud) < 20:
        return None
    return {
        "ret20": closes[-1] / closes[-21] - 1,
        "vol20": statistics.pstdev(rets[-20:]),
        "amihud20": sum(amihud[-20:]) / 20.0,
        "loga20": math.log1p(liq20),
        "maxret20": max(rets[-20:]),
        "liq20": liq20,
    }


def pct_rank(values: List[float]) -> List[float]:
    """平均秩百分位（并列取平均秩，∈ (0,1]）。"""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg / n
        i = j + 1
    return ranks


def composite_score(candidates: List[Dict[str, float]]) -> None:
    """就地给 candidates 加上 'score'（五因子方向化分位均值，越高越好）。

    正向因子取 rank_pct，反向因子取 1-rank_pct，与 H-F5 研究口径一致。
    """
    for key in DIRECTIONS:
        rk = pct_rank([c[key] for c in candidates])
        for c, r in zip(candidates, rk):
            c["rank_" + key] = r if DIRECTIONS[key] > 0 else 1.0 - r
    for c in candidates:
        c["score"] = sum(c["rank_" + key] for key in DIRECTIONS) / len(DIRECTIONS)
