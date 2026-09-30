# -*- coding: utf-8 -*-
"""A股流动性过滤与动态滑点模型。

优先使用真实成交额 amount。对于公开数据源只提供 OHLCV、且 volume 按 A 股常见“手”计量的情况，
可显式从价格和成交量估算成交额，避免把缺失 amount 错误当成“零流动性”。
"""

def _bar_amount(row):
    a=row.get('amount')
    if a not in (None,''):
        try:
            a=float(a)
            if a>0: return a
        except Exception:
            pass
    # Fallback: OHLCV-only A-share feeds commonly report volume in lots (1 lot=100 shares).
    try:
        close=float(row.get('close') or 0)
        volume=float(row.get('volume') or 0)
        if close>0 and volume>0:
            return close*volume*100.0
    except Exception:
        pass
    return 0.0

def avg_amount(rows, n=20):
    vals=[_bar_amount(r) for r in rows[-n:]]
    return sum(vals)/len(vals) if vals else 0.0

def is_liquid(rows, min_avg_amount=100_000_000, n=20):
    return avg_amount(rows,n) >= min_avg_amount

def dynamic_slippage(rows, base=0.0005):
    a=avg_amount(rows,20)
    if a>=1_000_000_000: return min(base,0.0003)
    if a>=300_000_000: return max(base,0.0005)
    if a>=100_000_000: return max(base,0.0010)
    return max(base,0.0030)


def sqrt_impact(rows, notional, k=1.0):
    """Almgren-Chriss sqrt 律冲击成本（单边，收益率计）。

    impact = k · σ_daily · √(Q / V)
      Q = 本笔名义金额，V = 20 日均成交额，σ = 20 日日收益标准差
    地板 1bp。k 事前固定（默认 1.0，覆盖临时冲击的保守估计）。
    """
    import math as _m
    import statistics as _st
    amts = [float(b["amount"] or 0) for b in rows[-20:] if b.get("amount")]
    V = sum(amts) / len(amts) if amts else 0.0
    if V <= 0 or notional <= 0:
        return 0.0030
    closes = [float(b["close"]) for b in rows[-21:] if b.get("close")]
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))
            if closes[i - 1] > 0]
    sigma = _st.pstdev(rets) if len(rets) > 1 else 0.0
    impact = k * sigma * _m.sqrt(notional / V)
    return max(impact, 0.0001)
