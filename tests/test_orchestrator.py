# -*- coding: utf-8 -*-
"""`orchestrator.py` 的行为测试。

## 为什么补这个文件

`orchestrator.py`（337 行，含一个 278 行的编排类）是项目核心，
却长期**无任何直接测试**（`grep -rn orchestrator tests/` 只命中一个检查拆分的用例）。
补齐后立刻发现一个**严重缺陷**：

    WorkflowOrchestrator.load_session() 必然抛
    TypeError: AnalysisResult.__init__() missing 1 required positional argument: 'analysis_type'

根因：`save_session` 在 5 处内联 dict 里都漏写了 `analysis_type`，
而该字段在 `AnalysisResult` 中是**必填**（无默认值）。
后果：**会话恢复功能完全不可用**，且因无测试而长期未被发现。

修复见 `orchestrator.WorkflowOrchestrator._serialize_result()`。
本文件除覆盖该缺陷外，还提供一条**通用守卫**
（`test_serialized_keys_are_accepted_by_analysis_result`），
拦截整类「save 写的字段 load 读不了」的问题，而不只是这一个字段。
"""
from __future__ import annotations

import dataclasses
import json
import os

import pytest
from agents import AnalysisResult
from orchestrator import AnalysisSession, WorkflowOrchestrator, create_workflow

#: 除 waiting_input / completed 外，每个阶段应产出一个非空提示词
AGENT_STAGES = (
    "analyst_fundamental",
    "analyst_sentiment",
    "analyst_news",
    "analyst_technical",
    "research_bullish",
    "research_bearish",
    "decision_trade",
    "decision_risk",
)

#: 与 AGENT_STAGES 一一对应、`submit_result` 应写入的会话字段
STAGE_TO_FIELD = {
    "analyst_fundamental": "analyst_reports",
    "analyst_sentiment": "analyst_reports",
    "analyst_news": "analyst_reports",
    "analyst_technical": "analyst_reports",
    "research_bullish": "bullish_report",
    "research_bearish": "bearish_report",
    "decision_trade": "trade_proposal",
    "decision_risk": "final_decision",
}


def _fresh() -> WorkflowOrchestrator:
    return create_workflow("600519", "贵州茅台")


# ---------------------------------------------------------------------------
# 会话与阶段推进
# ---------------------------------------------------------------------------

def test_session_autofills_id_and_created_at():
    """`AnalysisSession` 必须自动补齐 session_id 与 created_at。

    下游（report_generator 等）直接索引这些字段，为空会导致文件名异常。
    """
    s = AnalysisSession(stock_code="600519")
    assert s.session_id.startswith("600519_")
    assert s.created_at
    # 非 None 的 dict：下游直接索引，声明成 Optional 会让每次访问都要判空
    assert s.analyst_reports == {}


def test_start_analysis_normalizes_code_and_enters_first_stage():
    """股票代码须规范为大写，并直接进入第一个分析阶段（跳过 waiting_input）。"""
    orch = WorkflowOrchestrator()
    session = orch.start_analysis("sh600519")

    assert session.stock_code == "SH600519"
    assert session.company_name == "SH600519", "未给公司名时应回退为代码"
    assert session.current_stage == "analyst_fundamental"
    assert orch.current_stage_idx == 1, "应从第一个分析阶段开始，而非 waiting_input"


def test_start_analysis_keeps_given_company_name():
    orch = WorkflowOrchestrator()
    session = orch.start_analysis("600519", "贵州茅台")
    assert session.company_name == "贵州茅台"


def test_get_next_prompt_non_empty_for_every_agent_stage():
    """每个 Agent 阶段都应产出非空提示词（含需要前序报告的研究员/决策层）。"""
    orch = _fresh()
    for stage in AGENT_STAGES:
        orch.session.current_stage = stage
        prompt = orch.get_next_prompt()
        assert isinstance(prompt, str) and prompt.strip(), f"{stage} 未产出提示词"


def test_get_next_prompt_returns_none_when_not_actionable():
    """waiting_input 与 completed 阶段无提示词可给 —— 返回 None 而非空串。"""
    orch = _fresh()
    for stage in ("waiting_input", "completed"):
        orch.session.current_stage = stage
        assert orch.get_next_prompt() is None


def test_researcher_and_decision_prompts_survive_missing_prior_reports():
    """前序报告缺失时不得崩溃（研究员/决策层需要前序内容）。

    首次运行或会话从中间恢复时，前序报告可能为空 —— 此时应产出提示词，
    而不是抛 AttributeError。
    """
    orch = _fresh()
    for stage in ("research_bearish", "decision_trade", "decision_risk"):
        orch.session.current_stage = stage
        assert orch.get_next_prompt()


