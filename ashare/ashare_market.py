# -*- coding: utf-8 -*-
"""A股市场结构与可执行性规则（2026规则口径）。

只放与A股交易结构直接相关的确定性逻辑；具体交易日的涨跌幅优先使用逐日数据源字段。
"""
from __future__ import annotations
from typing import Any, Dict


def board_of(code: str) -> str:
    c = str(code).lower().replace('sh', '').replace('sz', '').replace('bj', '').zfill(6)
    if c.startswith('688'):
        return '科创板'
    if c.startswith('300') or c.startswith('301'):
        return '创业板'
    # 北交所代码段：43xxxx / 83xxxx / 87xxxx / 88xxxx（存量），以及
    # **920xxx**（2023 年起启用的新段，如 920000 安徽凤凰）。
    # 早期实现只判 ('8','4')，920xxx 会落到「其他A股」→ 涨跌幅被当成 10%
    # 而非 30%（2026-09-19 由 tests/test_exchange_rules.py 抓出）。
    if c.startswith(('8', '4')) or c.startswith('920'):
        return '北交所'
    # 200/900 are B-share codes, not A-share universe. Keep them explicit so
    # a broad code scan cannot silently mix B shares into the A-share model.
    if c.startswith('900'):
        return '沪B股'
    if c.startswith('200'):
        return '深B股'
    if c.startswith(('600', '601', '603', '605')):
        return '沪主板'
    if c.startswith(('000', '001', '002', '003')):
        return '深主板'
    return '其他A股'


def default_limit_ratio(code: str) -> float:
    """没有逐日limit_ratio时的板块默认值；IPO特殊日/退市整理等必须由数据状态覆盖。"""
    board = board_of(code)
    if board in ('科创板', '创业板'):
        return 0.20
    if board == '北交所':
        return 0.30
    if board in ('沪B股', '深B股'):
        return 0.10
    return 0.10


def execution_constraints(code: str, quote: Dict[str, Any] | None = None) -> Dict[str, Any]:
    q = quote or {}
    board = board_of(code)
    return {
        'board': board,
        't_plus_one': True,
        'same_day_sell_allowed': False,
        'default_limit_ratio': default_limit_ratio(code),
        'suspension': q.get('is_suspended'),
        'st_or_risk_warning': q.get('is_st'),
        'limit_ratio_source_required': True,
    }


def event_flags(code: str, bars: list[dict[str, Any]]) -> Dict[str, Any]:
    """从日K确定性推导涨停/跌停、炸板代理指标、连板高度等。"""
    if not bars:
        return {'status': 'insufficient_data'}
    ordered = sorted(bars, key=lambda x: str(x.get('date') or x.get('trade_date') or ''))
    up_days = down_days = 0
    failed_limit_up = 0
    limit_up_streak = 0
    max_limit_up_streak = 0
    last = None
    for b in ordered:
        close = b.get('close'); high = b.get('high'); prev = last
        ratio = b.get('limit_ratio') or b.get('limit_pct')
        if ratio is None:
            ratio = default_limit_ratio(code)
        ratio = float(ratio) / 100 if float(ratio) > 1 else float(ratio)
        if prev and close is not None:
            chg = float(close) / float(prev) - 1
            is_up = chg >= ratio - 0.002
            is_down = chg <= -ratio + 0.002
            if is_up:
                up_days += 1
                limit_up_streak += 1
                max_limit_up_streak = max(max_limit_up_streak, limit_up_streak)
                # 收盘未接近涨停，但盘中最高触及涨停：炸板代理
                if high is not None and float(high) >= float(prev) * (1 + ratio) * 0.998 and float(close) < float(prev) * (1 + ratio) * 0.998:
                    failed_limit_up += 1
            else:
                limit_up_streak = 0
            if is_down:
                down_days += 1
        last = close
    return {
        'status': 'ok',
        'limit_up_days': up_days,
        'limit_down_days': down_days,
        'failed_limit_up_proxy_days': failed_limit_up,
        'max_limit_up_streak': max_limit_up_streak,
    }
