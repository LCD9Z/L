# -*- coding: utf-8 -*-
"""AI股神团队 - Agent 基类与数据包注入。

本模块是 Agent 层的公共基础设施，由 agents.py 拆分而来（1.0）：

    DATA_RULES      全局铁律：只能依据数据包分析，禁止编造数字
    _json_block()   生成 JSON 输出格式要求块
    pack_data()     把事实清单渲染为提示词开头的【数据包】+【铁律】
    AnalysisResult  分析结果数据结构
    BaseAgent       Agent 基类（子类实现 generate_prompt）
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional
from datetime import datetime

# ---------------------------------------------------------------- L2 增强
# 数据包注入：把 data_fetcher 抓到的"事实清单"接入各角色提示词。
# 若 data_fetcher 不可用（如被单独拷贝），静默降级，不影响原有功能。
fact_sheet_to_text: Optional[Callable[[dict], str]] = None
try:
    from data_fetcher import fact_sheet_to_text as _fact_sheet_to_text
    fact_sheet_to_text = _fact_sheet_to_text
except Exception:
    pass


# 全局铁律：仅基于给定数据包，禁止编造数字，标注来源
DATA_RULES = """【铁律 - 必须遵守】
1. 你只能依据【数据包】中给出的数据进行分析，禁止使用记忆中模糊的价格、业绩或消息；
2. 数据包未提供的任何指标（如营收、净利、库存、资金流），一律标注【数据未获取】，不得编造、不得猜测数值；
3. 每个关键数字后标注来源：【已核实】= 数据包内明确给出；【推断】= 基于数据包的合理推导；【未知】= 无数据；
4. 最终必须输出固定 JSON（见输出格式），不得输出多余解释字段，JSON 外可附 1-2 句简短说明。"""


def _json_block(schema_desc: str) -> str:
    """生成 JSON 输出要求块。schema_desc 为该角色的 JSON 字段说明。"""
    return f"""【输出格式 - 必须输出合法 JSON】
{schema_desc}
⚠️ 请仅输出该 JSON，不要输出 JSON 之外的正文；如果确实无法判断，对应字段填 null。"""


def pack_data(fact_sheet: Optional[dict]) -> str:
    """把事实清单渲染为提示词开头的【数据包】+【铁律】块。"""
    if not fact_sheet:
        return ""
    body = ""
    if fact_sheet_to_text is not None:
        body = fact_sheet_to_text(fact_sheet)
    else:
        # 降级：手动渲染
        q = fact_sheet.get("quote", {})
        body = f"【数据包】股票：{q.get('name')} ({q.get('code')}) 最新价：{q.get('price')} 涨跌幅：{q.get('change_pct')}%"
    return f"{body}\n\n{DATA_RULES}"


@dataclass
class AnalysisResult:
    """分析结果数据结构"""
    agent_name: str
    agent_emoji: str
    analysis_type: str
    content: str
    signals: List[str] = field(default_factory=list)
    score: Optional[float] = None  # 1-10分
    recommendation: Optional[str] = None  # Buy/Sell/Hold
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class BaseAgent:
    """Agent基类"""
    def __init__(self, name: str, emoji: str, role: str):
        self.name = name
        self.emoji = emoji
        self.role = role
        self.system_prompt = ""
    
    def generate_prompt(self, stock_code: str, company_name: str = "") -> str:
        """生成分析提示词 - 子类需重写"""
        raise NotImplementedError
    
    def parse_response(self, response: str) -> AnalysisResult:
        """解析AI返回的分析结果"""
        return AnalysisResult(
            agent_name=self.name,
            agent_emoji=self.emoji,
            analysis_type=self.role,
            content=response
        )
