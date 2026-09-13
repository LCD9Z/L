# -*- coding: utf-8 -*-
"""
prompt_engine.py - AI股神系统 · 提示词引擎（L2）

职责：把 data_fetcher 抓到的"事实清单"与 8 个角色提示词组装成完整的
"分析指令包"，供模型执行。核心改进：
  - 每个阶段都携带【数据包】（真实数据）→ 杜绝模型编数字
  - 每个阶段都要求 JSON 结构化输出 → 可自动解析入库
  - 看多/看空改为基于同一事实清单【独立】论证 → 打破观点趋同
  - 交易员/风控基于多空论证裁决，并以数据包为事实基准

用法（配合 run_analysis.py）：
    python run_analysis.py 600519            # 取数并生成 8 阶段提示词
    python run_analysis.py 600519 --output xxx   # 指定输出目录
"""

import os
import json
from datetime import datetime
from typing import Optional

from agents import (
    FundamentalAnalyst, SentimentAnalyst, NewsAnalyst, TechnicalAnalyst,
    BullishResearcher, BearishResearcher, Trader, RiskManager,
)
from data_fetcher import build_fact_sheet, fact_sheet_to_text
from professional_committee import build_committee_prompt

# 8 个阶段的执行顺序与角色说明
STAGES = [
    ("analyst_fundamental", "📊 基本面分析师", "基本面分析"),
    ("analyst_sentiment", "🗣️ 情绪分析师", "市场情绪分析"),
    ("analyst_news", "📰 新闻分析师", "新闻与宏观分析"),
    ("analyst_technical", "📈 技术分析师", "技术面分析"),
    ("research_bullish", "🐂 看多研究员", "独立做多论证"),
    ("research_bearish", "🐻 看空研究员", "独立看空论证"),
    ("review_committee", "👥 专业评审委员会", "多专业独立压力测试"),
    ("decision_trade", "🧑‍💼 交易员", "综合裁决与交易策略"),
    ("decision_risk", "🛡️ 风控官&投资经理", "风险审批与最终决策"),
]

# 每个阶段输出的 JSON 文件（按顺序填写模型结果）
RESULT_FILES = {
    "analyst_fundamental": "01_fundamental.json",
    "analyst_sentiment": "02_sentiment.json",
    "analyst_news": "03_news.json",
    "analyst_technical": "04_technical.json",
    "research_bullish": "05_bullish.json",
    "research_bearish": "06_bearish.json",
    "review_committee": "07_committee.json",
    "decision_trade": "07_trade.json",
    "decision_risk": "08_risk.json",
}


def get_stage_prompt(stage: str, fact_sheet: dict, code: str,
                     company_name: str = "",
                     analyst_reports: Optional[list] = None,
                     bullish_report: str = "",
                     bearish_report: str = "",
                     trade_proposal: str = "",
                     committee_report: str = "") -> str:
    """生成指定阶段的提示词（带数据包）。"""

    def _content(reports):
        return [r if isinstance(r, str) else (r.get("content") or json.dumps(r, ensure_ascii=False))
                for r in (reports or [])]

    company = company_name or code
    if stage == "analyst_fundamental":
        return FundamentalAnalyst().generate_prompt(code, company, fact_sheet=fact_sheet)
    if stage == "analyst_sentiment":
        return SentimentAnalyst().generate_prompt(code, company, fact_sheet=fact_sheet)
    if stage == "analyst_news":
        return NewsAnalyst().generate_prompt(code, company, fact_sheet=fact_sheet)
    if stage == "analyst_technical":
        return TechnicalAnalyst().generate_prompt(code, company, fact_sheet=fact_sheet)
    if stage == "research_bullish":
        return BullishResearcher().generate_prompt(code, company, fact_sheet=fact_sheet)
    if stage == "research_bearish":
        return BearishResearcher().generate_prompt(code, company, fact_sheet=fact_sheet)
    if stage == "review_committee":
        prior = _content(analyst_reports) + [bullish_report or "", bearish_report or ""]
        return build_committee_prompt(code, company, fact_sheet, prior_reports=[x for x in prior if x])
    if stage == "decision_trade":
        base = Trader().generate_prompt(
            code, company,
            analyst_reports=_content(analyst_reports),
            bullish_report=bullish_report or "",
            bearish_report=bearish_report or "",
            fact_sheet=fact_sheet)
        return base + "\n\n【👥 专业评审委员会报告】\n" + (committee_report or "[委员会报告未提供]")
    if stage == "decision_risk":
        return RiskManager().generate_prompt(
            code, company,
            analyst_reports=_content(analyst_reports),
            bullish_report=bullish_report or "",
            bearish_report=bearish_report or "",
            trade_proposal=trade_proposal or "",
            fact_sheet=fact_sheet)
    raise ValueError(f"未知阶段: {stage}")


def build_analysis_package(code: str, company_name: str = "",
                           news_limit: int = 5,
                           existing_results: Optional[dict] = None) -> dict:
    """组装完整分析包。

    existing_results: 已有各阶段模型结果（dict: stage -> 模型返回文本/JSON），
                      用于把前面的结果注入后面的裁决类阶段。
    返回：{"code","company","fact_sheet","data_package","prompts": {stage: text}}
    """
    fact_sheet = build_fact_sheet(code, news_limit=news_limit)
    results = existing_results or {}

    def _txt(stage):
        v = results.get(stage)
        if not v:
            return ""
        if isinstance(v, str):
            return v
        return json.dumps(v, ensure_ascii=False)

    # 分析师报告列表（供交易/风控引用）
    analyst_reports = [_txt(s) for s in
                       ("analyst_fundamental", "analyst_sentiment",
                        "analyst_news", "analyst_technical")
                       if _txt(s)]

    prompts = {}
    for stage, _, _name in STAGES:
        prompts[stage] = get_stage_prompt(
            stage, fact_sheet, code, company_name,
            analyst_reports=analyst_reports,
            bullish_report=_txt("research_bullish"),
            bearish_report=_txt("research_bearish"),
            trade_proposal=_txt("decision_trade"),
            committee_report=_txt("review_committee"),
        )

    return {
        "code": code,
        "company": company_name or fact_sheet.get("quote", {}).get("name") or code,
        "fact_sheet": fact_sheet,
        "data_package": fact_sheet_to_text(fact_sheet),
        "prompts": prompts,
    }


def save_package(pkg: dict, output_dir: Optional[str] = None) -> str:
    """把分析包落盘：每个阶段一个 txt + 一个数据包 txt。返回输出目录。"""
    code = pkg["code"]
    if output_dir is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "reports", f"{code}_prompts_{ts}")
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "00_数据包.txt"), "w", encoding="utf-8") as f:
        f.write(pkg["data_package"])

    for stage, _emoji, _name in STAGES:
        path = os.path.join(output_dir, RESULT_FILES[stage].replace(".json", ".txt"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(pkg["prompts"][stage])

    with open(os.path.join(output_dir, "package.json"), "w", encoding="utf-8") as f:
        json.dump({
            "code": pkg["code"],
            "company": pkg["company"],
            "stages": [s[0] for s in STAGES],
            "result_files": RESULT_FILES,
        }, f, ensure_ascii=False, indent=2)

    return output_dir


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    pkg = build_analysis_package(code)
    out = save_package(pkg)
    print(f"✅ 分析包已生成：{out}")
    print(f"   股票：{pkg['company']} ({pkg['code']})")
    print(f"   数据来源：{pkg['fact_sheet'].get('meta', {}).get('data_source')}")
    for _stage, _e, name in STAGES:
        print(f"   - {name}")
