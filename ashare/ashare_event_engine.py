# -*- coding: utf-8 -*-
"""V3.2 A股事件层：公告、业绩、解禁、减持、回购、龙虎榜等的确定性归一化。

本模块只负责结构化与风险标签，不猜测事件影响。没有来源/发布日期的数据不会被
当作点时态事实使用。字段设计兼容常见 Tushare/公开数据源的列名，但不强依赖第三方包。
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional


def _text(v: Any) -> str:
    return str(v).strip() if v not in (None, "") else ""


def _date(v: Any) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v).strip().replace("/", "-")
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10] if len(s) >= 10 else s


def _num(v: Any) -> Optional[float]:
    try:
        if v in (None, "", "-"):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _asof_ok(published_at: Optional[str], cutoff: Optional[str]) -> bool:
    """事件必须在 cutoff 前已经公开；无法证明公开时间则不通过 PIT。"""
    if not cutoff:
        return True
    if not published_at:
        return False
    return str(published_at)[:19] <= str(cutoff)[:19]


def normalize_events(rows: Iterable[Dict[str, Any]], event_type: str,
                     cutoff: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    for row in rows or []:
        r = dict(row)
        published = _date(r.get("published_at") or r.get("ann_date") or r.get("trade_date") or r.get("date"))
        if not _asof_ok(published, cutoff):
            continue
        out.append({
            "event_type": event_type,
            "code": _text(r.get("code") or r.get("ts_code") or r.get("symbol")),
            "event_date": _date(r.get("event_date") or r.get("trade_date") or r.get("date")),
            "published_at": published,
            "title": _text(r.get("title") or r.get("name") or r.get("event")),
            "source": _text(r.get("source") or r.get("provider")) or "unknown",
            "source_url": _text(r.get("source_url") or r.get("url")) or None,
            "raw": r,
        })
    return out


def build_event_risk_pack(events: Iterable[Dict[str, Any]], cutoff: Optional[str] = None) -> Dict[str, Any]:
    """从已归一化/半归一化事件生成风险标签；不输出买卖结论。"""
    rows = []
    for e in events or []:
        published = e.get("published_at")
        if cutoff and not _asof_ok(published, cutoff):
            continue
        rows.append(e)
    counts: Dict[str, int] = {}
    for e in rows:
        k = str(e.get("event_type") or "unknown")
        counts[k] = counts.get(k, 0) + 1
    high_risk = []
    warnings = []
    # 事件类别是硬编码风险标签，不代表事件一定利空。
    for e in rows:
        typ = e.get("event_type")
        if typ in {"share_float", "holder_trade", "block_trade"}:
            high_risk.append("股东/解禁交易事件需复核供给冲击")
        elif typ in {"forecast", "express"}:
            warnings.append("业绩事件需核对公告发布日期与预测口径")
        elif typ in {"top_list", "moneyflow"}:
            warnings.append("资金/龙虎榜属于交易行为信息，不等同于基本面改善")
        elif typ in {"repurchase"}:
            warnings.append("回购事件需核对实施进度，不以董事会方案等同已完成")
    # 去重但保持稳定顺序
    def uniq(xs):
        return list(dict.fromkeys(xs))
    return {
        "status": "ok" if rows else "no_verified_events",
        "event_count": len(rows),
        "counts": counts,
        "high_risk_flags": uniq(high_risk),
        "warnings": uniq(warnings),
        "events": rows,
        "cutoff": cutoff,
    }


def normalize_forecast(row: Dict[str, Any]) -> Dict[str, Any]:
    """归一化业绩预告，不推断实际利润。"""
    return {
        "event_type": "forecast",
        "code": _text(row.get("ts_code") or row.get("code")),
        "published_at": _date(row.get("ann_date") or row.get("published_at")),
        "forecast_type": _text(row.get("type") or row.get("forecast_type")),
        "net_profit_min": _num(row.get("net_profit_min")),
        "net_profit_max": _num(row.get("net_profit_max")),
        "last_year_net_profit": _num(row.get("last_net_profit")),
        "change_min_pct": _num(row.get("p_change_min")),
        "change_max_pct": _num(row.get("p_change_max")),
        "source": _text(row.get("source")) or "unknown",
    }


def normalize_float_event(row: Dict[str, Any]) -> Dict[str, Any]:
    """归一化解禁/股东交易事件，保留原始数量单位，不擅自换算。"""
    return {
        "event_type": "share_float",
        "code": _text(row.get("ts_code") or row.get("code")),
        "event_date": _date(row.get("float_date") or row.get("event_date") or row.get("trade_date")),
        "published_at": _date(row.get("ann_date") or row.get("published_at")),
        "float_shares": _num(row.get("float_share") or row.get("float_shares")),
        "source": _text(row.get("source")) or "unknown",
    }
