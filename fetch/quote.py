# -*- coding: utf-8 -*-
"""实时行情：东财（双域名重试）+ 腾讯兜底 + 统一入口（带缓存）。

由 data_fetcher.py 拆分而来（对外 API 不变，实现下沉到 fetch/ 包）。
"""
import json
from typing import Optional
from .common import (
    QUOTE_FIELDS,
    _I0,
    _I1,
    _I2,
    _I30,
    _d,
    _empty_quote,
    _safe_float,
    normalize_code,
)
from .transport import (
    _cache_get,
    _cache_set,
    _http_get,
)



def fetch_quote_eastmoney(code: str) -> Optional[dict]:
    """东财实时行情，返回统一 dict；失败返回 None。主域名不稳定，双域名重试。"""
    _, secid, _ = normalize_code(code)
    hosts = ["push2.eastmoney.com", "push2delay.eastmoney.com"]
    for host in hosts:
        url = (
            f"https://{host}/api/qt/stock/get?secid={secid}"
            f"&fields={QUOTE_FIELDS}"
        )
        text = _http_get(url)
        if not text:
            continue
        try:
            data = json.loads(text).get("data")
        except json.JSONDecodeError:
            continue
        if not data:
            continue
        q = _empty_quote(str(data.get("f57") or ""))
        q["src"] = f"eastmoney/{host.split('.')[_I0]}"
        q["name"] = data.get("f58")
        q["price"] = _d(data.get("f43"))
        q["prev_close"] = _d(data.get("f60"))
        q["open"] = _d(data.get("f46"))
        q["high"] = _d(data.get("f44"))
        q["low"] = _d(data.get("f45"))
        q["change"] = _d(data.get("f169"))
        q["change_pct"] = _d(data.get("f170"))
        q["volume"] = data.get("f47")          # 手
        q["amount"] = data.get("f48")          # 元
        q["total_mv"] = _safe_float(data.get("f116"))
        q["float_mv"] = _safe_float(data.get("f117"))
        q["pe"] = _d(data.get("f162"))
        q["pb"] = _d(data.get("f167"))
        q["turnover"] = _d(data.get("f168"))
        q["amplitude"] = _d(data.get("f171"))
        q["quote_time"] = data.get("f86")
        # 东财未给涨跌时按价格自算（保证可复核）
        if q["change_pct"] is None and q["price"] and q["prev_close"]:
            q["change_pct"] = round((q["price"] - q["prev_close"]) / q["prev_close"] * 100, 2)
        if q["change"] is None and q["price"] and q["prev_close"]:
            q["change"] = round(q["price"] - q["prev_close"], 2)
        return q
    return None



def fetch_quote_tencent(tx_code: str) -> Optional[dict]:
    """腾讯行情（GBK），统一换算后返回。失败返回 None。"""
    url = f"https://qt.gtimg.cn/q={tx_code}"
    text = _http_get(url, headers={"Referer": "https://gu.qq.com/"}, decode="gbk")
    if not text or "=" not in text:
        return None
    payload = text.split("=", 1)[_I1].strip().strip(";").strip('"')
    parts = payload.split("~")
    # 腾讯字段（0-based）：名称=1 代码=2 最新=3 昨收=4 今开=5 成交量=6
    # 涨跌额=31 涨跌幅=32 最高=33 最低=34 成交额(万)=37 换手=38 PE=39 振幅=43 流通市值(亿)=44 总市值(亿)=45 PB=46
    if len(parts) < 47:
        return None

    def f(idx):
        try:
            v = parts[idx].strip()
            return float(v) if v not in ("", "-") else None
        except ValueError:
            return None

    q = _empty_quote(parts[_I2] if len(parts) > 2 else "")
    q["src"] = "tencent"
    q["name"] = parts[_I1] if len(parts) > 1 else None
    q["price"] = f(3)
    q["prev_close"] = f(4)
    q["open"] = f(5)
    q["high"] = f(33)
    q["low"] = f(34)
    q["change"] = f(31)
    q["change_pct"] = f(32)
    q["volume"] = f(6)                       # 手
    _amt = f(37)                             # 万元 → 元
    q["amount"] = _amt * 10000 if _amt is not None else None
    _tmv = f(45)                             # 亿元 → 元
    q["total_mv"] = _tmv * 1e8 if _tmv is not None else None
    _fmv = f(44)
    q["float_mv"] = _fmv * 1e8 if _fmv is not None else None
    q["pe"] = f(39)
    q["pb"] = f(46)
    q["turnover"] = f(38)
    q["amplitude"] = f(43)
    q["quote_time"] = parts[_I30] if len(parts) > 30 else None
    return q



def fetch_quote(code: str) -> dict:
    """东财优先，腾讯兜底；都失败返回带 note 的空结构。带 30s TTL 缓存。"""
    std, _, tx = normalize_code(code)
    cache_key = "quote:%s" % std
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    q = fetch_quote_eastmoney(code)
    if q and q.get("price") is not None:
        _cache_set(cache_key, q)
        return q
    q2 = fetch_quote_tencent(tx)
    if q2 and q2.get("price") is not None:
        _cache_set(cache_key, q2)
        return q2
    q3 = _empty_quote(std)
    q3["note"] = "行情接口均不可用，未获取到实时数据（请检查网络后重试）"
    return q3
