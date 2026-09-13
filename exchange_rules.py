# -*- coding: utf-8 -*-
"""集中管理A股交易规则；优先使用数据源提供的逐日状态。"""
from decimal import Decimal, ROUND_HALF_UP
from ashare_market import default_limit_ratio

def limit_ratio(code, bar=None):
    if bar:
        for k in ('limit_ratio','limit_pct'):
            if bar.get(k) is not None:
                v=float(bar[k]); return v/100 if v>1 else v
        # 2026规则已发生调整，不能仅凭 is_st 猜测涨跌幅；应由逐日状态字段提供。
    c=str(code).zfill(6)
    return default_limit_ratio(c)

def limit_prices(prev_close, code, bar=None, tick='0.01'):
    if not prev_close or float(prev_close)<=0: return None,None
    p=Decimal(str(prev_close)); r=Decimal(str(limit_ratio(code,bar))); q=Decimal(str(tick))
    up=(p*(Decimal('1')+r)).quantize(q, rounding=ROUND_HALF_UP)
    down=(p*(Decimal('1')-r)).quantize(q, rounding=ROUND_HALF_UP)
    return float(up),float(down)
