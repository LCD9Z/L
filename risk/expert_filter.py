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
| 🌊 产业策略师 | 「风格拥挤度 gate」 | ⚠️ **未实现** —— 需先做统计行业聚类，见 `PROJECT_HEALTH_AUDIT.md` |
| 🧮 估值分析师 | 「`pb`/`pe_ttm` 上轨降权/排除」 | ⚠️ **未实现** —— 需 PIT 财务 join |

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
    turnover_pct: float = TURNOVER_PCT_THRESHOLD,
    streak_threshold: int = STREAK_THRESHOLD,
    tail_factors: Sequence[str] = ("ret_20", "vol_ratio"),
    tail_frac: float = TAIL_FRAC,
) -> Tuple[Callable[[str, List[Dict[str, Any]], str], bool],
           Dict[str, Any]]:
    r"""把各专家的条件组合成一个 ``candidate_filter``。

    **组合方式：AND（任一条件触发即排除）**。

    :return: ``(filter_fn, stats)`` —— ``filter_fn(code, hist, day) -> bool``
        （``True`` = 保留）。``stats`` 记录各条件的排除规模，便于归因。

    **默认全部开启**。逐个关闭即可做单条件归因（见
    ``scripts/run_expert_filter_study.py``）。
    """
    excl_turnover: Dict[str, Set[str]] = {}
    excl_streak: Dict[str, Set[str]] = {}
    excl_tail: Dict[str, Set[str]] = {}
    blocked_days: Set[str] = set()

    if use_turnover:
        excl_turnover = precompute_turnover_extreme(data, pct=turnover_pct)
    if use_streak:
        excl_streak = precompute_limit_up_streak(data, threshold=streak_threshold)
    if use_tail:
        excl_tail = precompute_tail_exclusion(data, tail_factors, top_frac=tail_frac)
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
        return code not in excl_tail.get(d, ())

    stats = {
        "market_blocked_days": len(blocked_days),
        "turnover_excl_days": len(excl_turnover),
        "turnover_excl_pairs": sum(len(v) for v in excl_turnover.values()),
        "streak_excl_days": len(excl_streak),
        "streak_excl_pairs": sum(len(v) for v in excl_streak.values()),
        "tail_excl_days": len(excl_tail),
        "tail_excl_pairs": sum(len(v) for v in excl_tail.values()),
        "enabled": {"market": use_market, "turnover": use_turnover,
                    "streak": use_streak, "tail": use_tail},
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
