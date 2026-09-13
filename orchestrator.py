# -*- coding: utf-8 -*-
"""
AI股神团队 - 编排器模块
协调各个Agent的执行流程，管理分析状态
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, field

from agents import (
    AnalysisResult,
    FundamentalAnalyst, SentimentAnalyst, NewsAnalyst, TechnicalAnalyst,
    BullishResearcher, BearishResearcher,
    Trader, RiskManager
)


@dataclass
class AnalysisSession:
    """分析会话状态"""
    stock_code: str = ""
    company_name: str = ""
    session_id: str = ""
    created_at: str = ""
    current_stage: str = "waiting_input"
    # 用 default_factory 保证非 None：下游（report_generator 等）直接索引该字段，
    # 若声明为 Optional 则每次访问都要判空，且易漏。
    analyst_reports: Dict[str, AnalysisResult] = field(default_factory=dict)
    bullish_report: Optional[AnalysisResult] = None
    bearish_report: Optional[AnalysisResult] = None
    trade_proposal: Optional[AnalysisResult] = None
    final_decision: Optional[AnalysisResult] = None

    def __post_init__(self):
        if not self.session_id:
            self.session_id = f"{self.stock_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class WorkflowOrchestrator:
    """工作流编排器"""

    # 不可变元组：避免可变类属性被实例间共享修改（原为 list）
    STAGES = (
        "waiting_input",           # 等待输入
        "analyst_fundamental",     # 基本面分析
        "analyst_sentiment",       # 情绪分析
        "analyst_news",            # 新闻分析
        "analyst_technical",       # 技术分析
        "research_bullish",        # 看多研究
        "research_bearish",        # 看空研究
        "decision_trade",          # 交易决策
        "decision_risk",           # 风控审批
        "completed",               # 完成
    )
    
    def __init__(self, session: Optional[AnalysisSession] = None):
        self.session = session or AnalysisSession("", "")
        self.current_stage_idx = 0
        self._stage_names = {
            "waiting_input": "等待输入",
            "analyst_fundamental": "📊 基本面分析",
            "analyst_sentiment": "🗣️ 情绪分析",
            "analyst_news": "📰 新闻分析",
            "analyst_technical": "📈 技术分析",
            "research_bullish": "🐂 看多论证",
            "research_bearish": "🐻 看空论证",
            "decision_trade": "🧑‍💼 交易决策",
            "decision_risk": "🛡️ 风控审批",
            "completed": "✅ 分析完成",
        }
    
    def start_analysis(self, stock_code: str, company_name: str = "") -> AnalysisSession:
        """开始新的分析会话"""
        self.session = AnalysisSession(
            stock_code=stock_code.upper(),
            company_name=company_name or stock_code.upper(),
            session_id=f"{stock_code.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            current_stage="analyst_fundamental"
        )
        self.current_stage_idx = 1
        return self.session
    
    def get_next_prompt(self) -> Optional[str]:
        """获取下一个Agent的分析提示词。

        注意：各 Agent 的 generate_prompt 签名不同（研究员/决策层需要前序报告），
        故每个分支直接内联调用，不复用同一个变量 —— 否则类型无法静态校验。
        """
        stage = self.session.current_stage
        stock = self.session.stock_code
        company = self.session.company_name
        reports = [r.content for r in (self.session.analyst_reports or {}).values()]

        if stage == "analyst_fundamental":
            return FundamentalAnalyst().generate_prompt(stock, company)

        elif stage == "analyst_sentiment":
            return SentimentAnalyst().generate_prompt(stock, company)

        elif stage == "analyst_news":
            return NewsAnalyst().generate_prompt(stock, company)

        elif stage == "analyst_technical":
            return TechnicalAnalyst().generate_prompt(stock, company)

        elif stage == "research_bullish":
            return BullishResearcher().generate_prompt(stock, company, reports)

        elif stage == "research_bearish":
            bullish = self.session.bullish_report.content if self.session.bullish_report else ""
            return BearishResearcher().generate_prompt(stock, company, reports, bullish)

        elif stage == "decision_trade":
            bullish = self.session.bullish_report.content if self.session.bullish_report else ""
            bearish = self.session.bearish_report.content if self.session.bearish_report else ""
            return Trader().generate_prompt(stock, company, reports, bullish, bearish)

        elif stage == "decision_risk":
            bullish = self.session.bullish_report.content if self.session.bullish_report else ""
            bearish = self.session.bearish_report.content if self.session.bearish_report else ""
            trade = self.session.trade_proposal.content if self.session.trade_proposal else ""
            return RiskManager().generate_prompt(stock, company, reports, bullish, bearish, trade)

        return None
    
    def submit_result(self, agent_type: str, content: str,
                     score: Optional[float] = None,
                     recommendation: Optional[str] = None) -> str:
        """提交Agent分析结果，推进到下一阶段"""
        result = AnalysisResult(
            agent_name=self._get_agent_name(agent_type),
            agent_emoji=self._get_agent_emoji(agent_type),
            analysis_type=agent_type,
            content=content,
            score=score,
            recommendation=recommendation
        )
        
        # 保存结果
        if agent_type.startswith("analyst_"):
            self.session.analyst_reports[agent_type] = result
        elif agent_type == "research_bullish":
            self.session.bullish_report = result
        elif agent_type == "research_bearish":
            self.session.bearish_report = result
        elif agent_type == "decision_trade":
            self.session.trade_proposal = result
        elif agent_type == "decision_risk":
            self.session.final_decision = result
        
        # 推进阶段
        self._advance_stage()
        return self.session.current_stage
    
    def _advance_stage(self):
        """推进到下一个阶段"""
        current = self.session.current_stage
        if current in self.STAGES:
            idx = self.STAGES.index(current)
            if idx < len(self.STAGES) - 1:
                self.current_stage_idx = idx + 1
                self.session.current_stage = self.STAGES[idx + 1]
    
    def _get_agent_name(self, agent_type: str) -> str:
        """获取Agent名称"""
        names = {
            "analyst_fundamental": "基本面分析师",
            "analyst_sentiment": "情绪分析师",
            "analyst_news": "新闻分析师",
            "analyst_technical": "技术分析师",
            "research_bullish": "看多研究员",
            "research_bearish": "看空研究员",
            "decision_trade": "交易员",
            "decision_risk": "风控官&投资经理",
        }
        return names.get(agent_type, "未知Agent")
    
    def _get_agent_emoji(self, agent_type: str) -> str:
        """获取Agent表情"""
        emojis = {
            "analyst_fundamental": "📊",
            "analyst_sentiment": "🗣️",
            "analyst_news": "📰",
            "analyst_technical": "📈",
            "research_bullish": "🐂",
            "research_bearish": "🐻",
            "decision_trade": "🧑‍💼",
            "decision_risk": "🛡️",
        }
        return emojis.get(agent_type, "❓")
    
    def get_progress(self) -> Dict:
        """获取当前进度"""
        total = len(self.STAGES) - 1  # 排除 waiting_input
        current = self.current_stage_idx
        
        completed_stages = []
        for stage in self.STAGES[1:]:  # 跳过 waiting_input
            if self.STAGES.index(stage) < self.current_stage_idx:
                completed_stages.append(stage)
        
        return {
            "current_stage": self.session.current_stage,
            "current_stage_name": self._stage_names.get(self.session.current_stage, "未知"),
            "progress_percent": int((current / total) * 100),
            "completed_stages": completed_stages,
            "total_stages": total,
            "current_stage_num": current,
        }
    
    def is_completed(self) -> bool:
        """检查是否完成"""
        return self.session.current_stage == "completed"
    
    def save_session(self, filepath: Optional[str] = None) -> str:
        """保存会话到JSON"""
        if filepath is None:
            filepath = f"reports/{self.session.session_id}.json"

        # 仅当路径含目录时才创建：裸文件名的 dirname 为空串，
        # 直接 makedirs("") 会抛 FileNotFoundError。
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)

        data = {
            "stock_code": self.session.stock_code,
            "company_name": self.session.company_name,
            "session_id": self.session.session_id,
            "created_at": self.session.created_at,
            "current_stage": self.session.current_stage,
            "analyst_reports": {
                k: {
                    "agent_name": v.agent_name,
                    "agent_emoji": v.agent_emoji,
                    "content": v.content,
                    "score": v.score,
                    "recommendation": v.recommendation,
                    "timestamp": v.timestamp,
                }
                for k, v in self.session.analyst_reports.items()
            },
            "bullish_report": {
                "agent_name": self.session.bullish_report.agent_name,
                "agent_emoji": self.session.bullish_report.agent_emoji,
                "content": self.session.bullish_report.content,
                "score": self.session.bullish_report.score,
                "recommendation": self.session.bullish_report.recommendation,
                "timestamp": self.session.bullish_report.timestamp,
            } if self.session.bullish_report else None,
            "bearish_report": {
                "agent_name": self.session.bearish_report.agent_name,
                "agent_emoji": self.session.bearish_report.agent_emoji,
                "content": self.session.bearish_report.content,
                "score": self.session.bearish_report.score,
                "recommendation": self.session.bearish_report.recommendation,
                "timestamp": self.session.bearish_report.timestamp,
            } if self.session.bearish_report else None,
            "trade_proposal": {
                "agent_name": self.session.trade_proposal.agent_name,
                "agent_emoji": self.session.trade_proposal.agent_emoji,
                "content": self.session.trade_proposal.content,
                "score": self.session.trade_proposal.score,
                "recommendation": self.session.trade_proposal.recommendation,
                "timestamp": self.session.trade_proposal.timestamp,
            } if self.session.trade_proposal else None,
            "final_decision": {
                "agent_name": self.session.final_decision.agent_name,
                "agent_emoji": self.session.final_decision.agent_emoji,
                "content": self.session.final_decision.content,
                "score": self.session.final_decision.score,
                "recommendation": self.session.final_decision.recommendation,
                "timestamp": self.session.final_decision.timestamp,
            } if self.session.final_decision else None,
        }
        
        # 原子写入：先写临时文件，再替换，避免写入中途崩溃导致会话丢失
        tmp = filepath + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, filepath)

        return filepath
    
    @classmethod
    def load_session(cls, filepath: str) -> 'WorkflowOrchestrator':
        """从JSON加载会话"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        session = AnalysisSession(
            stock_code=data["stock_code"],
            company_name=data["company_name"],
            session_id=data["session_id"],
            created_at=data["created_at"],
            current_stage=data["current_stage"],
        )
        
        # 恢复分析师报告
        for key, report_data in data.get("analyst_reports", {}).items():
            session.analyst_reports[key] = AnalysisResult(**report_data)
        
        # 恢复其他报告
        if data.get("bullish_report"):
            session.bullish_report = AnalysisResult(**data["bullish_report"])
        if data.get("bearish_report"):
            session.bearish_report = AnalysisResult(**data["bearish_report"])
        if data.get("trade_proposal"):
            session.trade_proposal = AnalysisResult(**data["trade_proposal"])
        if data.get("final_decision"):
            session.final_decision = AnalysisResult(**data["final_decision"])
        
        orch = cls(session)
        orch.current_stage_idx = orch.STAGES.index(session.current_stage)
        return orch


# 快捷函数
def create_workflow(stock_code: str, company_name: str = "") -> WorkflowOrchestrator:
    """创建新的分析工作流"""
    orch = WorkflowOrchestrator()
    orch.start_analysis(stock_code, company_name)
    return orch


if __name__ == "__main__":
    # 测试
    orch = create_workflow("AAPL", "Apple Inc.")
    print(f"当前阶段: {orch.session.current_stage}")
    prompt = orch.get_next_prompt()
    print(f"\n提示词预览:\n{(prompt or '')[:200]}...")
