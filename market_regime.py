# -*- coding: utf-8 -*-
"""A股市场环境识别：强势/震荡/弱势，供选股和风控统一调用。

## 离线支持（2026-09-30 新增）

原实现**只能走实时接口**（`data_fetcher.fetch_kline`）→ **离线回测跑不了**。
这一点在 2026-09-30 的专家圆桌审查中被**信号派首席**点名：

> 「`market_regime.py` 依赖 `fetch_kline`（实时），**离线跑不了** →
> 需改为吃 `benchmark.csv`」

现在两条路径并存：

* **默认**（``bars=None``）：仍走 `fetch_kline`，供每日实盘调用，行为不变；
* **注入**（``bars={code: [bar, ...]}``）：**完全离线**，供回测使用。

> ⚠️ 注意：本模块只做「指数均线状态」这一层；**市场级风险门**
> （跌停家数占比 + 成交额分位）见 `risk/market_risk_gate.py` ——
> 后者是圆桌三位专家共识的更直接处方，且**天然离线**。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

BENCHMARKS = {
    "sh000001": "上证指数",
    "sh000300": "沪深300",
    "sz399006": "创业板指",
}

MIN_BARS = 65


def _ma(values: List[float], n: int) -> Optional[float]:
    return sum(values[-n:]) / n if len(values) >= n else None


def _bars_for(code: str, *, bars: Optional[Dict[str, List[Dict[str, Any]]]],
              limit: int) -> List[Dict[str, Any]]:
    """取某指数的 K 线：注入优先，否则走实时接口（惰性导入，离线环境不报错）。"""
    if bars is not None:
        return list(bars.get(code) or [])[-limit:]
    from data_fetcher import fetch_kline  # 惰性导入：离线场景不需要它
    return fetch_kline(code, limit=limit, min_quality="medium")


def _one(code: str, name: str, *,
         bars: Optional[Dict[str, List[Dict[str, Any]]]] = None,
         limit: int = 140) -> Dict[str, Any]:
    try:
        rows = _bars_for(code, bars=bars, limit=limit)
    except Exception:                      # 实时接口不可用（离线/无网）→ 诚实降级
        return {"name": name, "available": False, "reason": "data_unavailable"}
    closes = [float(r["close"]) for r in rows if r.get("close") is not None]
    if len(closes) < MIN_BARS:
        return {"name": name, "available": False, "reason": "insufficient_history"}
    last = closes[-1]
    ma20, ma60 = _ma(closes, 20), _ma(closes, 60)
    ret20 = (last / closes[-21] - 1) * 100 if len(closes) >= 21 and closes[-21] else 0.0
    return {"name": name, "available": True, "close": last,
            "ma20": round(ma20, 2) if ma20 is not None else None,
            "ma60": round(ma60, 2) if ma60 is not None else None,
            "ret20": round(ret20, 2),
            "bull": bool(ma20 is not None and ma60 is not None and last > ma20 > ma60),
            "bear": bool(ma20 is not None and ma60 is not None and last < ma20 < ma60)}


def get_market_regime(bars: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                      *, limit: int = 140) -> Dict[str, Any]:
    """识别市场环境。

    :param bars: ``{指数代码: [bar, ...]}``。**传入即为离线模式**（回测用）；
        ``None`` 时走实时接口（实盘用）。
    :param limit: 每只指数取最近多少根 K 线。

    ## ⚠️ 单指数降级（2026-09-30 新增）

    原规则是「**≥2 个指数同时多头/空头**」。但离线数据集 `benchmark.csv`
    **只有沪深300 一个指数**（见 `scripts/build_certified_dataset_v2.py`）——
    于是 `bulls >= 2` **永远为假**，模块在离线场景下**永远返回 RANGE，静默失效**。

    修复方式：可用指数数 ≥2 时沿用原多数规则；**恰好 1 个**时改用单指数规则
    （`close>ma20>ma60` 判 STRONG / `close<ma20<ma60` 判 WEAK），
    并在返回值里显式标注 ``degraded=True`` 与 ``available_indices``，
    使调用方**能看见**这一降级，而不是拿到一个恒为 RANGE 的哑结果。
    """
    details = [_one(c, n, bars=bars, limit=limit) for c, n in BENCHMARKS.items()]
    valid = [x for x in details if x.get("available")]
    n_valid = len(valid)
    if n_valid == 0:
        return {"regime": "UNKNOWN", "score": 0, "details": details,
                "available_indices": 0, "degraded": False,
                "note": "指数数据不足"}
    bulls = sum(x["bull"] for x in valid)
    bears = sum(x["bear"] for x in valid)
    avg_ret = sum(x["ret20"] for x in valid) / n_valid

    if n_valid >= 2:
        # 原多数规则（≥2 个指数一致）
        if bulls >= 2 and avg_ret > 2:
            regime, score = "STRONG", 2
        elif bears >= 2 and avg_ret < -2:
            regime, score = "WEAK", -2
        else:
            regime, score = "RANGE", 0
        degraded = False
    else:
        # 单指数降级规则：**显式标注**，不静默
        only = valid[0]
        if only["bull"] and avg_ret > 2:
            regime, score = "STRONG", 2
        elif only["bear"] and avg_ret < -2:
            regime, score = "WEAK", -2
        else:
            regime, score = "RANGE", 0
        degraded = True

    note = {"STRONG": "趋势策略可用，但仍禁止追一字涨停",
            "RANGE": "降低追涨，优先回踩和低风险买点",
            "WEAK": "显著降低仓位，严格控制新开仓"}[regime]
    if degraded:
        note += "（⚠️ 仅 1 个指数可用，为单指数降级判定，稳健性弱于三指数多数规则）"
    return {"regime": regime, "score": score, "details": details,
            "available_indices": n_valid, "degraded": degraded, "note": note}