def test_submit_result_routes_to_the_correct_session_field():
    """每种 agent_type 必须落到对应字段 —— 落错会让报告生成器读不到内容。"""
    orch = _fresh()
    for stage, field_name in STAGE_TO_FIELD.items():
        orch.session.current_stage = stage
        orch.submit_result(stage, f"{stage} 的内容", score=7.5, recommendation="Hold")

        if field_name == "analyst_reports":
            assert stage in orch.session.analyst_reports
            got = orch.session.analyst_reports[stage]
        else:
            got = getattr(orch.session, field_name)

        assert got is not None, f"{stage} 未写入 {field_name}"
        assert got.content == f"{stage} 的内容"
        assert got.analysis_type == stage
        assert got.score == 7.5
        assert got.recommendation == "Hold"


def test_submit_result_advances_through_all_stages_to_completed():
    """连续提交 8 个阶段的结果后应到达 completed，且进度为 100%。"""
    orch = _fresh()
    for stage in AGENT_STAGES:
        orch.session.current_stage = stage
        orch.submit_result(stage, "内容")

    assert orch.session.current_stage == "completed"
    assert orch.is_completed()
    assert orch.get_progress()["progress_percent"] == 100


def test_advance_stage_does_not_overrun_the_end():
    """在 completed 上再推进不得越界（原实现在末阶段会 IndexError）。"""
    orch = _fresh()
    orch.session.current_stage = "completed"
    orch._advance_stage()  # noqa: SLF001
    assert orch.session.current_stage == "completed"

    # 未知阶段同样不得崩溃，也不应改变状态
    orch.session.current_stage = "not_a_real_stage"
    orch._advance_stage()  # noqa: SLF001
    assert orch.session.current_stage == "not_a_real_stage"


def test_progress_counts_completed_stages_correctly():
    """已完成阶段列表必须与实际推进一致，且不含 waiting_input。"""
    orch = _fresh()
    progress = orch.get_progress()

    assert progress["total_stages"] == len(WorkflowOrchestrator.STAGES) - 1
    assert progress["current_stage"] == "analyst_fundamental"
    assert progress["completed_stages"] == [], "刚进入第一阶段时不应有已完成阶段"
    assert "waiting_input" not in progress["completed_stages"]

    orch.submit_result("analyst_fundamental", "内容")
    progress = orch.get_progress()
    assert progress["completed_stages"] == ["analyst_fundamental"]
    assert progress["progress_percent"] > 0


def test_unknown_agent_type_gets_placeholder_labels_without_crashing():
    """未知 agent_type 不得崩溃；标签用占位符（便于定位上游传参错误）。"""
    orch = _fresh()
    orch.submit_result("analyst_unknown", "内容")
    result = orch.session.analyst_reports["analyst_unknown"]
    assert result.agent_name == "未知Agent"
    assert result.agent_emoji == "❓"


def test_stages_is_immutable_tuple():
    """`STAGES` 必须是不可变元组。

    历史缺陷：原为 list 类属性 —— 可变类属性会被**所有实例共享**，
    任何一处 `STAGES.append(...)` 都会污染全局阶段表。
    """
    assert isinstance(WorkflowOrchestrator.STAGES, tuple)
    assert "waiting_input" in WorkflowOrchestrator.STAGES
    assert WorkflowOrchestrator.STAGES[-1] == "completed"


# ---------------------------------------------------------------------------
# 会话持久化（缺陷所在）
# ---------------------------------------------------------------------------

def test_save_load_round_trip_preserves_all_reports(tmp_path):
    """存盘再读回必须完整还原 —— 这是 `load_session` 曾必然失败的地方。

    历史缺陷：`save_session` 漏写 `analysis_type`（`AnalysisResult` 的必填字段），
    导致 `load_session` 抛 TypeError，会话恢复功能完全不可用。
    """
    orch = _fresh()
    orch.submit_result("analyst_fundamental", "基本面内容", score=8.0, recommendation="Buy")
    orch.submit_result("research_bullish", "看多内容")

    path = str(tmp_path / "session.json")
    orch.save_session(path)
    loaded = WorkflowOrchestrator.load_session(path)

    # 会话头字段
    assert loaded.session.stock_code == orch.session.stock_code
    assert loaded.session.company_name == orch.session.company_name
    assert loaded.session.session_id == orch.session.session_id
    assert loaded.session.created_at == orch.session.created_at
    assert loaded.session.current_stage == orch.session.current_stage

    # 分析师报告（逐字段比对）
    original = orch.session.analyst_reports["analyst_fundamental"]
    restored = loaded.session.analyst_reports["analyst_fundamental"]
    for f in dataclasses.fields(AnalysisResult):
        assert getattr(restored, f.name) == getattr(original, f.name), f"字段 {f.name} 往返不一致"

    # 单值报告
    assert loaded.session.bullish_report is not None
    assert loaded.session.bullish_report.content == "看多内容"
    assert loaded.session.bullish_report.analysis_type == "research_bullish"
    assert loaded.session.bearish_report is None, "未提交的报告应保持 None"


