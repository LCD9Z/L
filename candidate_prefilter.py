# -*- coding: utf-8 -*-
"""A股候选池确定性预筛：先机器硬门槛，再交给LLM做定性研究。"""
from __future__ import annotations
from typing import Any, Dict
from ashare.ashare_market import execution_constraints


def prefilter_fact_sheet(fact_sheet: Dict[str, Any]) -> Dict[str, Any]:
    q = fact_sheet.get('quote') or {}
    meta = fact_sheet.get('meta') or {}
    code = str(meta.get('code') or q.get('code') or '')
    bars = fact_sheet.get('kline') or []
    veto = []
    warnings = []
    if q.get('price') is None:
        veto.append('缺少当前价格')
    if q.get('amount') is None:
        warnings.append('缺少成交额，流动性判断降级')
    if q.get('turnover') is None:
        warnings.append('缺少换手率，流动性判断降级')
    if len(bars) < 20:
        warnings.append('历史K线不足20个交易日')
    if q.get('is_suspended') is True:
        veto.append('当前停牌')
    score = (fact_sheet.get('quant_score') or {}).get('score')
    event_pack = fact_sheet.get('event_risk') or {}
    if event_pack.get('high_risk_flags'):
        warnings.extend(event_pack['high_risk_flags'])
    if score is None:
        warnings.append('确定性量化评分不可用')
    return {
        'code': code,
        'board': execution_constraints(code, q).get('board'),
        'machine_score': score,
        'veto': veto,
        'warnings': warnings,
        'eligible_for_llm': not veto,
        'event_risk_flags': event_pack.get('high_risk_flags', []),
        'reason': '通过机器预筛' if not veto else '机器预筛否决',
    }
