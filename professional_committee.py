# -*- coding: utf-8 -*-
"""多专业独立评审委员会：让同一事实包接受不同专业视角的压力测试。"""
from __future__ import annotations
import json
from typing import Dict, List

ROLES = [
    ("quant", "量化研究员", "检验因子定义、数据泄漏、样本外、稳健性、基准与交易成本"),
    ("fundamental", "基本面基金经理", "检验盈利质量、现金流、估值、行业竞争力与会计风险"),
    ("ashare_trader", "A股资深交易员", "检验T+1、涨跌停、停牌、流动性、成交结构与执行可行性"),
    ("microstructure", "市场微观结构专家", "检验盘口/成交额/换手、冲击成本、封板/开板与异常交易"),
    ("risk", "首席风险官", "检验仓位、回撤、尾部风险、集中度、流动性与否决条件"),
    ("data_engineer", "数据与点时态审计师", "检验来源、发布时间、复权、公司行动、幸存者偏差和未来函数"),
    ("news", "事件与舆情研究员", "检验公告/新闻真实性、直接相关性、时间有效性与情绪反转风险"),
]


def build_committee_prompt(stock_code: str, company: str,
                         fact_sheet: Dict | None, prior_reports: List[str] | None = None) -> str:
    from agents import pack_data
    reports = "\n\n".join(prior_reports or []) or "[前序报告未提供]"
    machine_checks = json.dumps(deterministic_checks(fact_sheet), ensure_ascii=False, indent=2)
    role_text = "\n".join(f"{i}. {name}：{focus}" for i, (_, name, focus) in enumerate(ROLES, 1))
    return f"""【专业评审委员会｜{stock_code} {company}】
你不是一个观点统一的团队，而是7名互相独立、允许否决彼此结论的专家。

{pack_data(fact_sheet)}

【前序分析报告】
{reports}

【机器硬门槛检查（不可由LLM改写）】
{machine_checks}

【专家席位】
{role_text}

要求：
1. 每位专家只能基于数据包和前序报告中明确存在的事实；没有数据就写【数据未获取】。
2. 先指出最强的反对理由，再给结论，避免“大家都看多”的群体偏差。
3. 明确区分“研究观点”和“可执行交易”。
4. A股执行专家必须检查T+1、涨跌停、停牌、可卖性、流动性等约束。
5. 数据审计专家必须检查发布时间/研究时点、复权口径、幸存者偏差、未来函数。
6. 最终由委员会主席汇总：共识、分歧、否决项、必须补数项、建议是否进入交易决策。

只输出合法JSON：
{{
  "股票代码":"{stock_code}",
  "专家评审":[{{"角色":"量化研究员","结论":"...","评分":null,"主要风险":["..."],"数据缺口":["..."]}}],
  "共识":["..."],
  "关键分歧":["..."],
  "一票否决项":["..."],
  "必须补充数据":["..."],
  "主席结论":"进入交易决策/暂缓/否决",
  "主席理由":["..."]
}}
"""


def deterministic_checks(fact_sheet: Dict | None) -> Dict:
    """不调用LLM的硬门槛，给委员会提供可复核的机器审计结果。"""
    q = (fact_sheet or {}).get("quote", {})
    meta = (fact_sheet or {}).get("meta", {})
    news = (fact_sheet or {}).get("news", [])
    kline = (fact_sheet or {}).get("kline", [])
    quote_board = (fact_sheet or {}).get("quote", {}).get("board")
    checks = {
        "quote_price_available": q.get("price") is not None,
        "quote_time_available": bool(q.get("quote_time")),
        "kline_rows": len(kline),
        "news_rows": len(news),
        "crawl4ai_enabled": bool(meta.get("crawl4ai_enabled")),
        "historical_cutoff_set": bool(meta.get("cutoff_time")),
        "news_with_published_at": sum(1 for x in news if x.get("published_at")),
        "news_without_published_at": sum(1 for x in news if not x.get("published_at")),
        "amount_available": q.get("amount") is not None,
        "turnover_available": q.get("turnover") is not None,
        "board": quote_board,
        "t_plus_one": True,
    }
    hard_fail = []
    if not checks["quote_price_available"]:
        hard_fail.append("缺少实时价格")
    if checks["historical_cutoff_set"] and checks["news_without_published_at"]:
        hard_fail.append("历史研究存在无发布时间新闻")
    return {"checks": checks, "hard_fail": hard_fail, "pass": not hard_fail}


def committee_context(fact_sheet: Dict | None, prior_reports: List[str] | None = None) -> str:
    return json.dumps(deterministic_checks(fact_sheet), ensure_ascii=False, indent=2)
