# -*- coding: utf-8 -*-
"""V3 local Quant Skill router.

The external finance-quant-skills repository is treated as a knowledge/skill
source, not as a runtime dependency. This router gives our agents a stable
capability vocabulary and lets operators map a capability to an installed
implementation later (AKShare, Tushare, TDX, Backtrader, etc.).
"""
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class QuantSkill:
    name: str
    purpose: str
    preferred_tools: tuple
    risk_notes: tuple = ()


SKILLS = {
    "market_data": QuantSkill("market_data", "A股行情/K线/成交量", ("a-stock-data", "easy-tdx", "tushare")),
    "technical_factors": QuantSkill("technical_factors", "技术指标与趋势因子", ("easy-tdx", "tdxquant", "local")),
    "factor_research": QuantSkill("factor_research", "因子构建、排序、组合", ("local", "backtrader", "akquant")),
    "backtest": QuantSkill("backtest", "事件驱动/组合回测", ("backtrader", "rqalpha", "local"), ("必须使用点时态数据",)),
    "fundamental": QuantSkill("fundamental", "财务与估值研究", ("tushare", "akshare", "a-stock-data")),
    "event_research": QuantSkill("event_research", "公告/研报/新闻事件", ("a-stock-data", "crawl4ai")),
    "execution": QuantSkill("execution", "T+1/涨跌停/流动性/成本", ("local",)),
}


def route(task: str) -> Dict:
    key = task.strip().lower().replace(" ", "_")
    aliases = {
        "kline": "market_data",
        "行情": "market_data",
        "技术": "technical_factors",
        "技术指标": "technical_factors",
        "因子": "factor_research",
        "回测": "backtest",
        "财务": "fundamental",
        "公告": "event_research",
        "新闻": "event_research",
        "交易": "execution",
    }
    key = aliases.get(key, key)
    skill = SKILLS.get(key)
    if not skill:
        return {"ok": False, "task": task, "error": "unknown_skill"}
    return {
        "ok": True,
        "skill": skill.name,
        "purpose": skill.purpose,
        "preferred_tools": list(skill.preferred_tools),
        "risk_notes": list(skill.risk_notes),
    }
