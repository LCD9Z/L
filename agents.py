# -*- coding: utf-8 -*-
"""AI股神团队 - Agent 门面模块（向后兼容）。

历史上全部 Agent 定义集中在本文件（658 行）。1.0 起按职责拆分：

    agents_base.py        基类 / 数据包注入 / AnalysisResult
    agents_analysts.py    4 位分析师（基本面·情绪·新闻·技术）
    agents_researchers.py 看多 / 看空研究员
    agents_decision.py    交易员 / 风控官

本模块重新导出全部公开符号，**`from agents import X` 的既有用法完全不变**。
新代码可直接从子模块导入以减少依赖面。
"""

from typing import List

from agents_base import (
    DATA_RULES,
    AnalysisResult,
    BaseAgent,
    pack_data,
)
from agents_analysts import (
    FundamentalAnalyst,
    NewsAnalyst,
    SentimentAnalyst,
    TechnicalAnalyst,
)
from agents_researchers import BearishResearcher, BullishResearcher
from agents_decision import RiskManager, Trader

__all__ = [
    "AGENT_REGISTRY",
    "DATA_RULES",
    "AnalysisResult",
    "BaseAgent",
    "BearishResearcher",
    "BullishResearcher",
    "FundamentalAnalyst",
    "NewsAnalyst",
    "RiskManager",
    "SentimentAnalyst",
    "TechnicalAnalyst",
    "Trader",
    "create_agent",
    "get_analyst_team",
    "get_decision_team",
    "get_research_team",
    "pack_data",
]


# ---------------------------------------------------------------------------
# Agent 工厂
# ---------------------------------------------------------------------------

AGENT_REGISTRY = {
    "fundamental": FundamentalAnalyst,
    "sentiment": SentimentAnalyst,
    "news": NewsAnalyst,
    "technical": TechnicalAnalyst,
    "bullish": BullishResearcher,
    "bearish": BearishResearcher,
    "trader": Trader,
    "risk": RiskManager,
}


def create_agent(agent_type: str) -> BaseAgent:
    """创建Agent实例"""
    if agent_type not in AGENT_REGISTRY:
        raise ValueError(f"未知的Agent类型: {agent_type}")
    return AGENT_REGISTRY[agent_type]()


def get_analyst_team() -> List[BaseAgent]:
    """获取分析师团队"""
    return [
        FundamentalAnalyst(),
        SentimentAnalyst(),
        NewsAnalyst(),
        TechnicalAnalyst(),
    ]


def get_research_team() -> List[BaseAgent]:
    """获取研究员团队"""
    return [
        BullishResearcher(),
        BearishResearcher(),
    ]


def get_decision_team() -> List[BaseAgent]:
    """获取决策团队"""
    return [
        Trader(),
        RiskManager(),
    ]


if __name__ == "__main__":
    # 测试
    agent = FundamentalAnalyst()
    print(agent.generate_prompt("AAPL", "Apple Inc."))
