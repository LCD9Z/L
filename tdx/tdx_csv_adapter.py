# -*- coding: utf-8 -*-
"""通达信（TDX）导出日线 CSV 适配器。

源格式（单文件全市场，含表头）::

    date,code,market,open,high,low,close,volume,amount
    2022-04-29,899050,bj,1000.0,1000.0,1000.0,1000.0,455216,581906432.0

## 数据性质（经实测，务必阅读）

**1. 不复权（原始价）**
TDX `.day` 为原始成交价。实测存在 13,696 行单日 |涨跌| > 21% 的跳空 ——
而主板涨跌停为 ±10%、双创为 ±20%，正常交易不可能超过该幅度，
故这些跳空基本来自**除权除息**。因子计算前必须处理除权，
或仅在不受除权影响的短周期形态上使用。

**2. 品种混杂（约 41% 不是股票）**
同一文件混有 ETF/LOF、可转债、通达信板块指数（880/881/899）、宽基指数。
实测 9,438 个代码中仅约 5,580 个是真实 A 股股票，**必须过滤**。

**3. 幸存者偏差（严重）**
抽样 15 只在 2021–2026 期间退市/被合并的股票，**全部不在数据集中**；
99.1% 的代码数据持续到最后交易日。即本数据集**只含存续至今的标的**。
任何基于它的回测结果都会**系统性偏乐观**。

**4. 无 PIT 股票池**
需按上市日自行构造（见 `build_pit_universe`）。

**5. 缺少换手率 / 流通股本**
无法施加真实的容量与流动性约束。

## 结论

本模块只做**格式适配与品种过滤**，不声称数据满足实证要求。
可用于工程验证、跨截面因子行为的初步观察，**不足以单独支撑投资结论**。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import zipfile
from typing import Any, Dict, Iterator, List, Optional, Set

# 管线期望的列（load_certified_csv 用 csv.DictReader 读取）
PIPELINE_COLUMNS = ("date", "open", "close", "high", "low", "volume", "amount")

# 真实 A 股股票的 3 位代码前缀
_STOCK_PREFIXES = (
    "600", "601", "603", "605",          # 沪主板
    "688", "689",                        # 科创板
    "000", "001", "002", "003",          # 深主板 / 中小板
    "300", "301",                        # 创业板
    "430", "920",                        # 北交所
)
# 北交所旧代码段 830xxx-839xxx / 870xxx-873xxx
_BJ_OLD_RANGES = (range(830, 840), range(870, 874))

# 明确排除：通达信板块/市场指数（易被误当股票）
_TDX_INDEX_PREFIXES = ("880", "881", "899")


def _int_prefix(code: str) -> Optional[int]:
    try:
        return int(code[:3])
    except (ValueError, TypeError):
        return None


def classify(code: str, market: str = "") -> str:
    """判定品种类型。`market` 用于消歧（如 000001 在 sh 是上证指数、在 sz 是平安银行）。"""
    code = str(code).zfill(6)
    market = (market or "").strip().lower()
    p3 = code[:3]

    # 指数优先：000001(sh)/399xxx(sz) 等与股票代码重叠，必须靠 market 区分
    if p3 in _TDX_INDEX_PREFIXES:
        return "tdx_index"
    if market == "sh" and code in ("000001", "000300", "000905", "000016", "000688"):
        return "broad_index"
    if market == "sz" and p3 == "399":
        return "broad_index"

    if p3 in _STOCK_PREFIXES:
        return "stock"
    p3i = _int_prefix(code)
    if p3i is not None and any(p3i in r for r in _BJ_OLD_RANGES):
        return "stock"

    if code[:2] in ("15", "16") or p3 in ("501", "502", "510", "511", "512", "513",
                                          "515", "516", "518", "520", "560", "561",
                                          "562", "563", "588", "589", "159"):
        return "fund"
    if code[:2] in ("11", "12", "13"):
        return "convertible_bond"
    return "other"


def is_a_share_stock(code: str, market: str = "") -> bool:
    """是否为可交易的真实 A 股股票（排除 ETF/可转债/指数）。"""
    return classify(code, market) == "stock"


def classify_instrument(code: str, market: str = "") -> str:
    """v4.9 兼容别名：把本模块的细分类别归并为 ``stock`` / ``index`` / ``fund`` / ``other``。

    存在原因：v4.9 分支的 `tdx_inventory.py` 依赖该函数名，而其同名适配器只有
    粗粒度分类。本模块提供更细的 `classify()`（区分 tdx_index / broad_index /
    convertible_bond），此处做一次归并，使两套 API 并存而不破坏任一调用方。
    """
    kind = classify(code, market)
    if kind == "stock":
        return "stock"
    if kind in ("tdx_index", "broad_index"):
        return "index"
    if kind == "fund":
        return "fund"
    return "other"


def board_of(code: str) -> str:
    """所属板块（用于按板块设置涨跌停等规则）。"""
    code = str(code).zfill(6)
    p3 = code[:3]
    if p3 in ("600", "601", "603", "605"):
        return "sh_main"
    if p3 in ("688", "689"):
        return "star"
    if p3 in ("000", "001", "002", "003"):
        return "sz_main"
    if p3 in ("300", "301"):
        return "chinext"
    return "bse"


def _open_source(path: str):
    """同时支持 .zip 与裸 .csv。"""
    if str(path).lower().endswith(".zip"):
        z = zipfile.ZipFile(path)
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        return z.open(name), z
    return open(path, "rb"), None


def iter_rows(path: str, *, encoding: str = "utf-8-sig") -> Iterator[Dict[str, Any]]:
    """流式产出全部行（不做品种过滤）。"""
    raw, z = _open_source(path)
    try:
        text = io.TextIOWrapper(raw, encoding=encoding, newline="")
        rd = csv.reader(text)
        header = next(rd)
        if [h.strip().lower() for h in header] != [
                "date", "code", "market", "open", "high", "low", "close", "volume", "amount"]:
            raise ValueError(f"unexpected_header:{header}")
        for row in rd:
            if len(row) != 9:
                continue
            yield {
                "date": row[0].strip(),
                "code": row[1].strip().zfill(6),
                "market": row[2].strip().lower(),
                "open": float(row[3]),
                "high": float(row[4]),
                "low": float(row[5]),
                "close": float(row[6]),
                "volume": float(row[7]),
                "amount": float(row[8]),
            }
    finally:
        raw.close()
        if z is not None:
            z.close()


def iter_stock_rows(path: str) -> Iterator[Dict[str, Any]]:
    """仅产出真实 A 股股票的行。"""
    for r in iter_rows(path):
        if is_a_share_stock(r["code"], r["market"]):
            yield r


def scan_inventory(path: str) -> Dict[str, Any]:
    """扫描全量，返回品种分布与每只股票的行数/日期范围。

    用于决定导出哪些标的。返回::

        {"by_type": {类型: [行数, 代码数]},
         "stocks": {code: {"market":.., "rows":.., "first":.., "last":..}}}
    """
    from collections import Counter, defaultdict

    by_type: Counter = Counter()
    type_codes: Dict[str, Set[str]] = defaultdict(set)
    stocks: Dict[str, Dict[str, Any]] = {}

    for r in iter_rows(path):
        t = classify(r["code"], r["market"])
        by_type[t] += 1
        type_codes[t].add(r["code"])
        if t == "stock":
            s = stocks.get(r["code"])
            if s is None:
                stocks[r["code"]] = {"market": r["market"], "rows": 1,
                                     "first": r["date"], "last": r["date"]}
            else:
                s["rows"] += 1
                if r["date"] < s["first"]:
                    s["first"] = r["date"]
                if r["date"] > s["last"]:
                    s["last"] = r["date"]

    return {
        "by_type": {k: [v, len(type_codes[k])] for k, v in by_type.most_common()},
        "stocks": stocks,
    }


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid_ohlc(row: Dict[str, Any]) -> bool:
    """OHLC 自洽性校验（与 professional_audit.audit_csv 的判定保持一致）。

    源数据实测存在 113 行越界（占 9.8M 的 0.001%）。管线的审计是"任一行不合规
    即整体失败"，因此导出时必须清洗，否则整个数据集无法通过 preflight。
    """
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if min(o, h, l, c) <= 0:
        return False
    if h < l:
        return False
    # 开/收必须落在 [low, high] 区间内
    return not (h < max(o, c) or l > min(o, c))
    return True


def export_stock_csvs(
    src: str,
    out_dir: str,
    *,
    codes: Optional[Set[str]] = None,
    min_rows: int = 250,
    write_metadata: bool = True,
) -> Dict[str, Any]:
    """导出符合 `real_alpha_pipeline.load_certified_csv` 契约的每股 CSV + 元数据。

    产出：
        {out_dir}/{code}.csv              列 = PIPELINE_COLUMNS，按日期升序
        {out_dir}/{code}.metadata.json    {"strict":true,"sha256":..,"rows":..}

    导出时会：
      · 过滤掉 OHLC 不自洽的行（源数据存在少量此类行）
      · 去重同一 (code, date)（管线会校验日期唯一）
      · 剔除清洗后行数不足 min_rows 的标的

    返回统计摘要（含清洗计数）。
    """
    os.makedirs(out_dir, exist_ok=True)
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    dropped_invalid = 0

    for r in iter_stock_rows(src):
        if codes is not None and r["code"] not in codes:
            continue
        if not is_valid_ohlc(r):
            dropped_invalid += 1
            continue
        buckets.setdefault(r["code"], []).append(r)

    written, skipped, total_rows = [], [], 0
    dropped_dup = 0
    for code, rows in buckets.items():
        rows.sort(key=lambda x: x["date"])
        # 同一交易日去重（保留首条）
        uniq, seen = [], set()
        for r in rows:
            if r["date"] in seen:
                dropped_dup += 1
                continue
            seen.add(r["date"])
            uniq.append(r)
        rows = uniq
        if len(rows) < min_rows:
            skipped.append((code, len(rows)))
            continue
        path = os.path.join(out_dir, f"{code}.csv")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            w = csv.DictWriter(f, fieldnames=list(PIPELINE_COLUMNS))
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in PIPELINE_COLUMNS})
        if write_metadata:
            meta = {"strict": True, "sha256": _sha256(path), "rows": len(rows),
                    "code": code, "source": os.path.basename(str(src)),
                    "adjusted": False,
                    "note": "TDX raw (unadjusted) daily bars; survivorship-biased universe"}
            with open(os.path.join(out_dir, f"{code}.metadata.json"), "w",
                      encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
        written.append(code)
        total_rows += len(rows)

    return {"written": len(written), "skipped": len(skipped), "total_rows": total_rows,
            "out_dir": out_dir, "codes": sorted(written),
            "dropped_invalid_ohlc": dropped_invalid, "dropped_duplicate_dates": dropped_dup}


def build_pit_universe(stocks: Dict[str, Dict[str, Any]], dates: List[str],
                       *, min_history: int = 250) -> Dict[str, List[str]]:
    """按上市日构造最简 PIT 股票池快照。

    注意：本数据集**不含退市股**，因此本函数只能反映"上市后即长期在池"，
    **无法修正幸存者偏差**。返回 {date: [codes]}。
    """
    snaps: Dict[str, List[str]] = {}
    for d in dates:
        members = []
        for code, s in stocks.items():
            if s["first"] > d:
                continue                      # 尚未上市
            if s["last"] < d:
                continue                      # 已无数据
            members.append(code)
        snaps[d] = sorted(members)
    return snaps
