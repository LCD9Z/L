# -*- coding: utf-8 -*-
r"""专家组合过滤器 —— 把 2026-09-30 六人圆桌的处方落成一个**可组合、可开关**的过滤器。

## 方向（本模块的定位）

上一轮实测确定了 `candidate_filter` 与 `position_scaler` 的**语义分界**：

| | `candidate_filter`（本模块） | `position_scaler`（`market_risk_gate`） |
|---|---|---|
| 粒度 | **逐股** `(code, hist, day)` | 逐日 `(day)` |
| 表达力 | 「买 / 不买」 | 「买多少」（含半仓） |
| 适用 | **排除特定特征的个股** | 整体降敞口 |

→ **过滤器的方向 = 逐股排除「情绪/拥挤极端」**。这不是新想法 ——
它正是项目**唯一稳健的正向发现**（尾部剔除：剔除 `ret_20` + `vol_ratio` 顶部 20%）
的推广，而六位专家各自从自己的框架指向同一主线：

| 席位 | 处方 | 本模块中的条件 |
|------|------|--------------|
| 📡 信号派首席 | 「完全没有"什么时候该空仓"的开关」 | `use_market` —— 市场级风险日**全池排除** |
| 🏔️ 逆向投资人 | 「缺**时间序列**的情绪极值门」 | `use_turnover` —— 个股换手率 **250 日自身分位** > 80% |
| ⚡ 短线冲浪手 | 「连板/炸板代码已写好但从未接进回测」 | `use_streak` —— **连板高度 ≥ 2** |
| （项目已确立） | 尾部剔除（配对 t = +8.35/+3.62/+2.52） | `tail_factors` —— `ret_20`/`vol_ratio` 顶部 20% |
| 🌊 产业策略师 | 「风格拥挤度 gate」 | `use_industry_crowding` —— 统计行业簇的**等权换手率** 250 日自身分位 > 80% → 整簇排除 |
| 🧮 估值分析师 | 「`pb`/`pe_ttm` 上轨降权/排除」 | `use_valuation_cap` —— `pe_ttm` 当日截面分位 > 67% → 排除 |

> **2026-10-18：最后两个 ❌ 已落地。** 此前标注「未实现」的两条理由
> （「需先做统计行业聚类」「需 PIT 财务 join」）都已被既有模块解决 ——
> `pit/statistical_industry.py`（纯价格派生、PIT-clean 的收益相关性聚类）
> 与 `pit/pit_fundamentals.py`（`factors_as_of(code, day, price)` 给 `pb`/`pe_ttm`）。
> **不是新数据源，是把已有的两个模块接进过滤器。**

## 组合方式

**AND（任一条件触发即排除）** —— 各条件独立可开关，便于逐个归因。

## PIT 正确性

三个条件全部**只用 `day` 及之前的数据**：
- 换手率分位：滚动窗**不含当日**（避免自我参照，同 `market_risk_gate` 的教训）
- 连板高度：只看截至 `day` 的连续涨停
- 尾部剔除：`compute_factors(bars, i)` 本身只用到第 `i` 根

## 性能

`candidate_filter` 在回测里**逐股逐日**调用（300 只 × 776 天 ≈ 23 万次）。
故所有条件**预计算成 `{day: set(codes)}`**，热路径只做集合查找，**零 I/O、零计算**。
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from factors.factor_ic_lab import MIN_HISTORY, compute_factors

# ---- 事前固定的阈值（不得依据回测结果调整）----
TURNOVER_LOOKBACK = 250          # 个股换手率自身分位的历史窗
TURNOVER_PCT_THRESHOLD = 0.80    # 高于该分位 → 情绪过热 → 排除
STREAK_THRESHOLD = 2             # 连板高度 ≥ 该值 → 排除
TAIL_FRAC = 0.20                 # 尾部剔除：剔除顶部 20%
MIN_CROSS_SECTION = 50           # 截面过薄不做分位判定

# ---- 产业策略师 · 行业拥挤度 gate（2026-10-18 落地）----
# 为什么用「统计行业簇的等权换手率」而不是官方行业成交额占比：
# 项目**没有 PIT 官方行业分类**（用今天的分类回测历史＝分类幸存者偏差），
# 而 `pit/statistical_industry.py` 的收益相关性聚类是纯价格派生、无前视。
# 口径声明必须随结论走：**统计行业 ≠ 官方行业**。
IND_CROWD_LOOKBACK = 250         # 簇拥挤度的历史分位窗（与个股换手率同口径）
IND_CROWD_PCT_THRESHOLD = 0.80   # 簇换手率高于自身该分位 → 拥挤 → 整簇排除
IND_N_CLUSTERS = 20              # 目标簇数（statistical_industry 默认）
IND_RECLUSTER_EVERY = 60         # 重聚类间隔（交易日）
IND_MIN_CLUSTER_SIZE = 5         # 簇内有效成员少于该值 → 该簇不判定
#: 拥挤度的两种口径，**预注册时必须二选一并固定**（不得按结果挑）：
#:   ``level`` —— 簇等权换手率的**绝对水平**分位（最朴素，无额外假设）
#:   ``ratio`` —— 簇等权换手率 / 自身过去 lookback 日均值（**去趋势**）
#: 2026-10-18 冒烟实测（80 只 / 2599 天）：``level`` 触发日占比 **39.9%**、
#: 单日最多排除 **46/80 = 58%** —— 明显高于 80% 分位应有的 ~20%，
#: 说明簇均换手率存在**长期趋势**（量能中枢上移），绝对分位会把趋势误判为拥挤。
#: 这不是调参理由（按结果改阈值 = p-hacking），而是**两个口径都要预注册、
#: 各自独立跑 A/B、各自报告**的理由。
IND_CROWD_NORMALIZE = ("level", "ratio")

# ---- 估值分析师 · 估值上轨排除（2026-10-18 落地）----
# 与 `risk/valuation_weight.py` 的分档**同口径**（下轨 0.33 / 上轨 0.67），
# 区别只在于处置：那边「上轨降权到 0.5」，这边「上轨直接不买」。
# 两者**必须分开开关** —— 一个改权重、一个改候选集，混在一起无法归因。
VAL_METRIC = "pe_ttm"            # 项目双校正因子之一（与 valuation_weight 一致）
VAL_HIGH_PCT = 0.67              # 截面分位高于该值 → 上轨 → 排除


def _f(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 条件 A · 个股换手率的「时间序列」分位（逆向投资人）
# ---------------------------------------------------------------------------

def precompute_turnover_extreme(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    lookback: int = TURNOVER_LOOKBACK,
    pct: float = TURNOVER_PCT_THRESHOLD,
) -> Dict[str, Set[str]]:
    r"""逐股、逐日判定「换手率处于自身近 ``lookback`` 日高分位」。

    返回 ``{day: set(codes)}``。

    **PIT**：分位窗为 ``[i-lookback, i-1]``（**不含当日**）—— 与
    `market_risk_gate` 的成交额分位同一口径，避免自我参照。
    历史不足 ``lookback`` 日时**不做判定**（缺失即不干预）。
    """
    out: Dict[str, Set[str]] = {}
    for code, bars in data.items():
        hist: List[float] = []
        for b in bars:
            day = str(b.get("date") or "")
            t = _f(b.get("turnover"))
            if day and t is not None and len(hist) >= lookback:
                window = hist[-lookback:]
                below = sum(1 for x in window if x < t)
                if below / len(window) > pct:
                    out.setdefault(day, set()).add(code)
            if t is not None:
                hist.append(t)
    return out


# ---------------------------------------------------------------------------
# 条件 B · 连板高度（短线冲浪手）
# ---------------------------------------------------------------------------

def precompute_limit_up_streak(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    threshold: int = STREAK_THRESHOLD,
) -> Dict[str, Set[str]]:
    r"""逐股、逐日判定「截至当日已连续涨停 ≥ ``threshold`` 天」。

    用逐日 ``limit_ratio`` 判涨停（与 `exchange_rules` 口径一致，
    含 ST 的 5% 档与创业板改革前后差异）。

    **PIT**：只用到第 ``i`` 根及之前 —— 当日收盘即可判定。
    行情缺口（close 缺失）**断开连板计数**，不得跨缺口累加。
    """
    out: Dict[str, Set[str]] = {}
    for code, bars in data.items():
        prev_close: Optional[float] = None
        streak = 0
        for b in bars:
            day = str(b.get("date") or "")
            close = _f(b.get("close"))
            if close is None:
                prev_close = None
                streak = 0
                continue
            lr = _f(b.get("limit_ratio")) or 0.0
            if prev_close and prev_close > 0 and lr > 0:
                limit_up_price = round(prev_close * (1.0 + lr), 2)
                if close >= limit_up_price - 0.005:
                    streak += 1
                else:
                    streak = 0
            else:
                streak = 0
            if day and streak >= threshold:
                out.setdefault(day, set()).add(code)
            prev_close = close
    return out


# ---------------------------------------------------------------------------
# 条件 C · 尾部剔除（项目已确立的唯一稳健正向发现）
# ---------------------------------------------------------------------------

def precompute_tail_exclusion(
    data: Dict[str, List[Dict[str, Any]]],
    factors: Sequence[str] = ("ret_20", "vol_ratio"),
    *,
    top_frac: float = TAIL_FRAC,
    min_cross_section: int = MIN_CROSS_SECTION,
) -> Dict[str, Set[str]]:
    """逐因子、逐日「处于最高 ``top_frac`` 分位」的股票集合，**取并集**。

    与 `scripts/run_tail_exclusion_study.build_exclusion_maps` 同口径，
    但返回**并集**（任一因子处于尾部即排除），便于直接当 filter 用。
    """
    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    dates: Set[str] = set()
    for bars in data.values():
        dates.update(str(b["date"]) for b in bars if b.get("date"))

    out: Dict[str, Set[str]] = {}
    for day in sorted(dates):
        per_factor: Dict[str, List[Tuple[str, float]]] = {f: [] for f in factors}
        for code, bars in data.items():
            i = idx_map[code].get(day)
            if i is None or i < MIN_HISTORY:
                continue
            fac = compute_factors(bars, i)
            if fac is None:
                continue
            for f in factors:
                v = fac.get(f)
                if v is not None and v == v:          # 排除 NaN
                    per_factor[f].append((code, v))
        excl: Set[str] = set()
        for f in factors:
            pairs = per_factor[f]
            if len(pairs) < min_cross_section:
                continue
            pairs.sort(key=lambda t: t[1])
            cut = int(len(pairs) * (1 - top_frac))
            excl.update(code for code, _ in pairs[cut:])
        if excl:
            out[day] = excl
    return out


# ---------------------------------------------------------------------------
# 条件 D · 行业拥挤度 gate（产业策略师，2026-10-18 落地）
# ---------------------------------------------------------------------------

def precompute_industry_crowding(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    labels: Optional[Dict[str, Dict[str, int]]] = None,
    lookback: int = IND_CROWD_LOOKBACK,
    pct: float = IND_CROWD_PCT_THRESHOLD,
    n_clusters: int = IND_N_CLUSTERS,
    recluster_every: int = IND_RECLUSTER_EVERY,
    min_cluster_size: int = IND_MIN_CLUSTER_SIZE,
    normalize: str = "level",
) -> Dict[str, Set[str]]:
    r"""逐日判定「所属统计行业簇整体拥挤」，返回 ``{day: set(codes)}``。

    ## 语义

    「风格拥挤度」在项目里**没有官方行业口径可用**（无 PIT 行业分类），
    故用 :func:`pit.statistical_industry.build_statistical_industry`
    的收益相关性聚类作为「统计行业」。拥挤度定义为：

    > 该簇成员当日 **等权平均换手率**，相对该簇自身近 ``lookback`` 日
    > 的历史分位 **> ``pct``** ⇒ 该簇拥挤 ⇒ **整簇成员当日排除**。

    这与个股换手率条件（条件 A）的区别在**层级**：条件 A 判「这只股自己热」，
    本条件判「它所在的那一类整体热」—— 后者才能抓到「板块性过热」，
    而这正是产业策略师原话里「风格拥挤」的所指。

    ## ``normalize`` 两种口径（预注册时二选一，**不得按结果挑**）

    | 口径 | 定义 | 适用 / 风险 |
    |---|---|---|
    | ``level``（默认） | 簇均换手率的**绝对水平**分位 | 最朴素、无额外假设；但**受长期趋势污染**：量能中枢上移时天天像历史最高 |
    | ``ratio`` | 簇均换手率 / 其过去 ``lookback`` 日均值，再对该比率取分位 | 去趋势；引入「相对强度」这一层假设 |

    2026-10-18 冒烟（80 只 / 2599 天，``level``）：触发日 **39.9%**、单日最多排除
    **46/80**。80% 分位理论上应给 ~20% 触发率 —— 高出近一倍，是趋势被误判为拥挤的
    直接证据。**这不是调低阈值的理由**（按结果改阈值＝p-hacking），
    而是两个口径都要预注册、各自跑、各自报告的理由。

    ## PIT

    - 聚类：由 `build_statistical_industry` 保证（重聚类窗口 ``[T-lookback, T)``）；
    - 分位：窗口为 ``[i-lookback, i-1]``（**不含当日**），当日值只作被比较对象
      —— 与条件 A 同一口径（当日收盘后即可判定，次日开盘执行）。

    ## 缺失即不干预

    - 当日**无簇标签**的股票 → 不排除（不知道它属于哪一类，不猜）；
    - 簇内有效成员 < ``min_cluster_size`` → 该簇不判定；
    - 该簇历史不足 ``lookback`` 日 → 不判定。

    ⚠️ **一个刻意的例外**：簇判定为拥挤后，排除集包含该簇**全部有标签成员**，
    即使某只当日缺 `turnover`。理由：簇拥挤度是**簇级外部信息**
    （由同簇其他成员算出），不依赖该股自身当日数据；且方向是**保守**的
    （宁可少买一只不知情的，也不在已知过热的风格里持仓）。
    这与「个股自身指标缺失就不判它」不同 —— 后者没有外部信息可用。

    :param labels: 预算好的 ``{day: {code: cluster}}``；``None`` 则内部现算
        （**慢**：O(簇数² × 重聚类次数)，80 只 × 2599 天实测约 14 秒）。
    :param normalize: ``"level"`` 或 ``"ratio"``，见上表。
    """
    if normalize not in IND_CROWD_NORMALIZE:
        raise ValueError(f"normalize 只支持 {IND_CROWD_NORMALIZE}，收到 {normalize!r}")
    if labels is None:
        from pit.statistical_industry import build_statistical_industry
        labels = build_statistical_industry(
            data, n_clusters=n_clusters, recluster_every=recluster_every)
    if not labels:
        return {}

    turn_by: Dict[str, Dict[str, Optional[float]]] = {
        code: {str(b["date"]): _f(b.get("turnover"))
               for b in bars if b.get("date")}
        for code, bars in data.items()
    }

    # 逐日 → 逐簇 的等权平均换手率
    day_cluster_turn: Dict[str, Dict[int, float]] = {}
    for day, members in labels.items():
        acc: Dict[int, List[float]] = {}
        for code, cl in members.items():
            t = turn_by.get(code, {}).get(day)
            if t is None:
                continue
            acc.setdefault(cl, []).append(t)
        agg = {cl: sum(v) / len(v) for cl, v in acc.items()
               if len(v) >= min_cluster_size}
        if agg:
            day_cluster_turn[day] = agg

    hist: Dict[int, List[float]] = {}
    ratio_hist: Dict[int, List[float]] = {}
    out: Dict[str, Set[str]] = {}
    for day in sorted(day_cluster_turn):
        today = day_cluster_turn[day]
        hot: Set[int] = set()
        for cl, v in today.items():
            h = hist.setdefault(cl, [])
            rh = ratio_hist.setdefault(cl, [])
            cur_ratio: Optional[float] = None
            if len(h) >= lookback:
                window = h[-lookback:]
                mean = sum(window) / len(window)
                if mean > 0:
                    cur_ratio = v / mean
            if normalize == "ratio":
                series: List[float] = rh
                cur: Optional[float] = cur_ratio
            else:
                series = h
                cur = v if len(h) >= lookback else None
            if cur is not None and len(series) >= lookback:
                w = series[-lookback:]
                below = sum(1 for x in w if x < cur)
                if below / len(w) > pct:
                    hot.add(cl)
            h.append(v)                       # 当日值入历史，供**次日**比较
            if cur_ratio is not None:
                rh.append(cur_ratio)          # 比率序列同样只供次日使用
        if not hot:
            continue
        for code, cl in labels.get(day, {}).items():
            if cl in hot:
                out.setdefault(day, set()).add(code)
    return out


# ---------------------------------------------------------------------------
# 条件 E · 估值上轨排除（估值分析师，2026-10-18 落地）
# ---------------------------------------------------------------------------

def precompute_valuation_cap(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    fund: Any = None,
    dataset_dir: Optional[str] = None,
    metric: str = VAL_METRIC,
    high_pct: float = VAL_HIGH_PCT,
    min_cross_section: int = MIN_CROSS_SECTION,
    rebalance_days: Optional[Sequence[str]] = None,
) -> Dict[str, Set[str]]:
    r"""逐日判定「估值处于当日截面最高分位」，返回 ``{day: set(codes)}``。

    ## 与 `risk/valuation_weight.py` 的分工

    | | `valuation_weight` | **本函数** |
    |---|---|---|
    | 处置 | 上轨**降权**到 0.5 | 上轨**直接不买** |
    | 粒度 | `weight_func`（买多少） | `candidate_filter`（买不买） |

    两者**必须分开开关** —— 一个改权重、一个改候选集，混在一起无法归因。

    ## PIT

    用 `PitFundamentals.factors_as_of(code, day, price=当日收盘)`：
    只取**该日已公告**的报表（公告日不可信时退回法定披露截止日），
    价格用当日收盘 —— 两者都是当日已知量，无前视。

    ## 缺失即不干预

    - 该股该日无可用财报 / `metric` 缺失 / ≤0 → 不排除（**不插补**）；
    - 当日有效估值数 < ``min_cross_section`` → **不做分档**（截面太薄分位无意义）。

    :param fund: 预算好的 ``PitFundamentals`` 实例（便于测试注入）；
    :param dataset_dir: ``fund is None`` 时用它加载
        ``fundamentals.jsonl`` / ``disclosure_dates.jsonl``；
    :param rebalance_days: 只在这些日子分档；``None`` = 全部交易日（**慢**）。
    """
    if fund is None:
        if not dataset_dir:
            raise ValueError("precompute_valuation_cap 需要 fund 或 dataset_dir 之一")
        from pit.pit_fundamentals import (PitFundamentals, load_disclosures,
                                          load_records)
        records = load_records(os.path.join(dataset_dir, "fundamentals.jsonl"))
        disc_path = os.path.join(dataset_dir, "disclosure_dates.jsonl")
        disclosures = load_disclosures(disc_path) if os.path.exists(disc_path) else {}
        fund = PitFundamentals(records, disclosures)

    close_by: Dict[str, Dict[str, float]] = {
        code: {str(b["date"]): float(b["close"])
               for b in bars if b.get("date") and b.get("close") is not None}
        for code, bars in data.items()
    }
    if rebalance_days is None:
        all_days: Set[str] = set()
        for m in close_by.values():
            all_days.update(m)
        days: List[str] = sorted(all_days)
    else:
        days = [str(d) for d in rebalance_days]

    out: Dict[str, Set[str]] = {}
    for day in days:
        vals: List[Tuple[str, float]] = []
        for code, cm in close_by.items():
            px = cm.get(day)
            if px is None or px <= 0:
                continue
            f = fund.factors_as_of(code, day, price=px)
            v = _f((f or {}).get(metric))
            if v is not None and v > 0:       # 负 PE 无经济含义，不参与排序
                vals.append((code, v))
        if len(vals) < min_cross_section:
            continue
        vals.sort(key=lambda t: t[1])
        cut = int(len(vals) * high_pct)
        excl = {code for code, _ in vals[cut:]}
        if excl:
            out[day] = excl
    return out


# ---------------------------------------------------------------------------
# 组合
# ---------------------------------------------------------------------------

def build_expert_filter(
    data: Dict[str, List[Dict[str, Any]]],
    *,
    market_risk: Optional[Dict[str, Dict[str, Any]]] = None,
    use_market: bool = True,
    use_turnover: bool = True,
    use_streak: bool = True,
    use_tail: bool = True,
    use_industry_crowding: bool = False,
    use_valuation_cap: bool = False,
    turnover_pct: float = TURNOVER_PCT_THRESHOLD,
    streak_threshold: int = STREAK_THRESHOLD,
    tail_factors: Sequence[str] = ("ret_20", "vol_ratio"),
    tail_frac: float = TAIL_FRAC,
    ind_labels: Optional[Dict[str, Dict[str, int]]] = None,
    ind_crowd_pct: float = IND_CROWD_PCT_THRESHOLD,
    ind_crowd_lookback: int = IND_CROWD_LOOKBACK,
    ind_n_clusters: int = IND_N_CLUSTERS,
    ind_normalize: str = "level",
    valuation_fund: Any = None,
    valuation_dataset_dir: Optional[str] = None,
    valuation_metric: str = VAL_METRIC,
    valuation_high_pct: float = VAL_HIGH_PCT,
    valuation_rebalance_days: Optional[Sequence[str]] = None,
) -> Tuple[Callable[[str, List[Dict[str, Any]], str], bool],
           Dict[str, Any]]:
    r"""把各专家的条件组合成一个 ``candidate_filter``。

    **组合方式：AND（任一条件触发即排除）**。

    ## ⚠️ 为什么两个新条件默认 **False**

    条件 A–C 与市场 gate 默认开启，是因为它们已在此前的研究里跑过、
    结论已在案（尾部剔除 t = +8.35/+3.62/+2.52 等）。
    条件 D/E 是 2026-10-18 才落地的**处方**：

    - 默认开启会**静默改写** `scripts/run_expert_filter_study.py` 等脚本的
      既有配置 → 历史数字不可复现，且违反「改口径要重跑」的纪律；
    - 正确路径是**先预注册 A/B**（D 单开、E 单开、D+E），
      有了增量结论再决定是否改默认。

    所以默认关 = **尊重既有结论**，不是「没做完」。

    :return: ``(filter_fn, stats)`` —— ``filter_fn(code, hist, day) -> bool``
        （``True`` = 保留）。``stats`` 记录各条件的排除规模，便于归因。

    逐个关闭即可做单条件归因（见 ``scripts/run_expert_filter_study.py``）。
    """
    excl_turnover: Dict[str, Set[str]] = {}
    excl_streak: Dict[str, Set[str]] = {}
    excl_tail: Dict[str, Set[str]] = {}
    excl_ind: Dict[str, Set[str]] = {}
    excl_val: Dict[str, Set[str]] = {}
    blocked_days: Set[str] = set()

    if use_turnover:
        excl_turnover = precompute_turnover_extreme(data, pct=turnover_pct)
    if use_streak:
        excl_streak = precompute_limit_up_streak(data, threshold=streak_threshold)
    if use_tail:
        excl_tail = precompute_tail_exclusion(data, tail_factors, top_frac=tail_frac)
    if use_industry_crowding:
        excl_ind = precompute_industry_crowding(
            data, labels=ind_labels, lookback=ind_crowd_lookback, pct=ind_crowd_pct,
            n_clusters=ind_n_clusters, normalize=ind_normalize)
    if use_valuation_cap:
        excl_val = precompute_valuation_cap(
            data, fund=valuation_fund, dataset_dir=valuation_dataset_dir,
            metric=valuation_metric, high_pct=valuation_high_pct,
            rebalance_days=valuation_rebalance_days)
    if use_market and market_risk:
        blocked_days = {d for d, v in market_risk.items()
                        if (v or {}).get("state") == "EXTREME"}

    def flt(code: str, hist: List[Dict[str, Any]], day: str) -> bool:
        d = str(day)
        if d in blocked_days:
            return False
        if code in excl_turnover.get(d, ()):
            return False
        if code in excl_streak.get(d, ()):
            return False
        if code in excl_ind.get(d, ()):
            return False
        if code in excl_val.get(d, ()):
            return False
        return code not in excl_tail.get(d, ())

    stats = {
        "market_blocked_days": len(blocked_days),
        "turnover_excl_days": len(excl_turnover),
        "turnover_excl_pairs": sum(len(v) for v in excl_turnover.values()),
        "streak_excl_days": len(excl_streak),
        "streak_excl_pairs": sum(len(v) for v in excl_streak.values()),
        "tail_excl_days": len(excl_tail),
        "tail_excl_pairs": sum(len(v) for v in excl_tail.values()),
        "industry_crowd_excl_days": len(excl_ind),
        "industry_crowd_excl_pairs": sum(len(v) for v in excl_ind.values()),
        "valuation_cap_excl_days": len(excl_val),
        "valuation_cap_excl_pairs": sum(len(v) for v in excl_val.values()),
        "enabled": {"market": use_market, "turnover": use_turnover,
                    "streak": use_streak, "tail": use_tail,
                    "industry_crowding": use_industry_crowding,
                    "valuation_cap": use_valuation_cap},
        "caliber": {
            "ind_crowd_pct": ind_crowd_pct,
            "ind_crowd_lookback": ind_crowd_lookback,
            "ind_n_clusters": ind_n_clusters,
            "ind_normalize": ind_normalize,
            "valuation_metric": valuation_metric,
            "valuation_high_pct": valuation_high_pct,
        },
    }
    return flt, stats


def load_panel(dataset_dir: str, *, max_stocks: int = 0,
               min_rows: int = 200) -> Dict[str, List[Dict[str, Any]]]:
    """加载过滤器所需的**最小字段**面板（date/close/limit_ratio/turnover）。"""
    import csv as _csv

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
                    rows.append({"date": r.get("date"), "close": r.get("close"),
                                 "limit_ratio": r.get("limit_ratio"),
                                 "turnover": r.get("turnover")})
        except OSError:
            continue
        if len(rows) >= min_rows:
            out[c] = rows
    return out
