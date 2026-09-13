# -*- coding: utf-8 -*-
"""Deterministic A-share factor layer used before any LLM judgement.

Only computes from supplied historical bars. Missing inputs remain missing;
there is no synthetic fill. This is intentionally small and dependency-free.
"""
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Dict, List


def _valid(values):
    return [float(x) for x in values if x is not None]


def _returns(closes):
    c = _valid(closes)
    return [(c[i] / c[i - 1] - 1.0) for i in range(1, len(c)) if c[i - 1] > 0]


def compute_factors(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not bars:
        return {"status": "insufficient_data", "factors": {}}

    # 复权口径安全检查：不复权（raw）数据跨除权日会跳价，
    # 导致动量/回撤因子产生虚假信号。
    adjust = getattr(bars, "adjust", None) or getattr(bars, "source", None)
    warnings = []
    if adjust in ("raw", "tdx_local_raw"):
        warnings.append("raw_unadjusted_data: 因子可能因除权跳价失真，仅供形态参考")

    ordered = sorted(bars, key=lambda x: str(x.get("trade_date") or x.get("date") or ""))
    closes = [b.get("close") for b in ordered]
    vols = [b.get("volume") for b in ordered]
    amounts = [b.get("amount") for b in ordered]
    rets = _returns(closes)
    out: Dict[str, Any] = {"status": "ok", "factors": {}}
    if warnings:
        out["warnings"] = warnings
    if len(rets) >= 5:
        out["factors"]["momentum_5d"] = (closes[-1] / closes[-6] - 1) if closes[-6] else None
    if len(rets) >= 10:
        out["factors"]["momentum_10d"] = (closes[-1] / closes[-11] - 1) if closes[-11] else None
    if len(rets) >= 20:
        out["factors"]["momentum_20d"] = (closes[-1] / closes[-21] - 1) if closes[-21] else None
        out["factors"]["realized_vol_20d"] = pstdev(rets[-20:]) * sqrt(252)
    if len(rets) >= 60:
        out["factors"]["momentum_60d"] = (closes[-1] / closes[-61] - 1) if closes[-61] else None
        out["factors"]["realized_vol_60d"] = pstdev(rets[-60:]) * sqrt(252)
    if len(rets) >= 20:
        m5 = (closes[-1] / closes[-6] - 1) if closes[-6] else None
        m20 = (closes[-1] / closes[-21] - 1) if closes[-21] else None
        if m5 is not None and m20 is not None:
            out["factors"]["momentum_accel_5_20"] = m5 - (m20 / 4.0)
        prior20 = _valid(closes[-21:-1])
        out["factors"]["breakout_20d"] = (closes[-1] / max(prior20) - 1) if prior20 else None
        highs = _valid([b.get("high") for b in ordered[-20:]])
        lows = _valid([b.get("low") for b in ordered[-20:]])
        if highs and lows and max(highs) > 0:
            out["factors"]["range_pct_20d"] = (max(highs) - min(lows)) / max(highs)
    if len(closes) >= 20:
        window = _valid(closes[-20:])
        out["factors"]["drawdown_20d"] = closes[-1] / max(window) - 1 if window else None
    if len(vols) >= 5:
        vv = _valid(vols[-5:])
        out["factors"]["volume_ratio_5d"] = vv[-1] / mean(vv[:-1]) if len(vv) >= 2 and mean(vv[:-1]) else None
    if len(vols) >= 20:
        vv = _valid(vols[-20:])
        out["factors"]["volume_ratio_20d"] = vv[-1] / mean(vv[:-1]) if len(vv) >= 2 and mean(vv[:-1]) else None
    if len(amounts) >= 5:
        aa = _valid(amounts[-5:])
        out["factors"]["amount_ratio_5d"] = aa[-1] / mean(aa[:-1]) if len(aa) >= 2 and mean(aa[:-1]) else None
    turnovers = [b.get("turnover") for b in ordered[-20:]]
    tv = _valid(turnovers)
    if tv:
        out["factors"]["turnover_mean_20d"] = mean(tv)
    return out


def score_candidate(factors: Dict[str, Any]) -> Dict[str, Any]:
    f = factors.get("factors", {})
    score = 50.0
    reasons = []
    m5 = f.get("momentum_5d")
    m20 = f.get("momentum_20d")
    vol = f.get("realized_vol_20d")
    dd = f.get("drawdown_20d")
    vr = f.get("volume_ratio_5d")
    if m5 is not None:
        score += max(-10, min(10, m5 * 100))
        reasons.append("5日动量" + ("偏强" if m5 > 0 else "偏弱"))
    if m20 is not None:
        score += max(-8, min(8, m20 * 40))
        reasons.append("20日动量" + ("偏强" if m20 > 0 else "偏弱"))
    if dd is not None and dd < -0.10:
        score -= 8
        reasons.append("近20日回撤较大")
    if vol is not None and vol > 0.60:
        score -= 6
        reasons.append("实现波动率偏高")
    if vr is not None and vr > 2.0:
        reasons.append("成交量显著放大，需结合涨跌停结构复核")
    return {"score": round(max(0, min(100, score)), 2), "reasons": reasons}
