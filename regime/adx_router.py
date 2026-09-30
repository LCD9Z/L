# -*- coding: utf-8 -*-
"""ADX 三档市场状态路由（自 KHunter `trading/regime_router.py` 移植并本地化裁剪）。

## 与 KHunter 原实现的差异（有意为之，勿"补齐"）

- KHunter 以全A指数（000985.CSI）联动「选股策略 / 择时策略 / 仓位系数 / 买入执行方式」
  四件事；本地项目没有 KHunter 的策略命名体系，且本地数据集基准为 000300，
  因此**只移植「状态识别 → 仓位系数」这一层**。信号、阈值、持仓周期、成本一律不动，
  与本项目的「只改一个变量做实验」方法论一致。
- 状态口径与 KHunter 2026-09-11 简化版一致：仅按 ADX 强度三档
  （震荡 < 20 / 萌芽 20~25 / 明确 >= 25），不再区分多空方向。
- 默认关闭（enabled=False）；任何异常 / 数据不足一律回退为不缩放
  （position_ratio=1.0，source 说明原因），不阻断主流程 —— 与 KHunter
  「异常回退 disabled」的设计一致。
- 无状态文件：confirm_days 平滑由历史序列**确定性回放**推导，便于测试与复算。

## 防前视

ADX 本身只使用历史数据（Wilder 平滑均为后向算子），因此对整段序列一次性预计算
ADX 后，`decide(date)` 只查询 `date` 及之前的值，天然无未来函数。
confirm_days 切换判定同样只回放 `date` 及之前的标签序列。

## 仓位系数（KHunter 2026-09-11 默认，未经本地调优）

- 明确（ADX >= 25）→ 1.0（满额开仓预算）
- 萌芽（20 <= ADX < 25）→ 0.5
- 震荡（ADX < 20）→ 0.3

这些阈值与系数来自 KHunter 的样本内决策（其设计文档第 3、4 节），**不是**在本
项目数据上调出的参数。引入后只能做观察性对照，不得据此宣称策略有效性。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------

DEFAULT_POSITION_RATIOS: Dict[str, float] = {
    "明确": 1.0,
    "萌芽": 0.5,
    "震荡": 0.3,
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,          # 默认关闭（与 KHunter Q6 决策一致）
    "adx_period": 14,
    "confirm_days": 1,         # 1 = 即时切换（KHunter 2026-09-11 调整后的默认）
    "oscillation_lt": 20.0,    # ADX < 20 → 震荡
    "trending_ge": 25.0,       # ADX >= 25 → 明确；[20, 25) → 萌芽
    "position_ratios": None,   # None → DEFAULT_POSITION_RATIOS
    "manual_override": None,   # {"regime": "明确"} 或 None
}


@dataclass
class RouteDecision:
    """单日路由决策结果。"""

    as_of: str = ""
    regime: str = ""            # 生效档位（"震荡" | "萌芽" | "明确" | ""）
    raw_regime: str = ""        # 未平滑的即时档位（排查用）
    position_ratio: float = 1.0
    source: str = "disabled"    # auto | manual | disabled | insufficient_data
    adx: Optional[float] = None
    confirm_count: int = 0

    def is_active(self) -> bool:
        return self.source in ("auto", "manual")


# ---------------------------------------------------------------------------
# ADX（Wilder 1978 标准 14 期口径，纯标准库实现）
# ---------------------------------------------------------------------------

def compute_adx_by_date(bars: List[Dict[str, Any]], period: int = 14) -> Dict[str, float]:
    """对 OHLC 序列计算逐日 ADX，返回 {date: adx}。

    bars 需含 date/open/high/low/close（收盘价用于 TR 的前收）。
    数据不足（< 2*period 根）时返回空 dict —— 调用方按"数据不足"处理，
    绝不编造档位。
    """
    n = len(bars)
    if period <= 0 or n < 2 * period:
        return {}
    trs: List[float] = []
    plus_dms: List[float] = []
    minus_dms: List[float] = []
    for i in range(1, n):
        h = float(bars[i]["high"])
        low = float(bars[i]["low"])
        prev_h = float(bars[i - 1]["high"])
        prev_l = float(bars[i - 1]["low"])
        prev_c = float(bars[i - 1]["close"])
        up = h - prev_h
        dn = prev_l - low
        plus_dm = up if (up > dn and up > 0.0) else 0.0
        minus_dm = dn if (dn > up and dn > 0.0) else 0.0
        tr = max(h - low, abs(h - prev_c), abs(low - prev_c))
        trs.append(tr)
        plus_dms.append(plus_dm)
        minus_dms.append(minus_dm)

    m = n - 1  # TR/DM 序列长度
    if m < 2 * period - 1:
        return {}

    out: Dict[str, float] = {}
    s_tr = sum(trs[:period])
    s_pdm = sum(plus_dms[:period])
    s_ndm = sum(minus_dms[:period])
    dx_values: List[float] = []  # dx_values[k] 对应 bar 索引 k + period
    for k in range(m - period + 1):
        if k > 0:
            j = k + period - 1  # 本步并入的 TR/DM 下标
            s_tr = s_tr - s_tr / period + trs[j]
            s_pdm = s_pdm - s_pdm / period + plus_dms[j]
            s_ndm = s_ndm - s_ndm / period + minus_dms[j]
        pdi = 100.0 * s_pdm / s_tr if s_tr else 0.0
        ndi = 100.0 * s_ndm / s_tr if s_tr else 0.0
        denom = pdi + ndi
        dx = 100.0 * abs(pdi - ndi) / denom if denom else 0.0
        dx_values.append(dx)

    # ADX：前 period 个 DX 取均值，其后 Wilder 平滑
    if len(dx_values) < period:
        return {}
    adx = sum(dx_values[:period]) / period
    out[str(bars[2 * period - 1]["date"])] = adx
    for k in range(period, len(dx_values)):
        adx = (adx * (period - 1) + dx_values[k]) / period
        out[str(bars[k + period]["date"])] = adx
    return out


def classify_regime(adx: float, oscillation_lt: float = 20.0, trending_ge: float = 25.0) -> str:
    """ADX 强度三档（KHunter 2026-09-11 简化口径，仅强度、不分多空）。"""
    if adx < oscillation_lt:
        return "震荡"
    if adx < trending_ge:
        return "萌芽"
    return "明确"


def _replay_committed(labels: List[str], confirm_days: int) -> List[str]:
    """确定性回放「连续 confirm_days 日同档才切换」的平滑。"""
    if confirm_days <= 1:
        return list(labels)
    committed = labels[0]
    candidate = labels[0]
    streak = 1
    out = [committed]
    for lbl in labels[1:]:
        if lbl == candidate:
            streak += 1
        else:
            candidate = lbl
            streak = 1
        if lbl != committed and streak >= confirm_days:
            committed = lbl
        out.append(committed)
    return out


# ---------------------------------------------------------------------------
# 路由器
# ---------------------------------------------------------------------------

class RegimeRouter:
    """ADX 自适应路由器（仓位叠加层）。

    用法::

        router = RegimeRouter({"enabled": True}, index_bars=benchmark_bars)
        decision = router.decide("2024-06-03")
        scaler = router.make_position_scaler()
        result = portfolio_backtest(data, position_scaler=scaler, ...)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 index_bars: Optional[List[Dict[str, Any]]] = None):
        merged = dict(DEFAULT_CONFIG)
        if config:
            unknown = set(config) - set(DEFAULT_CONFIG)
            if unknown:
                raise ValueError(f"未知的 regime 配置项: {sorted(unknown)}")
            merged.update(config)
        if merged["position_ratios"] is None:
            merged["position_ratios"] = dict(DEFAULT_POSITION_RATIOS)
        self.config = merged
        self._adx_by_date: Dict[str, float] = {}
        self._labels: List[str] = []
        self._dates: List[str] = []
        if index_bars:
            self.set_index_bars(index_bars)

    # -- 配置与数据 ---------------------------------------------------------

    def set_index_bars(self, bars: List[Dict[str, Any]]) -> None:
        """设置指数 OHLC 序列并一次性预计算逐日 ADX（防前视见模块 docstring）。"""
        period = int(self.config["adx_period"])
        try:
            self._adx_by_date = compute_adx_by_date(bars, period=period)
        except Exception:
            # 任何计算异常都回退为"无状态数据"，绝不编造档位
            self._adx_by_date = {}
        self._dates = sorted(self._adx_by_date)
        self._labels = [
            classify_regime(self._adx_by_date[d],
                            float(self.config["oscillation_lt"]),
                            float(self.config["trending_ge"]))
            for d in self._dates
        ]

    @property
    def enabled(self) -> bool:
        return bool(self.config["enabled"])

    # -- 决策 ---------------------------------------------------------------

    def decide(self, trade_date: str) -> RouteDecision:
        trade_date = str(trade_date)
        if not self.enabled:
            return RouteDecision(as_of=trade_date, source="disabled", position_ratio=1.0)

        override = self.config.get("manual_override") or {}
        if override.get("regime"):
            regime = str(override["regime"])
            ratio = self.config["position_ratios"].get(regime, 1.0)
            return RouteDecision(as_of=trade_date, regime=regime, raw_regime=regime,
                                 position_ratio=float(ratio), source="manual")

        # 防前视：只使用 trade_date 及之前的 ADX 值
        idx = -1
        for i, d in enumerate(self._dates):
            if d <= trade_date:
                idx = i
            else:
                break
        if idx < 0:
            return RouteDecision(as_of=trade_date, source="insufficient_data", position_ratio=1.0)

        adx = self._adx_by_date[self._dates[idx]]
        raw = self._labels[idx]
        committed = _replay_committed(self._labels[: idx + 1], int(self.config["confirm_days"]))[-1]
        # 当日原始标签的连续天数（报告用）
        count = 0
        for lbl in reversed(self._labels[: idx + 1]):
            if lbl == raw:
                count += 1
            else:
                break
        ratio = float(self.config["position_ratios"].get(committed, 1.0))
        return RouteDecision(as_of=trade_date, regime=committed, raw_regime=raw,
                             position_ratio=ratio, source="auto", adx=adx, confirm_count=count)

    def make_position_scaler(self) -> Callable[[str], float]:
        """返回可直接传给 `portfolio_backtest(position_scaler=...)` 的回调。"""
        def scaler(day: str) -> float:
            return self.decide(day).position_ratio
        return scaler


def load_config(path: str) -> Dict[str, Any]:
    """从 JSON 文件加载配置（缺文件返回空 dict，由默认配置兜底）。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("regime 配置必须是 JSON 对象")
    return data
