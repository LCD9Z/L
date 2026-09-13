# -*- coding: utf-8 -*-
"""V3.2 A股候选池：确定性硬门槛 + 可解释排序。

输入可以来自任意已审计数据源。该模块不会联网，也不会生成缺失行情。
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List
from .ashare_market import board_of, execution_constraints


def screen_row(row: Dict[str, Any]) -> Dict[str, Any]:
    code = str(row.get("code") or row.get("ts_code") or "")
    q = row.get("quote") or row
    veto, warnings = [], []
    board = board_of(code)
    if board in ('沪B股', '深B股'):
        veto.append('B股，不属于A股选股宇宙')
    price = q.get("price")
    if price is None:
        veto.append("缺少价格")
    if q.get("is_suspended") is True:
        veto.append("停牌")
    if q.get("delisted") is True or q.get("is_delisted") is True:
        veto.append("退市/终止上市")
    if q.get("risk_warning") is True and q.get("risk_warning_tradeable") is False:
        veto.append("风险警示且不可交易")
    if q.get("amount") in (None, 0):
        warnings.append("成交额缺失或为0")
    if q.get("turnover") is None:
        warnings.append("换手率缺失")
    c = execution_constraints(code, q)
    return {
        "code": code,
        "board": board,
        "eligible": not veto,
        "veto": veto,
        "warnings": warnings,
        "constraints": c,
    }


def rank_candidates(rows: Iterable[Dict[str, Any]], min_score: float = 55.0) -> List[Dict[str, Any]]:
    out = []
    for row in rows or []:
        r = screen_row(row)
        if not r["eligible"]:
            continue
        score = row.get("score")
        if score is None:
            score = (row.get("quant_score") or {}).get("score")
        if score is None:
            continue
        try: score = float(score)
        except (TypeError, ValueError): continue
        if score < min_score: continue
        r["score"] = score
        out.append(r)
    out.sort(key=lambda x: (-x["score"], x["code"]))
    return out
