# -*- coding: utf-8 -*-
"""通达信原生 `.day` 二进制日线读取器（零第三方依赖）。

TDX 本地日线文件格式（每记录 32 字节，struct ``<IIIIIfII``）：:

    date(int, YYYYMMDD)  open(int)  high(int)  low(int)  close(int)
    amount(float32, 元)  volume(int, 股)  reserved(int)

价格需除以 100（A 股常规；部分低价品种可能为 1000，见 PRICE_DIV）。

本读取器只读文件**尾部** N 根（五因子最长回看 21 根 + 流动性 20 根），
以适配低配机器（i5-3320M / 7.8GB），避免全市场 ~9000 文件全量载入内存。
"""
from __future__ import annotations

import os
import struct
from typing import Any, Dict, List, Tuple

REC = struct.Struct("<IIIIIfII")
PRICE_DIV = 100.0

# 真实 A 股股票代码段（镜像自 tdx/tdx_csv_adapter.classify，避免外部依赖）
_STOCK_PREFIXES = ("600", "601", "603", "605", "688", "689",
                   "000", "001", "002", "003", "300", "301", "430", "920")
_BJ_OLD_RANGES = (range(830, 840), range(870, 874))
_TDX_INDEX_PREFIXES = ("880", "881", "899")
# sh 与股票代码重叠的宽基指数（必须靠 market 消歧）
_SH_INDEX_CODES = ("000001", "000300", "000905", "000016", "000688")


def is_a_share_stock(code: str, market: str = "") -> bool:
    """是否为可交易 A 股股票（排除 ETF/可转债/通达信板块指数/宽基指数）。"""
    code = str(code).zfill(6)
    p3 = code[:3]
    if p3 in _TDX_INDEX_PREFIXES:
        return False
    if market == "sh" and code in _SH_INDEX_CODES:
        return False
    if market == "sz" and p3 == "399":
        return False
    if p3 in _STOCK_PREFIXES:
        return True
    if code[:3].isdigit():
        pi = int(code[:3])
        if any(pi in r for r in _BJ_OLD_RANGES):
            return True
    return False


def read_day_tail(path: str, n: int = 80) -> List[Dict[str, Any]]:
    """读取 .day 文件最后 n 根（升序），返回 bar 列表（date/open/high/low/close/amount/volume）。

    注意：返回的 dict 是**混合类型**（``date`` 为 ``str`` 的 YYYYMMDD，
    其余为 ``float``）。此前标注为 ``Dict[str, float]`` 是错的，会让下游
    把 ``date`` 当作 float 使用（一处错误标注污染了 5 个调用方的类型推断）。
    """
    size = os.path.getsize(path)
    total = size // REC.size
    want = min(n, total)
    if want <= 0:
        return []
    with open(path, "rb") as f:
        f.seek((total - want) * REC.size)
        buf = f.read(want * REC.size)
    rows: List[Dict[str, Any]] = []
    for i in range(want):
        d, o, h, l, c, a, v, _ = REC.unpack_from(buf, i * REC.size)
        if c <= 0:
            continue
        rows.append({"date": str(d), "open": o / PRICE_DIV, "high": h / PRICE_DIV,
                     "low": l / PRICE_DIV, "close": c / PRICE_DIV,
                     "amount": float(a), "volume": float(v)})
    return rows


def read_day_all(path: str) -> List[Dict[str, Any]]:
    """读取 .day 文件**全部**记录（升序）。用于需要长历史的复权/IC 研究。

    返回结构同 :func:`read_day_tail`（混合类型 dict）。
    """
    with open(path, "rb") as f:
        buf = f.read()
    total = len(buf) // REC.size
    rows: List[Dict[str, Any]] = []
    for i in range(total):
        d, o, h, l, c, a, v, _ = REC.unpack_from(buf, i * REC.size)
        if c <= 0:
            continue
        rows.append({"date": str(d), "open": o / PRICE_DIV, "high": h / PRICE_DIV,
                     "low": l / PRICE_DIV, "close": c / PRICE_DIV,
                     "amount": float(a), "volume": float(v)})
    return rows


def board_of(code: str) -> str:
    """所属板块（用于涨跌停判定）。"""
    c = str(code).zfill(6)
    p3 = c[:3]
    if p3 in ("600", "601", "603", "605"):
        return "sh_main"
    if p3 in ("688", "689"):
        return "star"
    if p3 in ("000", "001", "002", "003"):
        return "sz_main"
    if p3 in ("300", "301"):
        return "chinext"
    return "bse"


def limit_pct(code: str) -> float:
    """该股涨跌停幅度（主板 10%、双创 20%、北交所 30%）。"""
    b = board_of(code)
    if b == "bse":
        return 0.30
    if b in ("star", "chinext"):
        return 0.20
    return 0.10


def scan_stocks(vipdoc_root: str, markets: Tuple[str, ...] = ("sh", "sz", "bj"),
                tail: int = 80) -> List[Tuple[str, str, str, List[Dict[str, Any]]]]:
    """扫描 vipdoc 下各市场 lday 目录，返回真实 A 股股票的 (code, market, path, bars)。"""
    out: List[Tuple[str, str, str, List[Dict[str, Any]]]] = []
    for market in markets:
        lday = os.path.join(vipdoc_root, market, "lday")
        if not os.path.isdir(lday):
            continue
        for fn in sorted(os.listdir(lday)):
            if not fn.endswith(".day"):
                continue
            stem = fn[:-4]                      # 如 sh600519
            if not stem.lower().startswith(market):
                continue
            code = stem[len(market):]           # 600519
            if not is_a_share_stock(code, market):
                continue
            path = os.path.join(lday, fn)
            bars = read_day_tail(path, tail)
            if bars:
                out.append((code, market, path, bars))
    return out


def scan_paths(vipdoc_root: str, markets: Tuple[str, ...] = ("sh", "sz", "bj")
               ) -> List[Tuple[str, str, str]]:
    """只扫描真实 A 股股票的 (code, market, path)，不读数据（供长历史研究用）。"""
    out: List[Tuple[str, str, str]] = []
    for market in markets:
        lday = os.path.join(vipdoc_root, market, "lday")
        if not os.path.isdir(lday):
            continue
        for fn in sorted(os.listdir(lday)):
            if not fn.endswith(".day"):
                continue
            stem = fn[:-4]
            if not stem.lower().startswith(market):
                continue
            code = stem[len(market):]
            if not is_a_share_stock(code, market):
                continue
            out.append((code, market, os.path.join(lday, fn)))
    return out


def load_names(path: str) -> Dict[str, str]:
    """从 CSV（表头 code,name）加载代码→名称映射。缺文件返回空。"""
    import csv
    names: Dict[str, str] = {}
    if not path or not os.path.exists(path):
        return names
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f)
        next(rd, None)   # 跳过表头（若有）
        for row in rd:
            if len(row) >= 2:
                names[row[0].strip().zfill(6)] = row[1].strip()
    return names
