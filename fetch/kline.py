# -*- coding: utf-8 -*-
"""历史日K：东财 / 腾讯 / 通达信本地 .day（不复权）三源 + KlineList。

由 data_fetcher.py 拆分而来（对外 API 不变，实现下沉到 fetch/ 包）。
"""
import json
import os
import struct
import time
from datetime import datetime
from typing import Optional
from .common import (
    _I0,
    _I1,
    _I2,
    _I3,
    _I4,
    _I5,
    _I6,
    _I7,
    _days_ago,
    normalize_code,
)
from .transport import (
    _http_get,
)



# 通达信安装根目录（可被环境变量 TDX_ROOT 覆盖）
_TDX_ROOT = os.environ.get("TDX_ROOT", r"D:\new_tdx")



def _fetch_kline_eastmoney(secid, beg, end):
    """东财历史日K（前复权）。返回 [{date,open,...}]，失败返回 []。"""
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&klt=101&fqt=1&beg={beg}&end={end}"
    )
    text = _http_get(url)
    if not text:
        return []
    try:
        data = json.loads(text).get("data")
    except json.JSONDecodeError:
        return []
    klines = (data or {}).get("klines") or []
    out = []
    for ln in klines:
        p = ln.split(",")
        if len(p) < 8:
            continue
        out.append({
            "date": p[_I0],
            "open": float(p[_I1]) if p[_I1] not in ("", "-") else None,
            "close": float(p[_I2]) if p[_I2] not in ("", "-") else None,
            "high": float(p[_I3]) if p[_I3] not in ("", "-") else None,
            "low": float(p[_I4]) if p[_I4] not in ("", "-") else None,
            "volume": float(p[_I5]) if p[_I5] not in ("", "-") else None,
            "amount": float(p[_I6]) if p[_I6] not in ("", "-") else None,
            "amplitude": float(p[_I7]) if p[_I7] not in ("", "-") else None,
        })
    return out



def _fetch_kline_tencent(tx_code, beg_date, end_date):
    """腾讯历史日K（前复权 qfq）兜底。beg/end 为 YYYY-MM-DD。"""
    url = (
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={tx_code},day,{beg_date},{end_date},320,qfq"
    )
    text = _http_get(url, headers={"Referer": "https://gu.qq.com/"})
    if not text:
        return []
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return []
    node = (d.get("data") or {}).get(tx_code) or {}
    rows = node.get("qfqday") or node.get("day") or []
    out = []
    for ln in rows:
        if not ln or len(ln) < 6:
            continue
        try:
            out.append({
                "date": str(ln[_I0]),
                "open": float(ln[_I1]),
                "close": float(ln[_I2]),
                "high": float(ln[_I3]),
                "low": float(ln[_I4]),
                "volume": float(ln[_I5]),
                "amount": None,
                "amplitude": None,
            })
        except (ValueError, TypeError):
            continue
    return out



def _validate_kline_rows(rows):
    """基础OHLC数据质量校验，过滤明显异常行并返回(有效行, 完整率)。"""
    valid = []
    for r in rows or []:
        vals = [r.get(k) for k in ("open", "close", "high", "low")]
        if any(v is None for v in vals):
            continue
        try:
            o, c, h, l = map(float, vals)
        except (TypeError, ValueError):
            continue
        if min(o, c, h, l) <= 0 or h < max(o, c) or l > min(o, c):
            continue
        valid.append(r)
    ratio = len(valid) / len(rows) if rows else 0.0
    return valid, ratio



class KlineList(list):
    """带来源/质量标注的 K 线列表（兼容 list 接口，切片时保留全部元数据）。

    元数据字段显式声明为类属性（而非运行时动态挂载），原因有二：
      1. 类型检查可识别，避免下游读到不存在的属性；
      2. __getitem__ 切片时必须逐个复制 —— 否则 `kline[-30:]` 会静默丢掉
         data_quality，下游 getattr 兜底会得到 "unknown" 而非真实质量。
    """

    source: Optional[str] = None         # "eastmoney_qfq" / "tencent_qfq" / "tdx_local_raw"
    adjust: Optional[str] = None         # "qfq"（前复权）/ "raw"（不复权）
    quality_ratio: float = 0.0           # 有效行占比（0-1）
    data_quality: str = "unknown"        # "high" / "medium" / "low"

    def __getitem__(self, idx):
        ret = super().__getitem__(idx)
        if isinstance(idx, slice):
            new = KlineList(ret)
            new.source = self.source
            new.adjust = self.adjust
            new.quality_ratio = self.quality_ratio
            new.data_quality = self.data_quality
            return new
        return ret



