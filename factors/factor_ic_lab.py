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


# ---------------------------------------------------------------------------
# 逐期横截面面板（IC 检验与正交化的共同输入）
# ---------------------------------------------------------------------------

def build_factor_panel(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    horizon: int = DEFAULT_HORIZON,
    step: int = DEFAULT_STEP,
    min_cross_section: int = 50,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """把行情数据整理成**逐期横截面因子面板**。

    每个期间记录同一批股票的 10 个因子值与前瞻收益，三者**逐元素对齐**
    （第 j 个元素属于同一只股票）——这是按截面做回归/正交化的前提。

    返回::

        {"periods": [{"date": str,
                      "factors": {factor: [值, ...]},
                      "forward": [前瞻收益, ...]}, ...],
         "panel_len": 全池交易日数,
         "factor_names": [...],
         "horizon": int, "step": int}
    """
    idx_map: Dict[str, Dict[str, int]] = {}
    for code, bars in data.items():
        idx_map[code] = {str(b["date"]): k for k, b in enumerate(bars)}

    panel = build_panel(data)
    if start:
        panel = [d for d in panel if d >= start]
    if end:
        panel = [d for d in panel if d <= end]

    periods: List[Dict[str, Any]] = []
    for day in panel[MIN_HISTORY::step]:
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
        periods.append({"date": day, "factors": f_vals, "forward": y_vals})

    return {
        "periods": periods,
        "panel_len": len(panel),
        "factor_names": list(FACTOR_LABELS),
        "horizon": horizon,
        "step": step,
    }


def panel_ic_series(panel: Dict[str, Any]) -> Dict[str, List[float]]:
    """从面板计算逐期 IC 序列（每个因子一条）。"""
    series: Dict[str, List[float]] = {k: [] for k in FACTOR_LABELS}
    for p in panel.get("periods", []):
        y = p["forward"]
        for k in series:
            vals = p["factors"].get(k)
            if not vals:
                continue
            ic = spearman(vals, y)
            if ic is not None:
                series[k].append(ic)
    return series


def _summarize_ic(series: Dict[str, List[float]]) -> Dict[str, Any]:
    """把逐期 IC 序列汇总为统计量（`run_ic_study` 的后半段，独立以便复用）。"""
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
    return out


def _study_from_panel(panel: Dict[str, Any], horizon: int, step: int) -> Dict[str, Any]:
    """面板 → IC 检验结果（与 `run_ic_study` 同结构）。"""
    series = panel_ic_series(panel)
    periods = panel.get("periods", [])
    sizes = [len(p["forward"]) for p in periods]
    fwd_series = [sum(p["forward"]) / len(p["forward"]) for p in periods]
    return {
        "factors": _summarize_ic(series),
        "n_rebalance_dates": len(sizes),
        "avg_cross_section": (sum(sizes) / len(sizes)) if sizes else 0,
        "mean_universe_forward_return": (sum(fwd_series) / len(fwd_series)) if fwd_series else 0.0,
        "horizon": horizon, "step": step,
    }


# ---------------------------------------------------------------------------
# 因子正交化（2026-09-19 新增）
#
# 动机：实测五因子的横截面秩相关中，`amihud_20 ~ log_amount_20` 达 **-0.869**
# （100% 截面 |r|>0.5）、`vol_20 ~ max_ret_20` 达 **+0.843**（99.8%）。
# 五因子等权合成因此**重复计票**：真实权重是 1:2:2 而非 1:1:1:1:1，
# 组合被隐性推向小市值+高非流动性。
# 详见 ALPHA_CAPABILITY_GAP_ANALYSIS.md §3.2。
#
# ## 为什么不用「每个因子对其余全部因子回归」的对称残差化
#
# 该做法看似"对称、无需定序"，但对两个标准化变量可解析地看出它**不减少冗余**：
# 设 corr(a,b)=ρ，则 a_resid=a-ρb、b_resid=b-ρa，于是
#
#     corr(a_resid, b_resid) = (ρ³-ρ)/(1-ρ²) = **-ρ**
#
# 即相关**幅度不变、符号翻转**。用它"正交化"只是把冗余换了个方向，
# 反而会让等权合成变成"一半因子正着算、一半反着算"。
# 故本模块**不提供**该方法，只提供下面两种真正能消除冗余的：
#
#   * `sequential` —— 顺序残差化（Gram-Schmidt）。真正正交，但**依赖顺序**；
#     顺序必须**事前声明**并写进结论，不得按 IC 结果调整。
#   * `lowdin`     —— Löwdin 对称正交化 ``Z(Z'Z)^{-1/2}``。**与顺序无关**，
#     且在"最小改动原向量"的意义下唯一；代价是因子高度共线时矩阵病态。
# ---------------------------------------------------------------------------

# 五因子复合打分所用因子（与 scripts/run_daily_factor_screen.py 一致）
COMPOSITE_FACTORS = ["ret_20", "vol_20", "amihud_20", "log_amount_20", "max_ret_20"]

# 顺序残差化的**事前声明顺序**（经济逻辑，非按结果挑选）：
#   价格路径一阶特征 → 二阶矩 → 极端值统计 → 规模/流动性 → 由其派生的冲击成本。
# 越靠前的因子"保留"越多的公共方差；靠后的因子只留增量信息。
ORTHO_ORDER_DEFAULT = ["ret_20", "vol_20", "max_ret_20", "log_amount_20", "amihud_20"]


def _rank_standardize(vals: Sequence[float]) -> Optional[List[float]]:
    """平均秩 → 标准化（均值 0、标准差 1）。

    用秩而非原值：抗离群，且与 IC 的 Spearman 口径一致。
    样本 < 3 或序列为常数（标准差 0）时返回 ``None``（不编造）。
    """
    n = len(vals)
    if n < 3:
        return None
    order = sorted(range(n), key=lambda k: vals[k])
    rk = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rk[order[k]] = avg
        i = j + 1
    mean = sum(rk) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rk) / n)
    if sd <= 0:
        return None
    return [(r - mean) / sd for r in rk]


