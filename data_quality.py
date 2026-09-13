# -*- coding: utf-8 -*-
"""A股研究数据质量与点时态（Point-in-Time）质量门禁。"""


def audit_bars(bars, large_jump=0.30):
    """同时检查日期、OHLCV、重复、顺序及异常跳变。"""
    issues = []
    prev = None
    seen = set()
    for i, b in enumerate(bars or []):
        d = str(b.get("date", ""))
        if not d:
            issues.append((i, "missing_date"))
        if d in seen and d:
            issues.append((i, "duplicate_date"))
        if d:
            seen.add(d)
        if prev and d and d < prev:
            issues.append((i, "non_monotonic_date"))
        if d:
            prev = d
        vals = [b.get(k) for k in ("open", "high", "low", "close")]
        if any(v is None for v in vals):
            issues.append((i, "missing_ohlc"))
            continue
        try:
            o, h, l, c = map(float, vals)
        except (TypeError, ValueError):
            issues.append((i, "non_numeric_ohlc"))
            continue
        if min(o, h, l, c) <= 0:
            issues.append((i, "non_positive_price"))
        if h < max(o, c) or l > min(o, c) or h < l:
            issues.append((i, "invalid_ohlc"))
        if b.get("volume") is not None:
            try:
                if float(b["volume"]) < 0:
                    issues.append((i, "negative_volume"))
            except (TypeError, ValueError):
                issues.append((i, "invalid_volume"))
        if i > 0 and bars[i-1].get("close") not in (None, 0):
            try:
                jump = abs(c / float(bars[i-1]["close"]) - 1.0)
                if jump > large_jump and not b.get("corporate_action_adjusted"):
                    issues.append((i, "large_price_jump_review"))
            except (TypeError, ValueError, ZeroDivisionError):
                pass
    return {"ok": not issues, "issues": issues, "rows": len(bars or [])}


def quality_score(bars):
    """返回0-100的可解释质量分；仅用于数据质量，不代表股票评分。"""
    audit = audit_bars(bars)
    n = max(audit["rows"], 1)
    bad = len(audit["issues"])
    return max(0.0, round(100.0 * (1.0 - bad / n), 2))


def require_pit_asof(records, asof_date):
    """拒绝发布日期晚于研究时点的记录；历史回测无发布时间也不应默认视为可用。"""
    bad = []
    missing_pub = []
    for i, r in enumerate(records or []):
        pub = r.get("published_at") or r.get("asof") or r.get("date")
        if pub is None or str(pub).strip() == "":
            missing_pub.append(i)
            continue
        if str(pub) > str(asof_date):
            bad.append(i)
    return {
        "ok": not bad and not missing_pub,
        "future_record_indices": bad,
        "missing_timestamp_indices": missing_pub,
        "checked": len(records or []),
    }


def validate_bars(bars):
    """兼容 Phase12/14 API，返回 errors 结构。"""
    from datetime import datetime
    errors = []
    seen = set()
    prev = None
    for i, b in enumerate(bars or []):
        d = str(b.get("date", ""))
        if not d:
            errors.append({"index": i, "type": "missing_date"})
        else:
            try:
                datetime.fromisoformat(d[:10])
            except ValueError:
                errors.append({"index": i, "type": "invalid_date"})
            if d in seen:
                errors.append({"index": i, "type": "duplicate_date"})
            seen.add(d)
            if prev and d < prev:
                errors.append({"index": i, "type": "non_monotonic_date"})
            prev = d
        vals = [b.get(k) for k in ("open", "high", "low", "close")]
        if any(v is None for v in vals):
            errors.append({"index": i, "type": "missing_ohlc"})
            continue
        try:
            o, h, l, c = map(float, vals)
            if min(o, h, l, c) <= 0:
                errors.append({"index": i, "type": "non_positive_price"})
            if h < max(o, c) or l > min(o, c) or h < l:
                errors.append({"index": i, "type": "invalid_ohlc"})
        except (TypeError, ValueError):
            errors.append({"index": i, "type": "non_numeric_ohlc"})
    return {"ok": not errors, "errors": errors, "rows": len(bars or [])}
