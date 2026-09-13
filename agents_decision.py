# -*- coding: utf-8 -*-
"""AI股神团队 - 决策团队（交易员 / 风控官）。

交易员综合研判并给出指令，风控官拥有最终审批与一票否决权。
由 agents.py 拆分而来（1.0）。
"""

from typing import List, Optional

from agents_base import BaseAgent, _json_block, pack_data


class Trader(BaseAgent):
    """交易员Agent"""
    def __init__(self):
        super().__init__("交易员", "🧑‍💼", "trader")
        self.system_prompt = """你是一位冷静、客观的首席交易员，拥有最终决定权。

核心指令：
1. 综合研判：阅读多头和空头研究员的辩论记录，权衡双方论据的力度。
2. 制定策略：基于所有信息，决定具体的交易行动（买入 Buy、卖出 Sell 或 持有 Hold）。
3. 确定细节：如果决定交易，需明确交易的时机、方向和理由。
4. 输出：提交一份包含明确交易指令的初步提案。

请用中文输出，保持冷静客观。"""
    
    def generate_prompt(self, stock_code: str, company_name: str = "",
                       analyst_reports: Optional[List[str]] = None,
                       bullish_report: str = "",
                       bearish_report: str = "",
                       fact_sheet: Optional[dict] = None) -> str:
        company = company_name or stock_code
        data_block = pack_data(fact_sheet)
        
        return f"""【🧑‍💼 交易员决策任务】

股票：{stock_code} ({company})

{data_block}

{'='*50}
【分析师团队报告汇总】
{chr(10).join(analyst_reports) if analyst_reports else '[分析师报告将在此处插入]'}
{'='*50}

【🐂 看多研究员观点】
{bullish_report or '[看多报告将在此处插入]'}
{'='*50}

【🐻 看空研究员观点】
{bearish_report or '[看空报告将在此处插入]'}
{'='*50}

作为首席交易员，你需要：

1. 综合评估
   - 以【数据包】中的真实数据为基准，校验多空双方观点的数据依据是否成立
   - 对引用数据包中不存在的数据的观点，标注【数据存疑】
   - 权衡多空双方论据强度，识别关键因素

2. 制定交易策略
   - 明确交易方向（买入/卖出/持有）
   - 入场时机（立即/等待回调/等待突破）
   - 建议仓位大小（基于信心水平）
   - 持有周期

3. 风险管理
   - 建议止损位（须给出具体价位及依据）
   - 目标收益位
   - 风险收益比评估

4. 执行计划
   - 具体交易执行方案
   - 加仓/减仓策略
   - 退出条件

{_json_block('''{"交易指令":"强烈买入/买入/持有/卖出/强烈卖出","股票代码":"...","信心评分":X(1-10),"建议仓位%":X,"目标价":X,"止损价":X,"风险收益比":X,"关键执行条件":["..."],"数据存疑点":["观点引用了数据包中没有的数据"]}''')}
"""


class RiskManager(BaseAgent):
    """风控与投资组合经理"""
    def __init__(self):
        super().__init__("风控官&投资经理", "🛡️", "risk")
        self.system_prompt = """你是一位严格的风控官，你的首要任务是保护本金。

核心指令：
1. 审核提案：审查交易员提交的交易提案。
2. 风险评估：检查仓位、成交额、换手率、波动率、最大回撤、涨跌停/停牌/T+1等A股交易约束；数据包未提供的组合风险指标标注【未知】。
3. 一票否决：如果交易风险过高（如仓位过重、逆势操作），你有权拒绝或修正交易指令。
4. 最终执行：给出一个风险等级的评分，评分范围：1-10分。

请用中文输出，严格保守。"""
    
    def generate_prompt(self, stock_code: str, company_name: str = "",
                       analyst_reports: Optional[List[str]] = None,
                       bullish_report: str = "",
                       bearish_report: str = "",
                       trade_proposal: str = "",
                       fact_sheet: Optional[dict] = None) -> str:
        company = company_name or stock_code
        data_block = pack_data(fact_sheet)
        
        return f"""【🛡️ 风控与投资经理审批任务】

股票：{stock_code} ({company})

{data_block}

{'='*50}
【分析师团队报告汇总】
{chr(10).join(analyst_reports) if analyst_reports else '[分析师报告将在此处插入]'}
{'='*50}

【🐂 看多研究员观点】
{bullish_report or '[看多报告将在此处插入]'}
{'='*50}

【🐻 看空研究员观点】
{bearish_report or '[看空报告将在此处插入]'}
{'='*50}

【🧑‍💼 交易员提案】
{trade_proposal or '[交易提案将在此处插入]'}
{'='*50}

作为风控官与投资组合经理，你需要：

1. 全面风险评估（以数据包真实数据为准）
   - 流动性风险：成交额、换手率是否足以支持该仓位（数据包已给出）
   - 波动风险：振幅、涨跌幅反映的当日波动水平
   - 估值风险：PE/PB 是否处于明显高位
   - 集中度/相关性风险：与现有持仓的关系（无组合信息时标注【未知】）
   - 尾部风险：数据包未覆盖的黑天鹅可能（标注【未知】）

2. 交易员提案审核
   - 仓位建议是否与成交额/换手率匹配
   - 止损设置是否充分（相对当日振幅是否合理）
   - 风险收益比是否可接受（至少 1:2）

3. 一票否决权行使
   - 风险过高 → 明确拒绝并说明理由
   - 可修正 → 提出调整建议（降低仓位、调整止损等）
   - 风险可控 → 批准

4. 最终决策
   - 审批结果
   - 最终仓位建议
   - 风险等级评分（1-10，10为最高风险）
   - 关键监控指标

{_json_block('''{"审批结果":"批准/拒绝/有条件批准","股票代码":"...","风险等级":X(1-10,10最高),"修正建议":["..."],"最终仓位建议%":X,"最终交易指令":"...","关键监控指标":["..."],"一票否决理由":"如适用","数据缺口":["..."]}''')}
"""
