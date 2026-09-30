# -*- coding: utf-8 -*-
r"""市场级风险状态门（纯离线，零新数据源）。

## 为什么做这个

2026-09-30 的六人专家圆桌审查中，**三个席位各自独立**提出同一个缺口：

| 席位 | 原话 |
|------|------|
| 信号派首席 | 「系统**完全没有"什么时候该空仓"的开关**」 |
| 逆向投资人 | 「缺**时间序列**的情绪极值门」（现有尾部剔除只是**横截面**过滤） |
| 产业策略师 | 「缺风格拥挤度 gate」→ 2024-01 窗口策略 −30.71% 而等权全A **+31.40%** |

三人的处方都指向「**市场级状态门**」，且都指出**零新数据可实现** ——
v3 数据集里逐日 `limit_ratio`（涨跌停幅度）与 `amount`（成交额）**一直都在，
却从未被当作信号使用**（此前只用于「涨跌停不可买」的成交约束）。

## 指标

1. **跌停家数占比** `limit_down_ratio` = 当日跌停股票数 / 当日有行情股票数
   —— 系统性风险的**直接观测量**（不是代理变量）。跌停需 `close <= round(prev_close×(1−limit_ratio), 2)`，
   逐日 `limit_ratio` 已按板块/ST/改革日分段（见 `exchange_rules`）。
2. **全市场成交额分位** `amount_percentile` = 当日全市场成交额在**过去 lookback 日**中的分位
   —— 拥挤度/情绪的**时间序列**位置（逆向投资人点名缺的正是这一维）。

## PIT 正确性

- 两个指标都**只用当日及之前**的数据（`amount_percentile` 用**不含当日**的历史窗，避免自我参照）
- 状态在**当日收盘后**确定 → **T+1 开盘**方可据此交易

## 阈值（事前固定，不做事后调整）

| 状态 | 条件 | 语义 |
|------|------|------|
| `EXTREME` | 跌停占比 ≥ 20% | 系统性风险事件（历史极罕见） |
| `ELEVATED` | 跌停占比 ≥ 5% | 风险抬升 |
| `NORMAL` | 其余 | 常态 |

阈值取自**历史分布**而非结果调优：常态日跌停占比约 1%，而极端日达 28%~78%（见模块自检输出）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# 事前固定的阈值 —— 不得依据回测结果调整
EXTREME_LIMIT_DOWN_RATIO = 0.20
ELEVATED_LIMIT_DOWN_RATIO = 0.05
DEFAULT_LOOKBACK = 250
# 涨停价/跌停价的舍入容差（与 exchange_rules 的 round(...,2) 口径一致）
_PRICE_EPS = 0.005


def _f(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _limit_down(close: float, prev_close: Optional[float], limit_ratio: float) -> bool:
    """当日是否跌停（`close` 触及跌停价）。``prev_close`` 缺失或 ``limit_ratio<=0`` 时返回 False。"""
    if prev_close is None or prev_close <= 0 or limit_ratio <= 0:
        return False
    limit_down_price = round(prev_close * (1.0 - limit_ratio), 2)
    return close <= limit_down_price + _PRICE_EPS


def _percentile_rank(history: Sequence[float], value: float) -> Optional[float]:
    """``value`` 在 ``history`` 中的分位（0~1）。历史为空返回 ``None``。"""
    if not history:
        return None
    below = sum(1 for x in history if x < value)
    return below / len(history)


def compute_market_risk(
    bars_by_code: Dict[str, List[Dict[str, Any]]],
    *,
    lookback: int = DEFAULT_LOOKBACK,
    min_cross_section: int = 50,
) -> Dict[str, Dict[str, Any]]:
    r"""逐日计算市场级风险状态。

    :param bars_by_code: ``{code: [bar, ...]}``，每个 bar 需含
        ``date`` / ``close`` / ``amount``，建议含逐日 ``limit_ratio``。
    :param lookback: 成交额分位的滚动窗口（**不含当日**，避免自我参照）。
    :param min_cross_section: 当日有行情的股票数低于此值时该日判为数据不足，状态置 ``None``。

    :return: ``{date: {"limit_down_ratio", "amount_percentile", "state",
        "limit_down_count", "cross_section"}}``，按日期升序。

    **PIT 正确**：每个日期的指标只使用该日及之前的数据；状态在当日收盘后确定。
    """
    if not bars_by_code:
        return {}

    # 逐日聚合：跌停家数、有行情家数、全市场成交额
    cross_section: Dict[str, int] = {}
    limit_down_count: Dict[str, int] = {}
    total_amount: Dict[str, float] = {}

    for code in sorted(bars_by_code):
        prev_close: Optional[float] = None
        for bar in bars_by_code[code]:
            day = str(bar.get("date") or "")
            if not day:
                continue
            close = _f(bar.get("close"))
            if close is None:
                prev_close = None          # 行情缺口 → 断开前收，避免用隔日价判跌停
                continue
            lr = _f(bar.get("limit_ratio")) or 0.0
            cross_section[day] = cross_section.get(day, 0) + 1
            if _limit_down(close, prev_close, lr):
                limit_down_count[day] = limit_down_count.get(day, 0) + 1
            amt = _f(bar.get("amount"))
            if amt is not None and amt > 0:
                total_amount[day] = total_amount.get(day, 0.0) + amt
            prev_close = close

    days: List[str] = sorted(cross_section)
    out: Dict[str, Dict[str, Any]] = {}
    amt_hist: List[float] = []          # 滚动窗（不含当日）

    for day in days:
        n = cross_section[day]
        if n < min_cross_section:
            out[day] = {"limit_down_ratio": None, "amount_percentile": None,
                        "state": None, "limit_down_count": limit_down_count.get(day, 0),
                        "cross_section": n}
            # 数据不足日仍把成交额推进窗口（它是真实观测），但不产出状态
            amt = total_amount.get(day)
            if amt is not None:
                amt_hist.append(amt)
                if len(amt_hist) > lookback:
                    amt_hist.pop(0)
            continue

        ratio = limit_down_count.get(day, 0) / n
        amt = total_amount.get(day)
        # ⚠️ 分位用**不含当日**的历史窗 —— 否则当日成交额自己参与排名，产生自我参照
        pct = _percentile_rank(amt_hist[-lookback:], amt) if amt is not None else None

        if ratio >= EXTREME_LIMIT_DOWN_RATIO:
            state = "EXTREME"
        elif ratio >= ELEVATED_LIMIT_DOWN_RATIO:
            state = "ELEVATED"
        else:
            state = "NORMAL"

        out[day] = {"limit_down_ratio": round(ratio, 6),
                    "amount_percentile": (round(pct, 4) if pct is not None else None),
                    "state": state,
                    "limit_down_count": limit_down_count.get(day, 0),
                    "cross_section": n}

        if amt is not None:
            amt_hist.append(amt)
            if len(amt_hist) > lookback:
                amt_hist.pop(0)

    return out


def load_bars_for_risk(dataset_dir: str, codes: Optional[Iterable[str]] = None,
                       *, max_stocks: int = 0,
                       min_rows: int = 200) -> Dict[str, List[Dict[str, Any]]]:
    """从 v3 数据集加载**最小必要字段**（date/close/amount/limit_ratio）。

    刻意不走 `load_certified_csv`：市场级指标不需要 OHLC 全字段，
    且要对 5,667 只股票快速扫描。
    """
    import csv as _csv

    stock_dir = os.path.join(dataset_dir, "stocks")
    if codes is None:
        codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                       if f.endswith(".csv") and f[:-4].isdigit())
    codes = list(codes)
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
                                 "amount": r.get("amount"),
                                 "limit_ratio": r.get("limit_ratio")})
        except OSError:
            continue
        if len(rows) >= min_rows:
            out[c] = rows
    return out


def build_market_filter(risk_by_day: Dict[str, Dict[str, Any]],
                        *,
                        block_states: Tuple[str, ...] = ("EXTREME",),
                        cooldown_days: int = 0,
                        trading_days: Optional[Sequence[str]] = None):
    r"""把逐日风险状态包成 ``portfolio_backtest`` 的 ``candidate_filter``。

    签名 ``(code, hist, day) -> bool``：返回 ``False`` 表示该股当日**不进候选池**。

    ## ⚠️ 与 ``build_market_gate``（position_scaler）的语义差异 —— 这是关键

    | | `position_scaler`（gate） | `candidate_filter`（filter） |
    |---|---|---|
    | 签名 | `(day) -> float` | `(code, hist, day) -> bool` |
    | 阻断方式 | **新开仓预算 = 0** → 当日**不建仓** | 该股**不进候选池** → 系统**顺位选下一只** |
    | 全池阻断时 | 空仓 | 候选池空 → 空仓（**等价**） |
    | 部分阻断时 | 不适用（无逐股能力） | **换股**，持仓数可能仍填满 → **交易数可能上升** |
    | 卖出 | 不影响 | 不影响 |

    **三条必须注意的坑**：

    1. **「排除全池」才等价于「不开仓」**。若只想在风险日少买，
       用 filter 会变成**换股**（买排名更低的票），与「降敞口」不是一回事。
    2. **filter 可能增加交易数**（换股 = 卖出 + 买入），
       而项目已测出**成本拖累 16.58pp/年**是最大确定性损耗 —— 换股会**加剧**它。
       gate 则直接减少建仓，不产生额外交易。
    3. **`candidate_filter` 在 `portfolio_backtest` 里对每只股票逐日调用**，
       故本函数内**不做任何 I/O**（预计算查表），否则回测会慢几个数量级。

    :param cooldown_days: 同 ``build_market_gate``，冷却交易日数（0 = 关闭）。
    :param trading_days: 交易日序列（升序），``cooldown_days > 0`` 时必需。
    """
    days_sorted: List[str] = sorted(trading_days) if trading_days else []
    day_index = {d: i for i, d in enumerate(days_sorted)}

    cooled: set = set()
    if cooldown_days > 0 and days_sorted:
        block_idx = [day_index[d] for d in days_sorted
                     if (risk_by_day.get(d) or {}).get("state") in block_states]
        for i in block_idx:
            for k in range(i, min(i + cooldown_days + 1, len(days_sorted))):
                cooled.add(days_sorted[k])

    # 预计算「被阻断的日期集合」—— 回测热路径里只做集合查找，零 I/O
    blocked_days: set = {
        d for d, v in risk_by_day.items()
        if (v or {}).get("state") in block_states
    } | cooled

    def flt(code: str, hist: List[Dict[str, Any]], day: str) -> bool:
        # 注意：`code` / `hist` 刻意未使用 —— 市场级 filter 是**全池**判定，
        # 不区分个股。若将来要做「风险日只排除高波动股」，才需要读 hist。
        del code, hist
        return str(day) not in blocked_days

    return flt


def build_market_gate(risk_by_day: Dict[str, Dict[str, Any]],
                      *,
                      block_states: Tuple[str, ...] = ("EXTREME",),
                      reduce_states: Tuple[str, ...] = ("ELEVATED",),
                      reduce_scale: float = 0.5,
                      cooldown_days: int = 0,
                      trading_days: Optional[Sequence[str]] = None):
    r"""把逐日风险状态包成 ``portfolio_backtest`` 可用的 ``position_scaler``。

    返回 ``callable(day) -> float``（0~1 的新开仓预算缩放系数）：
    ``block_states`` 中的状态返回 0.0（**不建仓**），``reduce_states`` 返回 ``reduce_scale``，
    其余返回 1.0。**未知日期（无状态）返回 1.0** —— 缺失即不干预，不猜测。

    ## ⚠️ 为什么需要 ``cooldown_days``（2026-09-30 实测教训）

    首版只按「**当日**状态」缩放。但 `position_scaler` 只在**当日**生效，
    而策略每 20 日才调仓一次 —— **EXTREME 日落在调仓日上的概率仅约 1/20**。
    实测 A/B：`2024-01-02` 起的窗口内含 2 个 EXTREME 日（2024-02-05、2025-04-07），
    但 **Δ = +0.00pp、交易数与回撤完全相同** —— **门根本没被触发**。

    修正：``cooldown_days > 0`` 时，某日处于 ``block_states`` 会使其后的
    ``cooldown_days`` 个**交易日**（需传 ``trading_days``）同样被阻断。
    这更符合「系统性风险事件」的语义 —— **踩踏不是一日事件，余波持续数周**。

    :param cooldown_days: 阻断状态的冷却交易日数。**0 = 关闭冷却（首版行为）**。
    :param trading_days: 交易日序列（升序）。``cooldown_days > 0`` 时必需。
    """
    days_sorted: List[str] = sorted(trading_days) if trading_days else []
    day_index = {d: i for i, d in enumerate(days_sorted)}

    # 预计算：哪些交易日处于冷却窗内
    cooled: set = set()
    if cooldown_days > 0 and days_sorted:
        block_idx = [day_index[d] for d in days_sorted
                     if (risk_by_day.get(d) or {}).get("state") in block_states]
        for i in block_idx:
            for k in range(i, min(i + cooldown_days + 1, len(days_sorted))):
                cooled.add(days_sorted[k])

    def scale(day: str) -> float:
        st = (risk_by_day.get(str(day)) or {}).get("state")
        if st in block_states:
            return 0.0
        if str(day) in cooled:
            return 0.0
        if st in reduce_states:
            return reduce_scale
        return 1.0

    return scale