def _fetch_kline_tdx(std, tx, beg, end):
    """通达信本地 .day 文件解析（不复权）。

    读取 {TDX_ROOT}/vipdoc/{sh,sz,bj}/lday/{tx}.day，每根 32 字节：
      日期(int32) 开/高/低/收(4×int32, 实际×100) 成交额(float32,元)
      成交量(int32,手) 保留(4字节)
    beg/end 为 YYYYMMDD 字符串。返回 KlineList（source='tdx_local_raw'），
    文件不存在/解析失败返回空 KlineList。
    """
    out = KlineList()
    out.source = "tdx_local_raw"
    if not std or not tx:
        return out
    market = tx[:_I2]  # "sh" / "sz" / "bj"
    if market not in ("sh", "sz", "bj"):
        return out
    path = os.path.join(_TDX_ROOT, "vipdoc", market, "lday", f"{tx}.day")
    if not os.path.exists(path):
        return out
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return out
    beg_i = int(beg) if beg else 0
    end_i = int(end) if end else 99999999
    n = len(data) // 32
    for i in range(n):
        b = data[i * 32:(i + 1) * 32]
        if len(b) < 32:
            break
        try:
            d, o, h, l, c = struct.unpack("<5I", b[:20])
            amt, = struct.unpack("<f", b[20:24])
            vol, = struct.unpack("<I", b[24:28])
        except struct.error:
            continue
        if d < beg_i or d > end_i:
            continue
        out.append({
            "date": str(d),
            "open": round(o / 100, 2),
            "close": round(c / 100, 2),
            "high": round(h / 100, 2),
            "low": round(l / 100, 2),
            "volume": float(vol),
            "amount": float(amt),
            "amplitude": None,
        })
    return out



def fetch_kline(code, beg=None, end=None, limit=None, min_quality="low", allow_raw=False):
    """东财历史日K（前复权，klt=101），东财失败自动兜底腾讯，再失败兜底通达信本地。

    返回 [{date,open,close,high,low,volume,amount,amplitude}]，
    按时间正序；beg/end 为 YYYYMMDD；limit 只保留最近 N 根。
    本地兜底返回不复权数据，KlineList.source='tdx_local_raw' 供下游标注。
    """
    std, secid, tx = normalize_code(code)
    if beg is None:
        span = max(limit * 2, 8) if limit else 8
        beg = _days_ago(span)
    if end is None:
        end = _days_ago(0)
    rows = []
    for attempt in range(3):
        rows = _fetch_kline_eastmoney(secid, beg, end)
        if rows:
            break
        if attempt < 2:
            time.sleep(0.5)
    source = "eastmoney_qfq" if rows else None
    if not rows:
        d0 = datetime.strptime(beg, "%Y%m%d")
        d1 = datetime.strptime(end, "%Y%m%d")
        rows = _fetch_kline_tencent(tx, d0.strftime("%Y-%m-%d"), d1.strftime("%Y-%m-%d"))
        source = "tencent_qfq" if rows else None
    if not rows and allow_raw:
        rows = _fetch_kline_tdx(std, tx, beg, end)
        source = "tdx_local_raw" if rows else None
    valid, ratio = _validate_kline_rows(rows)
    rows = valid
    if limit and len(rows) > limit:
        rows = rows[len(rows) - limit:]
    out = KlineList(rows)
    out.source = source
    out.adjust = "raw" if source == "tdx_local_raw" else ("qfq" if source else None)
    out.quality_ratio = round(ratio, 3)
    out.data_quality = "high" if source == "eastmoney_qfq" and ratio >= .98 else ("medium" if source == "tencent_qfq" and ratio >= .95 else "low")
    levels = {"low": 0, "medium": 1, "high": 2}
    if levels.get(out.data_quality, 0) < levels.get(min_quality, 0):
        return KlineList()
    return out



def fetch_close_on(code, date_str):
    """回填：取指定日（YYYY-MM-DD）收盘 K 线；无则 None。"""
    beg = date_str.replace("-", "")
    rows = fetch_kline(code, beg=beg, end=beg)
    for r in rows:
        if r["date"] == date_str:
            return r
    return None
