# -*- coding: utf-8 -*-
"""多 Agent 团队的交互式流程执行。

从 `main.py` 迁出并**去重**：原 `run_analyst_team` / `run_research_team` /
`run_decision_team` 三个函数共 164 行，结构约 90% 相同，差异仅在
「阶段列表 + 评分/建议的提示文案 + 完成词」。此处用 :class:`StageSpec`
参数化，三处调用收敛为同一实现。

**行为保持**：阶段顺序、提示文案、保存路径、进度打印、提交时机均与原实现一致。
唯一的防御性改动：`reports/` 目录改为**无条件**创建（原实现仅分析师路径创建，
其余两处依赖它已存在）。

共同红线：

* **阶段不匹配就跳过**，不得推进非当前阶段 —— 会话可能从任意阶段续跑。
* **空输入不提交**：用户粘贴为空时跳过该阶段，不写入空结果污染会话。
* **每次提交后立即保存**：交互式流程随时可能被中断。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List, Sequence

from .display import (
    Colors,
    get_input,
    get_multiline_input,
    print_progress_bar,
    print_stage_header,
)


@dataclass(frozen=True)
class StageSpec:
    """一个交互阶段的完整规格。"""

    stage: str          # 阶段 id，用于与会话当前阶段比对
    title: str          # 阶段标题
    desc: str           # 阶段说明
    score_prompt: str   # 评分输入提示
    advice_prompt: str  # 建议输入提示
    done_word: str      # 完成语（"分析已完成" / "论证已完成" / "决策已完成"）
    copy_hint: str      # 提示词复制提示语


_ANALYST_HINT = "📝 请将此提示词复制到TRAE聊天中，获取AI分析结果："
_PLAIN_HINT = "📝 请将此提示词复制到TRAE聊天中："

ANALYST_STAGES: List[StageSpec] = [
    StageSpec("analyst_fundamental", "📊 基本面分析师", "深度挖掘公司财务与价值",
              "评分 (1-10，如无可直接回车跳过): ",
              "投资建议 (如：强烈买入/买入/持有/卖出/强烈卖出): ",
              "分析", _ANALYST_HINT),
    StageSpec("analyst_sentiment", "🗣️ 情绪分析师", "追踪市场情绪与舆情",
              "评分 (1-10，如无可直接回车跳过): ",
              "投资建议 (如：强烈买入/买入/持有/卖出/强烈卖出): ",
              "分析", _ANALYST_HINT),
    StageSpec("analyst_news", "📰 新闻分析师", "解读宏观事件与公司动态",
              "评分 (1-10，如无可直接回车跳过): ",
              "投资建议 (如：强烈买入/买入/持有/卖出/强烈卖出): ",
              "分析", _ANALYST_HINT),
    StageSpec("analyst_technical", "📈 技术分析师", "分析价格行为与技术指标",
              "评分 (1-10，如无可直接回车跳过): ",
              "投资建议 (如：强烈买入/买入/持有/卖出/强烈卖出): ",
              "分析", _ANALYST_HINT),
]

RESEARCH_STAGES: List[StageSpec] = [
    StageSpec("research_bullish", "🐂 看多研究员", "寻找买入理由，构建做多逻辑",
              "强度评分 (1-10): ",
              "建议 (如：重仓/中等/轻仓/卖出/观望): ",
              "论证", _PLAIN_HINT),
    StageSpec("research_bearish", "🐻 看空研究员", "寻找风险信号，构建避险逻辑",
              "强度评分 (1-10): ",
              "建议 (如：重仓/中等/轻仓/卖出/观望): ",
              "论证", _PLAIN_HINT),
]

DECISION_STAGES: List[StageSpec] = [
    StageSpec("decision_trade", "🧑‍💼 交易员", "综合研判，制定交易策略",
              "信心评分 (1-10): ",
              "交易指令 (如：强烈买入/买入/持有/卖出/强烈卖出): ",
              "决策", _PLAIN_HINT),
    StageSpec("decision_risk", "🛡️ 风控官&投资经理", "风险评估，最终审批",
              "风险等级 (1-10): ",
              "审批结果 (如：批准/拒绝/有条件批准): ",
              "决策", _PLAIN_HINT),
]


def run_team(orch: Any, stages: Sequence[StageSpec]) -> None:
    """按规格执行一组阶段；只处理与会话当前阶段匹配的那一个。"""
    for spec in stages:
        if orch.session.current_stage != spec.stage:
            continue

        print_stage_header(spec.title, spec.title[0], spec.desc)

        prompt = orch.get_next_prompt()
        if not prompt:
            print(f"{Colors.WARNING}⚠️ 该阶段无可用提示词，跳过：{spec.stage}{Colors.END}")
            continue

        print(f"{Colors.BOLD}{spec.copy_hint}{Colors.END}\n")
        print(f"{Colors.WARNING}{'─' * 70}{Colors.END}")
        print(prompt)
        print(f"{Colors.WARNING}{'─' * 70}{Colors.END}\n")

        prompt_file = f"reports/{orch.session.session_id}_{spec.stage}_prompt.txt"
        os.makedirs("reports", exist_ok=True)
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"{Colors.GREEN}✅ 提示词已保存到: {prompt_file}{Colors.END}\n")

        print(f"{Colors.BOLD}📥 请将AI返回的分析结果粘贴 below (输入空行结束):{Colors.END}")
        result = get_multiline_input("")
        if not result.strip():
            print(f"{Colors.WARNING}⚠️  未输入内容，跳过此步骤。{Colors.END}")
            continue

        score_str = get_input(spec.score_prompt, required=False)
        score = float(score_str) if score_str else None
        recommendation = get_input(spec.advice_prompt, required=False)

        orch.submit_result(spec.stage, result, score, recommendation)
        orch.save_session()

        progress = orch.get_progress()
        print_progress_bar(progress["progress_percent"])
        print(f"{Colors.GREEN}✅ {spec.title} {spec.done_word}已完成并保存！{Colors.END}\n")


def run_analyst_team(orch: Any) -> None:
    """运行分析师团队。"""
    run_team(orch, ANALYST_STAGES)


def run_research_team(orch: Any) -> None:
    """运行研究员团队（辩论）。"""
    run_team(orch, RESEARCH_STAGES)


def run_decision_team(orch: Any) -> None:
    """运行决策团队。"""
    run_team(orch, DECISION_STAGES)
