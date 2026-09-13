# -*- coding: utf-8 -*-
"""A股市场环境识别：强势/震荡/弱势，供选股和风控统一调用。"""
from data_fetcher import fetch_kline

BENCHMARKS = {
    "sh000001": "上证指数",
    "sh000300": "沪深300",
    "sz399006": "创业板指",
}

def _ma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None

def _one(code, name):
    rows = fetch_kline(code, limit=140, min_quality="medium")
    closes = [r.get("close") for r in rows if r.get("close") is not None]
    if len(closes) < 65:
        return {"name": name, "available": False}
    last = closes[-1]
    ma20, ma60 = _ma(closes, 20), _ma(closes, 60)
    ret20 = (last / closes[-21] - 1) * 100 if len(closes) >= 21 and closes[-21] else 0
    return {"name": name, "available": True, "close": last, "ma20": round(ma20, 2), "ma60": round(ma60, 2), "ret20": round(ret20, 2), "bull": last > ma20 > ma60, "bear": last < ma20 < ma60}

def get_market_regime():
    details = [_one(c, n) for c, n in BENCHMARKS.items()]
    valid = [x for x in details if x.get("available")]
    if not valid:
        return {"regime": "UNKNOWN", "score": 0, "details": details, "note": "指数数据不足"}
    bulls = sum(x["bull"] for x in valid)
    bears = sum(x["bear"] for x in valid)
    avg_ret = sum(x["ret20"] for x in valid) / len(valid)
    if bulls >= 2 and avg_ret > 2:
        regime, score = "STRONG", 2
    elif bears >= 2 and avg_ret < -2:
        regime, score = "WEAK", -2
    else:
        regime, score = "RANGE", 0
    return {"regime": regime, "score": score, "details": details,
            "note": {"STRONG":"趋势策略可用，但仍禁止追一字涨停", "RANGE":"降低追涨，优先回踩和低风险买点", "WEAK":"显著降低仓位，严格控制新开仓"}[regime]}
