# -*- coding: utf-8 -*-
"""`main.py` 入口冒烟测试。

## 为什么需要这个文件

工作交接文档把 `main.py` 的拆分评估列为待办 #2，并明确前置条件：

> 入口，无测试覆盖，验证手段弱；**需先补冒烟**

本文件提供该冒烟覆盖。**不触发任何 LLM 调用、网络请求或真实报告生成** ——
只验证入口的**控制流与契约**（哪些函数被调用、以什么顺序、异常路径是否安全）。

## 覆盖边界（刻意不覆盖的）

* 不验证报告内容质量 —— 那是 `reporting/` 的职责
* 不验证 Agent 分析逻辑 —— 那是 `agents_*` 的职责
* 不验证飞书推送实际送达 —— 那是 `notify/` 的职责
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

import main


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self, stock_code: str = "600519", stage: str = "analyst_fundamental"):
        self.session_id = "test-session"
        self.stock_code = stock_code
        self.company_name = "测试公司"
        self.current_stage = stage


class _FakeOrchestrator:
    """满足 main() 所需的最小契约。"""

    def __init__(self, completed: bool = True, stock_code: str = "600519"):
        self.session = _FakeSession(stock_code)
        self._completed = completed
        self.saved = 0

    def get_progress(self) -> Dict[str, Any]:
        return {"current_stage_name": "决策阶段", "progress_percent": 100 if self._completed else 40}

    def is_completed(self) -> bool:
        return self._completed

    def save_session(self, filepath: Optional[str] = None) -> str:
        self.saved += 1
        return filepath or "session.json"

    def get_next_prompt(self) -> Optional[str]:
        return None


@pytest.fixture
def isolated_main(monkeypatch):
    """把 main() 的外部依赖全部替换为替身，记录调用序列。"""
    calls: List[str] = []
    orch = _FakeOrchestrator()
    state: Dict[str, Any] = {"orch": orch, "calls": calls}

    def _team(tag: str):
        def _run(o: Any) -> None:
            calls.append(tag)
        return _run

    def _report(o: Any) -> str:
        calls.append("report")
        return "reports/x.html"

    def _push(s: Any, p: str) -> Dict[str, Any]:
        calls.append("feishu")
        return {"ok": True}

    monkeypatch.setattr(main, "load_existing_session", lambda: None)
    monkeypatch.setattr(main, "create_workflow", lambda code, name="": orch)
    monkeypatch.setattr(main, "run_analyst_team", _team("analyst"))
    monkeypatch.setattr(main, "run_research_team", _team("research"))
    monkeypatch.setattr(main, "run_decision_team", _team("decision"))
    monkeypatch.setattr(main, "generate_final_report", _report)
    monkeypatch.setattr(main, "is_configured", lambda: False)
    monkeypatch.setattr(main, "send_analysis_summary", _push)
    # 末尾会询问是否打开报告 —— 固定为「否」，避免测试真的拉起浏览器。
    # ask_yes_no 自身的解析契约由下方独立用例覆盖。
    monkeypatch.setattr(main, "ask_yes_no", lambda prompt, default=True: False)
    return state


# ---------------------------------------------------------------------------
# 输出类函数：不得崩溃
# ---------------------------------------------------------------------------

def test_print_helpers_do_not_crash(capsys):
    main.print_banner()
    main.print_stage_header("标题", "🚀", "说明")
    assert capsys.readouterr().out


def test_progress_bar_handles_normal_range(capsys):
    for pct in (0, 1, 50, 99, 100):
        main.print_progress_bar(pct)
    out = capsys.readouterr().out
    assert "0%" in out and "100%" in out


def test_progress_bar_survives_out_of_range(capsys):
    """越界进度不应抛异常（曾见调用方直接传入未裁剪的百分比）。"""
    main.print_progress_bar(-10)
    main.print_progress_bar(150)
    assert capsys.readouterr().out


# ---------------------------------------------------------------------------
# 输入类函数：重试与解析契约
# ---------------------------------------------------------------------------

def test_get_input_retries_until_non_empty(monkeypatch, capsys):
    answers = iter(["", "   ", "600519"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert main.get_input("代码: ") == "600519"
    assert "输入不能为空" in capsys.readouterr().out


def test_get_input_allows_empty_when_optional(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "  ")
    assert main.get_input("公司名: ", required=False) == ""


def test_get_input_exits_on_eof(monkeypatch):
    """EOF 应干净退出，而不是抛未捕获异常。"""
    def _raise(*a):
        raise EOFError
    monkeypatch.setattr("builtins.input", _raise)
    with pytest.raises(SystemExit) as exc:
        main.get_input("代码: ")
    assert exc.value.code == 0


def test_ask_yes_no_parsing(monkeypatch):
    cases = [
        ("", True, True), ("", False, False),
        ("y", True, True), ("Y", True, True), ("yes", True, True), ("是", True, True),
        ("n", True, False), ("N", True, False), ("no", True, False), ("否", True, False),
    ]
    for answer, default, expected in cases:
        monkeypatch.setattr("builtins.input", lambda *a, _v=answer: _v)
        assert main.ask_yes_no("?", default=default) is expected, f"输入 {answer!r} 解析错误"


def test_ask_yes_no_retries_on_invalid(monkeypatch, capsys):
    answers = iter(["maybe", "y"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert main.ask_yes_no("?") is True
    assert "请输入 y 或 n" in capsys.readouterr().out


def test_multiline_input_stops_on_end(monkeypatch):
    answers = iter(["第一行", "第二行", "END"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert main.get_multiline_input("输入: ") == "第一行\n第二行"


def test_multiline_input_stops_on_blank_after_content(monkeypatch):
    answers = iter(["第一行", "", "不应被读取"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert main.get_multiline_input("输入: ") == "第一行"


# ---------------------------------------------------------------------------
# main() 控制流
# ---------------------------------------------------------------------------

def test_main_new_session_runs_all_teams_in_order(isolated_main, monkeypatch):
    answers = iter(["600519", ""])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))

    main.main()

    assert isolated_main["calls"] == ["analyst", "research", "decision", "report"]
    assert isolated_main["orch"].saved == 1


def test_main_resume_session_skips_create(isolated_main, monkeypatch):
    """已有会话时应走续跑路径，不得再次 create_workflow。"""
    created: List[str] = []

    def _create(code: str, name: str = "") -> Any:
        created.append(code)
        return isolated_main["orch"]

    monkeypatch.setattr(main, "load_existing_session", lambda: isolated_main["orch"])
    monkeypatch.setattr(main, "create_workflow", _create)

    main.main()

    assert created == []
    assert isolated_main["calls"] == ["analyst", "research", "decision", "report"]


def test_main_incomplete_session_skips_report(monkeypatch):
    """未完成时应给出进度提示并跳过报告生成。"""
    calls: List[str] = []
    orch = _FakeOrchestrator(completed=False)

    def _team(tag: str):
        def _run(o: Any) -> None:
            calls.append(tag)
        return _run

    def _report(o: Any) -> str:
        calls.append("report")
        return "x.html"

    monkeypatch.setattr(main, "load_existing_session", lambda: orch)
    monkeypatch.setattr(main, "run_analyst_team", _team("analyst"))
    monkeypatch.setattr(main, "run_research_team", _team("research"))
    monkeypatch.setattr(main, "run_decision_team", _team("decision"))
    monkeypatch.setattr(main, "generate_final_report", _report)

    main.main()

    assert "report" not in calls


def test_main_pushes_to_feishu_when_configured(isolated_main, monkeypatch):
    monkeypatch.setattr(main, "is_configured", lambda: True)
    answers = iter(["600519", ""])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))

    main.main()

    assert "feishu" in isolated_main["calls"]


def test_main_survives_feishu_failure(isolated_main, monkeypatch):
    """飞书推送失败不得中断本地流程（契约：不影响报告生成）。"""
    monkeypatch.setattr(main, "is_configured", lambda: True)
    monkeypatch.setattr(main, "send_analysis_summary", lambda s, p: {"ok": False, "message": "boom"})
    answers = iter(["600519", ""])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))

    main.main()  # 不应抛出

    assert "report" in isolated_main["calls"]
