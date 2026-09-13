# -*- coding: utf-8 -*-
"""横截面因子 IC 检验引擎（经济逻辑驱动，非数据挖掘）。

## 为什么用横截面 IC 而不是组合回测

本项目所用数据集存在**幸存者偏差**（不含退市股）。但关键区别在于：

- 组合回测看的是收益的**绝对水平** → 幸存者偏差直接污染（亏损样本被剔除）
- 横截面 IC 看的是**排序关系**（哪只股票比哪只涨得多）→ 幸存者偏差影响小得多

因此 IC 检验在**有偏数据上依然能给出可信的方向性结论**。这是本引擎的方法论基础。

同时使用 **Spearman 秩相关**：秩相关只看排序，天然抗离群值，
能规避"不复权价在除权日产生的假跳空"对结果的干扰。

## 检验设计

- 调仓频率：每 5 个交易日
- 前瞻收益：未来 5 个交易日（与调仓周期一致 → **无重叠**，t 检验有效）
- 每期对全池股票计算因子值，与前瞻收益求秩相关 → 得到 IC 序列
- 汇总：IC 均值、标准差、ICIR、t 统计量、p 值
- 另做分位组（Q1~Q5）平均前瞻收益，检验单调性

## 待检验假设（均先有经济逻辑，再检验）

| 编号 | 假设 | 经济逻辑 | 预期符号 |
|------|------|---------|---------|
| H1 | 短期反转 | 散户主导 + 高换手 → 短期过度反应后修正 | `ret_5` < 0 |
| H2 | 中期反转 | 同上，20 日尺度 | `ret_20` < 0 |
| H3 | 换手异象 | 卖空受限下高换手反映意见分歧与高估（Miller 1977） | `vol_ratio` < 0 |
| H4 | 低波动异象 | 投资者偏好彩票型标的，推高高波动股估值 | `vol_20` < 0 |
| H5 | MAX 效应 | 追逐极端收益（Bali-Cakici-Whitelaw） | `max_ret_20` < 0 |
| H6 | 非流动性溢价 | 流动性差的股票需更高预期收益补偿（Amihud） | `amihud_20` > 0 |
| H7 | 规模/流动性 | 小盘、低成交额股的历史溢价 | `log_amount_20` < 0 |
| H8 | 名义价格 | 低价股的散户偏好与估值偏离 | `price` 待定 |
| H9 | 突破/超买 | 逼近区间高点意味着短期超买 | `dist_high_20` > 0 为超买 |

**注意**：H1~H5 的预期符号与项目基线策略的构造**方向相反** ——
基线给"上涨/突破/高换手"加分。本检验将直接说明该方向是否站得住。
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 因子名 → 中文说明
FACTOR_LABELS = {
    "ret_1": "1日收益（极短期反转）",
    "ret_5": "5日收益（短期动量/反转）",
    "ret_20": "20日收益（中期动量/反转）",
    "vol_20": "20日波动率",
    "amihud_20": "20日 Amihud 非流动性",
    "log_amount_20": "20日均成交额(对数)",
    "vol_ratio": "量能放大(5日/20日)",
    "max_ret_20": "20日最大单日涨幅",
    "dist_high_20": "距20日高点(≤0，越接近0越超买)",
    "price": "收盘价(名义价格)",
}

# 先验预期方向：+1 表示预期 IC>0，-1 表示预期 IC<0，0 表示待定
PRIOR_SIGN = {
    "ret_1": -1, "ret_5": -1, "ret_20": -1,
    "vol_20": -1, "max_ret_20": -1, "vol_ratio": -1,
    "amihud_20": +1, "log_amount_20": -1,
    "dist_high_20": +1, "price": 0,
}

MIN_HISTORY = 25          # 计算 20 日因子所需的最少历史
DEFAULT_HORIZON = 5       # 前瞻收益天数
DEFAULT_STEP = 5          # 调仓间隔（与 horizon 一致 → 无重叠）


# ---------------------------------------------------------------------------
# 因子计算
# ---------------------------------------------------------------------------

def _closes(bars: Sequence[Dict[str, Any]]) -> List[float]:
    return [float(b["close"]) for b in bars]


def compute_factors(bars: Sequence[Dict[str, Any]], i: int) -> Optional[Dict[str, float]]:
    """在第 i 根 K 线上计算全部因子。历史不足返回 None。

    所有因子**只使用第 i 根及之前的数据**，不使用未来信息。
    """
    if i < MIN_HISTORY:
        return None
    win = bars[i - 20:i + 1]
    cl = _closes(win)
    if len(cl) < 21 or any(c <= 0 for c in cl):
        return None
    amts = [float(b.get("amount") or 0) for b in win]
    vols = [float(b.get("volume") or 0) for b in win]

    rets = [cl[k] / cl[k - 1] - 1 for k in range(1, len(cl))]
    if any(not math.isfinite(r) for r in rets):
        return None

    f: Dict[str, float] = {}
    f["ret_1"] = cl[-1] / cl[-2] - 1
    f["ret_5"] = cl[-1] / cl[-6] - 1
    f["ret_20"] = cl[-1] / cl[-21] - 1
    f["vol_20"] = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    f["max_ret_20"] = max(rets) if rets else 0.0
    f["price"] = cl[-1]

    avg_amt = sum(amts) / len(amts)
    f["log_amount_20"] = math.log(avg_amt) if avg_amt > 0 else float("nan")

    # Amihud 非流动性：|收益| / 成交额，取均值后放大 1e8 便于读数
    amihud = [abs(rets[k]) / amts[k + 1] for k in range(len(rets)) if amts[k + 1] > 0]
    f["amihud_20"] = (sum(amihud) / len(amihud) * 1e8) if amihud else float("nan")

    v5 = sum(vols[-5:]) / 5
    v20 = sum(vols) / len(vols)
    f["vol_ratio"] = (v5 / v20) if v20 > 0 else float("nan")

    highs = [float(b["high"]) for b in win]
    peak = max(highs)
    f["dist_high_20"] = (cl[-1] / peak - 1) if peak > 0 else float("nan")

    if any(not math.isfinite(v) for v in f.values()):
        return None
    return f


def forward_return(bars: Sequence[Dict[str, Any]], i: int, horizon: int) -> Optional[float]:
    """第 i 根之后 horizon 个交易日的收盘价收益。数据不足返回 None。"""
    j = i + horizon
    if j >= len(bars):
        return None
    c0, c1 = float(bars[i]["close"]), float(bars[j]["close"])
    if c0 <= 0:
        return None
    return c1 / c0 - 1


# ---------------------------------------------------------------------------
# 统计工具
# ---------------------------------------------------------------------------

def _rank(values: Sequence[float]) -> List[float]:
    """平均秩（处理并列）。"""
    order = sorted(range(len(values)), key=lambda k: values[k])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Spearman 秩相关系数。样本过少或方差为 0 时返回 None。"""
    n = len(xs)
    if n < 5 or n != len(ys):
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[k] - mx) * (ry[k] - my) for k in range(n))
    dx = math.sqrt(sum((r - mx) ** 2 for r in rx))
    dy = math.sqrt(sum((r - my) ** 2 for r in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _t_pvalue(t: float, df: int) -> Optional[float]:
    """双尾 p 值。无 scipy 依赖：用正态近似（样本量足够时误差可忽略）。"""
    if df <= 0:
        return None
    # 正态近似
    z = abs(t)
    return math.erfc(z / math.sqrt(2))


def _winsorize(vals: List[float], lo: float = 0.01, hi: float = 0.99) -> List[float]:
    if len(vals) < 20:
        return vals
    s = sorted(vals)
    a = s[int(lo * (len(s) - 1))]
    b = s[int(hi * (len(s) - 1))]
    return [min(max(v, a), b) for v in vals]


# ---------------------------------------------------------------------------
# 主检验
# ---------------------------------------------------------------------------

def build_panel(data: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """全池共同的交易日序列（升序）。"""
    dates: set = set()
    for bars in data.values():
        dates.update(str(b["date"]) for b in bars if b.get("date"))
    return sorted(dates)


def run_ic_study(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    horizon: int = DEFAULT_HORIZON,
    step: int = DEFAULT_STEP,
    min_cross_section: int = 50,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """在给定股票池上做横截面 IC 检验。

    返回 {factor: {ic_mean, ic_std, icir, t, p, n_periods, quintiles, prior_sign, hit}}
    """
    # 预建每只股票的日期索引
    idx_map: Dict[str, Dict[str, int]] = {}
    for code, bars in data.items():
        idx_map[code] = {str(b["date"]): k for k, b in enumerate(bars)}

    panel = build_panel(data)
    if start:
        panel = [d for d in panel if d >= start]
    if end:
        panel = [d for d in panel if d <= end]

    # 每期收集 (factor, fwd_ret) 对
    series: Dict[str, List[float]] = {k: [] for k in FACTOR_LABELS}
    fwd_series: List[float] = []
    period_sizes: List[int] = []

    # 调仓日：每 step 个交易日一次
    rebal = panel[MIN_HISTORY::step]
    for day in rebal:
        f_vals: Dict[str, List[float]] = {k: [] for k in FACTOR_LABELS}
        y_vals: List[float] = []
        for code, bars in data.items():
            i = idx_map[code].get(day)
            if i is None:
                continue
            fac = compute_factors(bars, i)
            if fac is None:
                continue
            fr = forward_return(bars, i, horizon)
            if fr is None:
                continue
            for k in FACTOR_LABELS:
                f_vals[k].append(fac[k])
            y_vals.append(fr)
        if len(y_vals) < min_cross_section:
            continue
        period_sizes.append(len(y_vals))
        for k in FACTOR_LABELS:
            ic = spearman(f_vals[k], y_vals)
            if ic is not None:
                series[k].append(ic)
        fwd_series.append(sum(y_vals) / len(y_vals))

    out: Dict[str, Any] = {}
    for k, ics in series.items():
        if len(ics) < 10:
            out[k] = {"error": "insufficient_periods", "n_periods": len(ics)}
            continue
        m = sum(ics) / len(ics)
        sd = statistics.pstdev(ics) if len(ics) > 1 else 0.0
        icir = (m / sd) if sd > 0 else 0.0
        t = icir * math.sqrt(len(ics))
        out[k] = {
            "ic_mean": m, "ic_std": sd, "icir": icir,
            "t": t, "p": _t_pvalue(t, len(ics) - 1),
            "n_periods": len(ics),
            "positive_rate": sum(1 for x in ics if x > 0) / len(ics),
            "prior_sign": PRIOR_SIGN.get(k, 0),
            "label": FACTOR_LABELS.get(k, k),
        }

    return {
        "factors": out,
        "n_rebalance_dates": len(period_sizes),
        "avg_cross_section": (sum(period_sizes) / len(period_sizes)) if period_sizes else 0,
        "mean_universe_forward_return": (sum(fwd_series) / len(fwd_series)) if fwd_series else 0.0,
        "horizon": horizon, "step": step,
    }


def quintile_returns(
    data: Dict[str, List[Dict[str, Any]]],
    factor: str,
    *,
    horizon: int = DEFAULT_HORIZON,
    step: int = DEFAULT_STEP,
    min_cross_section: int = 50,
    n_groups: int = 5,
) -> Optional[Dict[str, Any]]:
    """分位组平均前瞻收益（Q1=因子值最低，Q5=最高）。

    使用均值收益（非秩），因此对离群值敏感 —— 已做 1%/99% 缩尾。
    """
    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    panel = build_panel(data)
    rebal = panel[MIN_HISTORY::step]

    group_rets: List[List[float]] = [[] for _ in range(n_groups)]
    for day in rebal:
        pairs: List[Tuple[float, float]] = []
        for code, bars in data.items():
            i = idx_map[code].get(day)
            if i is None:
                continue
            fac = compute_factors(bars, i)
            if fac is None:
                continue
            fr = forward_return(bars, i, horizon)
            if fr is None:
                continue
            pairs.append((fac[factor], fr))
        if len(pairs) < min_cross_section:
            continue
        pairs.sort(key=lambda t: t[0])
        rets = _winsorize([p[1] for p in pairs])
        n = len(pairs)
        for g in range(n_groups):
            lo = g * n // n_groups
            hi = (g + 1) * n // n_groups
            if hi > lo:
                group_rets[g].append(sum(rets[lo:hi]) / (hi - lo))

    if not group_rets[0]:
        return None
    means = [sum(g) / len(g) for g in group_rets]
    return {
        "factor": factor,
        "group_mean_returns": means,
        "long_short_pct": (means[-1] - means[0]) * 100,
        "monotonic": _is_monotonic(means),
        "n_periods": len(group_rets[0]),
    }


def _is_monotonic(vals: Sequence[float]) -> bool:
    inc = all(vals[k] <= vals[k + 1] for k in range(len(vals) - 1))
    dec = all(vals[k] >= vals[k + 1] for k in range(len(vals) - 1))
    return inc or dec