def test_load_session_restores_stage_index(tmp_path):
    """恢复后的 `current_stage_idx` 必须与阶段匹配，否则进度条会错位。"""
    orch = _fresh()
    for stage in ("analyst_fundamental", "analyst_sentiment"):
        orch.submit_result(stage, "内容")

    path = str(tmp_path / "session.json")
    orch.save_session(path)
    loaded = WorkflowOrchestrator.load_session(path)

    assert loaded.current_stage_idx == WorkflowOrchestrator.STAGES.index(
        loaded.session.current_stage
    )
    assert loaded.get_progress() == orch.get_progress()


def test_serialized_keys_are_accepted_by_analysis_result():
    """**通用守卫**：序列化键集合必须与 `AnalysisResult` 的字段契约一致。

    拦的不是某个具体缺陷，而是整类「save 写的字段 load 读不了」的问题：
    - 写出 dataclass 不认识的键 → `TypeError: unexpected keyword argument`
    - 漏写无默认值的必填字段 → `TypeError: missing required positional argument`
    本次的 `analysis_type` 缺失即属后者。新增字段时这条会立刻失败。
    """
    fields = {f.name for f in dataclasses.fields(AnalysisResult)}
    required = {
        f.name
        for f in dataclasses.fields(AnalysisResult)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }

    sample = AnalysisResult(
        agent_name="测试", agent_emoji="🧪", analysis_type="analyst_test", content="内容"
    )
    serialized = WorkflowOrchestrator._serialize_result(sample)  # noqa: SLF001

    assert serialized is not None
    unknown = set(serialized) - fields
    assert not unknown, f"序列化写出了 AnalysisResult 不认识的字段: {sorted(unknown)}"

    missing = required - set(serialized)
    assert not missing, (
        f"序列化缺少必填字段（load_session 会抛 TypeError）: {sorted(missing)}"
    )

    # 反向：序列化结果必须真的能被反序列化回来
    assert AnalysisResult(**serialized) == sample


def test_serialize_result_passes_none_through():
    """None 必须原样返回 —— 未提交的报告在 JSON 中应是 null，而非空对象。"""
    assert WorkflowOrchestrator._serialize_result(None) is None  # noqa: SLF001


def test_save_session_accepts_bare_filename(tmp_path, monkeypatch):
    """裸文件名（不含目录）必须可用。

    历史缺陷：原实现无条件 `os.makedirs(os.path.dirname(path))`，
    而裸文件名的 dirname 是空串 → `FileNotFoundError`。
    """
    monkeypatch.chdir(tmp_path)
    orch = _fresh()
    returned = orch.save_session("bare_session.json")

    assert returned == "bare_session.json"
    assert (tmp_path / "bare_session.json").is_file()


def test_save_session_writes_atomically_and_leaves_no_temp_file(tmp_path):
    """原子写入：先写 .tmp 再 replace，且成功后不留临时文件。"""
    orch = _fresh()
    path = tmp_path / "s.json"
    orch.save_session(str(path))

    assert path.is_file()
    assert not (tmp_path / "s.json.tmp").exists(), "临时文件未清理"

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["stock_code"] == "600519"
    assert payload["current_stage"] == orch.session.current_stage


def test_save_session_creates_missing_parent_directories(tmp_path):
    """多级不存在的目录应被自动创建。"""
    orch = _fresh()
    path = tmp_path / "deep" / "nested" / "s.json"
    orch.save_session(str(path))
    assert path.is_file()


def test_load_session_of_unknown_stage_raises_value_error(tmp_path):
    """文件里的 current_stage 不在 STAGES 中时应显式报错，而非静默错位。

    静默容忍会让进度条与阶段推进基于错误前提运行 —— 属本项目最警惕的
    「看起来正常、实际错误」。
    """
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "stock_code": "600519",
                "company_name": "贵州茅台",
                "session_id": "x",
                "created_at": "2026-01-01 00:00:00",
                "current_stage": "not_a_real_stage",
                "analyst_reports": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        WorkflowOrchestrator.load_session(str(path))


def test_create_workflow_helper_returns_started_orchestrator():
    """快捷函数应等价于「构造 + start_analysis」。"""
    orch = create_workflow("000001", "平安银行")
    assert isinstance(orch, WorkflowOrchestrator)
    assert orch.session.current_stage == "analyst_fundamental"
    assert orch.session.company_name == "平安银行"
    assert os.path.basename(orch.session.session_id).startswith("000001_")