def _gram(cols: Sequence[Sequence[float]], n: int) -> List[List[float]]:
    """标准化列的 Gram 矩阵 ``Z'Z / n``（即相关矩阵，对角线应为 1）。

    先算它再在 k×k 空间里做正交化：残差是原列的线性组合，
    系数只由 Gram 矩阵决定 —— 于是每期只需 O(n·k²) 而非 O(n·k³)。
    """
    k = len(cols)
    s = [[0.0] * k for _ in range(k)]
    for a in range(k):
        ca = cols[a]
        for b in range(a, k):
            cb = cols[b]
            v = 0.0
            for t in range(n):
                v += ca[t] * cb[t]
            v /= n
            s[a][b] = v
            s[b][a] = v
    return s


def _materialize(coefs: Sequence[float], cols: Sequence[Sequence[float]],
                 n: int) -> List[float]:
    """把系数向量作用到原标准化列上，得到实际因子值。"""
    out = [0.0] * n
    for a, c in enumerate(coefs):
        if c == 0.0:
            continue
        ca = cols[a]
        for t in range(n):
            out[t] += c * ca[t]
    return out


def _jacobi_eigen(a: List[List[float]], max_sweeps: int = 100,
                  tol: float = 1e-14) -> Tuple[List[float], List[List[float]]]:
    """对称矩阵特征分解（循环 Jacobi 旋转）。

    返回 ``(特征值, 特征向量矩阵 V)``，``V`` 的第 j 列是第 j 个特征向量。
    仅用于 k 很小的相关矩阵（k <= 10），不追求大规模效率。
    """
    n = len(a)
    m = [row[:] for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off = math.sqrt(sum(m[i][j] ** 2 for i in range(n) for j in range(i + 1, n)))
        if off < tol:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(m[p][q]) < 1e-18:
                    continue
                theta = (m[q][q] - m[p][p]) / (2.0 * m[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    mkp, mkq = m[k][p], m[k][q]
                    m[k][p] = c * mkp - s * mkq
                    m[k][q] = s * mkp + c * mkq
                for k in range(n):
                    mpk, mqk = m[p][k], m[q][k]
                    m[p][k] = c * mpk - s * mqk
                    m[q][k] = s * mpk + c * mqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    return [m[i][i] for i in range(n)], v


def _sequential_basis(s: List[List[float]], k: int) -> Optional[List[List[float]]]:
    """顺序残差化（Gram-Schmidt）在 Gram 空间中的基向量系数。

    第 i 个基向量 = 第 i 个标准化列对前 i-1 个**已正交化**基向量的残差，再归一化。
    返回 ``None`` 表示某一步残差方差退化（该因子被前面的因子完全解释）。
    """
    basis: List[List[float]] = []
    for i in range(k):
        coefs = [0.0] * k
        coefs[i] = 1.0
        for bc in basis:
            dot = sum(bc[t] * s[i][t] for t in range(k))
            for t in range(k):
                coefs[t] -= dot * bc[t]
        var = sum(coefs[a] * coefs[b] * s[a][b] for a in range(k) for b in range(k))
        if var <= 1e-12:
            return None
        scale = 1.0 / math.sqrt(var)
        basis.append([c * scale for c in coefs])
    return basis


def _lowdin_basis(s: List[List[float]], k: int,
                  eigen_floor: float) -> Optional[List[List[float]]]:
    """Löwdin 对称正交化 ``Z(Z'Z)^{-1/2}`` 在 Gram 空间中的系数。

    返回 ``k`` 个系数向量（第 b 个对应输出列 b）。
    最小特征值 <= ``eigen_floor`` 时返回 ``None`` —— 因子近似共线时
    ``S^{-1/2}`` 会放大噪声，宁可判不可用，也不产出一个被噪声主导的"正交"结果。
    """
    evals, v = _jacobi_eigen([row[:] for row in s])
    if min(evals) <= eigen_floor:
        return None
    inv_sqrt = [[0.0] * k for _ in range(k)]
    for i in range(k):
        for j in range(k):
            inv_sqrt[i][j] = sum(v[i][a] * (evals[a] ** -0.5) * v[j][a] for a in range(k))
    return [[inv_sqrt[a][b] for a in range(k)] for b in range(k)]


def factor_rank_correlation(
    panel: Dict[str, Any],
    *,
    factors: Optional[Sequence[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """各因子对在**每个横截面内**的 Spearman 秩相关，再对截面取均值。

    ``mean_rho`` 接近 ±1 的两个因子在等权合成时**重复计票**。
    另给 ``abs_gt_0_5_rate``（|rho| > 0.5 的截面占比）——它比均值更能反映
    "是否稳定地冗余"：均值 0.4 但 100% 截面都 > 0.5 与均值 0.4 但只有 10% 截面
    超过 0.5，含义完全不同。
    """
    names = list(factors) if factors else list(panel.get("factor_names") or FACTOR_LABELS)
    pairs = [(names[i], names[j]) for i in range(len(names)) for j in range(i + 1, len(names))]
    acc: Dict[str, List[float]] = {f"{a}~{b}": [] for a, b in pairs}
    for p in panel.get("periods", []):
        for a, b in pairs:
            va, vb = p["factors"].get(a), p["factors"].get(b)
            if not va or not vb:
                continue
            rho = spearman(va, vb)
            if rho is not None:
                acc[f"{a}~{b}"].append(rho)
    out: Dict[str, Dict[str, Any]] = {}
    for key, vals in acc.items():
        if not vals:
            out[key] = {"mean_rho": None, "abs_gt_0_5_rate": None, "n_cross_sections": 0}
            continue
        out[key] = {
            "mean_rho": sum(vals) / len(vals),
            "abs_gt_0_5_rate": sum(1 for v in vals if abs(v) > 0.5) / len(vals),
            "n_cross_sections": len(vals),
        }
    return out


def orthogonalize_panel(
    panel: Dict[str, Any],
    *,
    method: str = "sequential",
    factors: Optional[Sequence[str]] = None,
    order: Optional[Sequence[str]] = None,
    min_cross_section: int = 10,
    eigen_floor: float = 1e-6,
) -> Dict[str, Any]:
    """对每个横截面做正交化，返回新面板（不修改入参）。

    * ``"sequential"``（默认）—— 顺序残差化（Gram-Schmidt）。按 ``order``
      依次对**已正交化**的前序因子回归取残差。真正消除冗余，但**结果依赖顺序**：
      ``order`` 缺省用事前声明的 :data:`ORTHO_ORDER_DEFAULT`，
      **不得依据 IC 结果调整顺序**（那等于用结果选参数）。
    * ``"lowdin"`` —— Löwdin 对称正交化，**与顺序无关**。因子近似共线
      （最小特征值 <= ``eigen_floor``）时该期判为不可用、原样保留，不硬算。

    因子值先转平均秩再标准化（抗离群、与 Spearman 口径一致），
    正交化在标准化空间内进行，结果等价于对原列做线性组合。

    残差后的因子**不再可单独解释** —— 其经济含义是"扣掉前序因子后的增量信息"，
    报告里必须写明。某期若秩标准化失败或样本不足，该期**原样保留**并标记
    ``orthogonalized=False`` —— 不补造、不丢弃。
    """
    names_all = list(panel.get("factor_names") or FACTOR_LABELS)
    wanted = [f for f in (list(factors) if factors else list(COMPOSITE_FACTORS)) if f in names_all]
    if method == "sequential":
        seq = list(order) if order else [f for f in ORTHO_ORDER_DEFAULT if f in wanted]
        names = [f for f in seq if f in wanted] + [f for f in wanted if f not in seq]
    elif method == "lowdin":
        names = wanted
    else:
        raise ValueError(f"unknown method: {method}（可选 'sequential' / 'lowdin'）")

    new_periods: List[Dict[str, Any]] = []
    for p in panel.get("periods", []):
        cols: Dict[str, List[float]] = {}
        for f in names:
            z = _rank_standardize(p["factors"].get(f) or [])
            if z is None:
                cols = {}
                break
            cols[f] = z
        n = len(next(iter(cols.values()))) if cols else 0
        if len(cols) < 2 or n < min_cross_section:
            keep = dict(p)
            keep["orthogonalized"] = False
            keep["ortho_skip_reason"] = ("insufficient_or_degenerate_cross_section"
                                         if len(cols) < 2 else "below_min_cross_section")
            new_periods.append(keep)
            continue

        ordered = [cols[f] for f in names]
        s = _gram(ordered, n)
        basis = (_sequential_basis(s, len(names)) if method == "sequential"
                 else _lowdin_basis(s, len(names), eigen_floor))
        if basis is None:
            keep = dict(p)
            keep["orthogonalized"] = False
            keep["ortho_skip_reason"] = ("degenerate_residual_variance" if method == "sequential"
                                         else "ill_conditioned_gram_matrix")
            new_periods.append(keep)
            continue

        merged = dict(p["factors"])
        for f, coefs in zip(names, basis, strict=True):
            merged[f] = _materialize(coefs, ordered, n)
        new_periods.append({
            "date": p.get("date"),
            "factors": merged,
            "forward": p["forward"],
            "orthogonalized": True,
        })

    return {
        "periods": new_periods,
        "panel_len": panel.get("panel_len"),
        "factor_names": names_all,
        "horizon": panel.get("horizon"),
        "step": panel.get("step"),
        "orthogonalized_factors": names,
        "ortho_method": method,
        "ortho_order": names if method == "sequential" else None,
        "n_periods_orthogonalized": sum(1 for p in new_periods if p.get("orthogonalized")),
    }


def run_orthogonal_ic_study(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    method: str = "sequential",
    factors: Optional[Sequence[str]] = None,
    order: Optional[Sequence[str]] = None,
    eigen_floor: float = 1e-6,
    horizon: int = DEFAULT_HORIZON,
    step: int = DEFAULT_STEP,
    min_cross_section: int = 50,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """正交化前后的 IC 对照 + 冗余诊断（一次构建面板，两处复用）。

    返回 ``{raw, orthogonalized, correlation_before, correlation_after,
    method, order, factors, n_periods_orthogonalized}``。
    ``raw`` 与 :func:`run_ic_study` 在同一数据上**逐值相同**（有测试守卫）。
    """
    built = build_factor_panel(data, horizon=horizon, step=step,
                               min_cross_section=min_cross_section, start=start, end=end)
    orth_panel = orthogonalize_panel(built, method=method, factors=factors, order=order,
                                     min_cross_section=min_cross_section,
                                     eigen_floor=eigen_floor)
    # 冗余诊断只覆盖**被正交化的那一组**：若把未正交化的因子也算进来，
    # "最差的一对"永远来自未正交化的因子，前后对照将看不出任何变化。
    targets = orth_panel["orthogonalized_factors"]
    return {
        "raw": _study_from_panel(built, horizon, step),
        "orthogonalized": _study_from_panel(orth_panel, horizon, step),
        "correlation_before": factor_rank_correlation(built, factors=targets),
        "correlation_after": factor_rank_correlation(orth_panel, factors=targets),
        "method": method,
        "order": orth_panel["ortho_order"],
        "factors": list(targets),
        "n_periods_orthogonalized": orth_panel["n_periods_orthogonalized"],
    }


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

    返回 {factor: {ic_mean, ic_std, icir, t, p, n_periods, prior_sign, label}}

    实现已提取为 ``build_factor_panel`` + ``_study_from_panel`` 两步
    （2026-09-19，为接入正交化），**数值结果不变** ——
    有 `tests/test_factor_ic_lab_refactor.py` 以固定合成数据锁定重构前后的输出。
    """
    built = build_factor_panel(data, horizon=horizon, step=step,
                               min_cross_section=min_cross_section, start=start, end=end)
    return _study_from_panel(built, horizon, step)


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
