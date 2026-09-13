# -*- coding: utf-8 -*-
"""公共常量与纯函数：字段表、代码规范化、数值解析/格式化、日期工具。

由 data_fetcher.py 拆分而来（对外 API 不变，实现下沉到 fetch/ 包）。
"""
from datetime import date, timedelta


_I0, _I1, _I2, _I3, _I4, _I5, _I6, _I7, _I30 = (0, 1, 2, 3, 4, 5, 6, 7, 30)



# 东财实时行情字段（f43=最新价 f44=最高 f45=最低 f46=今开 f47=成交量 f48=成交额
# f57=代码 f58=名称 f59=昨收 f60=昨收 f86=时间 f107=市场 f116=总市值 f117=流通市值
# f162=PE f167=PB f168=换手 f169=涨跌额 f170=涨跌幅 f171=振幅）
QUOTE_FIELDS = (
    "f43,f44,f45,f46,f47,f48,f57,f58,f59,f60,f86,"
    "f107,f116,f117,f162,f167,f168,f169,f170,f171"
)



def _empty_quote(code: str) -> dict:
    """空行情结构（字段齐全、缺数据为 None，便于下游统一处理）。"""
    return {
        "src": "",
        "code": code,
        "name": None,
        "price": None,
        "prev_close": None,
        "open": None,
        "high": None,
        "low": None,
        "change": None,
        "change_pct": None,
        "volume": None,
        "amount": None,
        "total_mv": None,
        "float_mv": None,
        "pe": None,
        "pb": None,
        "turnover": None,
        "amplitude": None,
        "quote_time": None,
        "note": "",
    }



def normalize_code(code: str):
    """规范化股票代码：返回 (标准代码, 东财secid, 腾讯前缀代码)。

    规则：sh/sz/bj 前缀优先；否则 6/9 开头→沪(1.)，0/3/2 开头→深(0.)，8/4 开头→北(0.)。
    """
    code = code.strip().lower()
    if code.startswith("sh"):
        c = code[_I2:]
        return c, f"1.{c}", f"sh{c}"
    if code.startswith("sz"):
        c = code[_I2:]
        return c, f"0.{c}", f"sz{c}"
    if code.startswith("bj"):
        c = code[_I2:]
        return c, f"0.{c}", f"bj{c}"
    if code.startswith(("6", "9")):
        return code, f"1.{code}", f"sh{code}"
    if code.startswith(("0", "3", "2")):
        return code, f"0.{code}", f"sz{code}"
    if code.startswith(("8", "4")):
        return code, f"0.{code}", f"bj{code}"
    return code, f"1.{code}", f"sh{code}"



def _d(v, scale=100):
    """东财字段除以精度再四舍五入；None/'-' 视为缺数据。"""
    if v is None:
        return None
    try:
        return round(float(v) / scale, 2)
    except (ValueError, TypeError):
        return None



def _safe_float(v):
    """安全转 float：None/'-'/'空串' 等占位值视为缺数据返回 None。"""
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return None



def _fmt_amount(v):
    """格式化金额（元），支持大数与 NaN 防御。"""
    if v is None:
        return "未知"
    try:
        n = float(v)
    except (ValueError, TypeError):
        return "未知"
    if n != n or n in (float("inf"), float("-inf")):
        return "未知"
    if abs(n) >= 1e12:
        return f"{n / 1e12:.2f} 万亿"
    if abs(n) >= 1e8:
        return f"{n / 1e8:.2f} 亿"
    if abs(n) >= 1e4:
        return f"{n / 1e4:.2f} 万"
    return f"{n:.0f}"



def _days_ago(n):
    """N 个自然日前的日期，格式 YYYYMMDD。n=0 表示今天。"""
    d = date.today() - timedelta(days=n)
    return d.strftime("%Y%m%d")
