# -*- coding: utf-8 -*-
r"""统计行业：用收益相关性聚类生成 **PIT-clean** 的「伪行业」标签。

## 为什么需要

2026-09-30 专家圆桌审查中，**产业策略师**指出项目的最大悖论：

> 「10 个价量因子 IC 强显著（\|t\| 2~10），组合层却全线不赚钱。读法是
> **反转/波动类因子在不同景气度行业里方向相反** —— 景气上行行业里「高波动」是趋势延续，
> 景气下行行业里「高波动」是出逃踩踏。把全市场池在一起算 IC，得到的是**正负相抵后的残渣**。」

而项目此前因「**无 PIT 行业数据**」**放弃了行业中性化**。产业策略师给出的解法：

> 「**「景气度/产业趋势排序」不需要官方行业分类** —— 用 v3 已有的价格面板做
> **收益相关性聚类**生成「统计行业」标签，**纯价格派生、零新数据源、PIT-clean**，
> 正好绕开死结。」

## ⚠️ 口径声明（必须随结论一起说）

**统计行业 ≠ 官方行业。** 它是**收益共动性**的聚类结果，可能把
「同属一个产业链但不同官方行业」的股票聚在一起，也可能把同一官方行业内
相关性低的两半拆开。所有基于它的结论**必须标注该限制**。

## PIT 保证

每个重聚类时点 `T` 只用 **`[T-lookback, T)`** 的收益（**不含 T 当日**）；
标签从 `T` 生效到下一个重聚类时点。**无前视。**

## ⚠️ 关键：必须**先剔除市场因子**再聚类

A 股个股普遍与市场高相关（0.5~0.7），直接对**原始收益**聚类会**链式坍缩**成
1~2 个巨簇（实测：193 只聚成 ``[116, 47, 6, 5, 4, ...]`` —— 两簇吃掉 **84%**），
「统计行业」退化成「大盘 vs 非大盘」，**失去区分力**。

做法：逐日减去**当日截面均值收益**（等权市场的代理），聚类用的是**残差**。

## 算法

贪心凝聚聚类（agglomerative）：
1. 每个股票自成一簇；
2. 反复合并**平均相关性最高**的一对簇，直到剩 ``n_clusters`` 个；
3. 簇编号按「成员数降序 + 首成员代码」稳定排序（保证可复现）。

选它而非 k-means：**不需要预设距离度量与迭代次数**，且对 A 股这种
「少数强共动板块 + 大量噪声」的结构更稳。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_LOOKBACK = 120          # 收益窗口（交易日）
DEFAULT_RECLUSTER_EVERY = 60    # 重聚类间隔（交易日）
DEFAULT_N_CLUSTERS = 20         # 目标簇数
MIN_OBS = 60                    # 低于该观测数的股票不参与聚类


def _returns(closes: Sequence[float]) -> List[float]:
    out: List[float] = []
    for i in range(1, len(closes)):
        a, b = closes[i - 1], closes[i]
        out.append(b / a - 1.0 if a > 0 else 0.0)
    return out


def _corr(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """皮尔逊相关。任一序列方差为 0 或长度不足返回 ``None``。"""
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    sxx = sum((xs[i] - mx) ** 2 for i in range(n))
    syy = sum((ys[i] - my) ** 2 for i in range(n))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _cluster(
    codes: List[str],
    corr: Dict[Tuple[str, str], float],
    n_clusters: int,
) -> Dict[str, int]:
    """贪心凝聚聚类：反复合并平均相关最高的两簇。"""
    if not codes:
        return {}
    k = max(1, min(n_clusters, len(codes)))
    clusters: List[List[str]] = [[c] for c in codes]

    def pair_corr(a: List[str], b: List[str]) -> float:
        tot = 0.0
        cnt = 0
        for x in a:
            for y in b:
                v = corr.get((min(x, y), max(x, y)))
                if v is not None:
                    tot += v
                    cnt += 1
        return tot / cnt if cnt else -2.0

    while len(clusters) > k:
        best_c = -2.0
        best_i = 0
        best_j = 1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                c = pair_corr(clusters[i], clusters[j])
                if c > best_c:
                    best_c, best_i, best_j = c, i, j
        clusters[best_i] = clusters[best_i] + clusters[best_j]
        clusters.pop(best_j)

    # 稳定编号：成员数降序 + 首成员代码升序（可复现）
    clusters.sort(key=lambda m: (-len(m), min(m)))
    # ⚠️ 循环变量不得复用 `c` —— 它在上面已被绑为 float（best_c 系列），
    # mypy 的流分析会因此把 `out[c]` 的键推成 float，报 invalid index。
    out: Dict[str, int] = {}
    for idx, members in enumerate(clusters):
        for member_code in members:
            out[member_code] = idx
    return out


def build_statistical_industry(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    lookback: int = DEFAULT_LOOKBACK,
    recluster_every: int = DEFAULT_RECLUSTER_EVERY,
    n_clusters: int = DEFAULT_N_CLUSTERS,
    min_obs: int = MIN_OBS,
) -> Dict[str, Dict[str, int]]:
    r"""生成逐日的统计行业标签。

    :param data: ``{code: [bar, ...]}``，bar 需含 ``date`` / ``close``。
    :return: ``{day: {code: cluster_id}}`` —— 该日生效的标签。
        无标签的股票**不在 dict 里**（缺失即缺失，不猜）。

    **PIT**：重聚类时点 ``T`` 的窗口为 ``[T-lookback, T)``，**不含 T 当日**。
    """
    # 主日历（全池日期的并集，升序）
    all_days: set = set()
    for bars in data.values():
        all_days.update(str(b["date"]) for b in bars if b.get("date"))
    days = sorted(all_days)
    if not days:
        return {}

    # 每个 code 的 close 序列 + 日期索引
    close_by: Dict[str, Dict[str, float]] = {}
    for code, bars in data.items():
        close_by[code] = {str(b["date"]): float(b["close"])
                          for b in bars if b.get("date") and b.get("close") is not None}

    out: Dict[str, Dict[str, int]] = {}
    current: Dict[str, int] = {}

    for di, day in enumerate(days):
        if di % recluster_every == 0 and di >= lookback:
            window = days[di - lookback:di]        # 不含当日 → PIT
            raw: Dict[str, List[float]] = {}
            for code, cm in close_by.items():
                closes = [cm[d] for d in window if d in cm]
                if len(closes) >= min_obs:
                    raw[code] = _returns(closes)

            # ⚠️ 关键：**先剔除市场因子再聚类**。
            # A 股个股普遍与市场高相关（0.5~0.7），直接对原始收益聚类会**链式坍缩**
            # 成 1~2 个巨簇（实测：193 只聚成 [116, 47, 6, 5, ...] —— 两簇吃掉 84%），
            # 「统计行业」就退化成「大盘 vs 非大盘」，失去区分力。
            # 做法：逐日减去**当日截面均值收益**（等权市场的代理），聚类用的是**残差**。
            series: Dict[str, List[float]] = {}
            n_obs = min((len(v) for v in raw.values()), default=0)
            if n_obs >= min_obs:
                means = [0.0] * n_obs
                for v in raw.values():
                    tail = v[-n_obs:]
                    for t in range(n_obs):
                        means[t] += tail[t]
                cnt = len(raw)
                means = [m / cnt for m in means]
                for code, v in raw.items():
                    tail = v[-n_obs:]
                    series[code] = [tail[t] - means[t] for t in range(n_obs)]
            codes = sorted(series)
            corr: Dict[Tuple[str, str], float] = {}
            for i in range(len(codes)):
                for j in range(i + 1, len(codes)):
                    c = _corr(series[codes[i]], series[codes[j]])
                    if c is not None:
                        corr[(codes[i], codes[j])] = c
            current = _cluster(codes, corr, n_clusters)
        if current:
            out[day] = dict(current)

    return out


def load_closes(dataset_dir: str, *, max_stocks: int = 0,
                min_rows: int = 200) -> Dict[str, List[Dict[str, Any]]]:
    """加载聚类所需的最小面板（date / close）。"""
    import csv as _csv
    import os

    stock_dir = os.path.join(dataset_dir, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                   if f.endswith(".csv") and f[:-4].isdigit())
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]

    out: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        if not os.path.exists(p):
            continue
        rows: List[Dict[str, Any]] = []
        try:
            with open(p, encoding="utf-8", newline="") as fh:
                for r in _csv.DictReader(fh):
                    rows.append({"date": r.get("date"), "close": r.get("close")})
        except OSError:
            continue
        if len(rows) >= min_rows:
            out[c] = rows
    return out
