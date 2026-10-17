# -*- coding: utf-8 -*-
"""模块拆分防回归测试。

1.0 把三个巨石文件按职责拆分，本测试守护拆分后的兼容性与一致性：

  · agents.py         → agents_base / agents_analysts / agents_researchers / agents_decision
  · daily_stock_pick  → runtime_env / stock_scoring / pool_manager / industry_context / lark_notify
  · report_generator  → report_styles / report_markdown

重点：拆分不得改变对外 API，不得让生成产物发生字节级变化。
"""
import glob
import os

import pytest


# ---------------------------------------------------------------------------
# agents.py 门面兼容性
# ---------------------------------------------------------------------------

def test_agents_facade_reexports_public_api():
    """agents.py 必须仍能导出历史公开符号（`from agents import X` 不失效）。"""
    import agents

    expected = [
        "AnalysisResult", "BaseAgent", "DATA_RULES", "pack_data",
        "FundamentalAnalyst", "SentimentAnalyst", "NewsAnalyst", "TechnicalAnalyst",
        "BullishResearcher", "BearishResearcher", "Trader", "RiskManager",
        "AGENT_REGISTRY", "create_agent",
        "get_analyst_team", "get_research_team", "get_decision_team",
    ]
    missing = [n for n in expected if not hasattr(agents, n)]
    assert missing == [], f"agents.py 门面缺失符号: {missing}"


def test_agents_facade_objects_are_same_as_submodules():
    """门面导出的类应与子模块中的定义是同一对象（不是副本）。"""
    import agents
    import agents_analysts
    import agents_decision
    import agents_researchers

    assert agents.FundamentalAnalyst is agents_analysts.FundamentalAnalyst
    assert agents.TechnicalAnalyst is agents_analysts.TechnicalAnalyst
    assert agents.BullishResearcher is agents_researchers.BullishResearcher
    assert agents.Trader is agents_decision.Trader
    assert agents.RiskManager is agents_decision.RiskManager


def test_agents_registry_covers_all_eight_roles():
    """8 个角色应全部可经工厂创建，且名字唯一。"""
    from agents import AGENT_REGISTRY, create_agent

    assert len(AGENT_REGISTRY) == 8
    names = [create_agent(t).name for t in AGENT_REGISTRY]
    assert len(set(names)) == 8, f"角色名重复: {names}"
    with pytest.raises(ValueError):
        create_agent("不存在的角色")


def test_analyst_and_decision_prompts_contain_output_schema_block():
    """分析师与决策 Agent 的提示词应含 JSON 输出格式块（_json_block 生效）。"""
    from agents import create_agent

    for t in ["fundamental", "sentiment", "news", "technical", "trader", "risk"]:
        prompt = create_agent(t).generate_prompt("600519", "贵州茅台")
        assert "输出格式" in prompt, f"{t} 缺少输出格式块"
        assert "JSON" in prompt, f"{t} 未约束 JSON 输出"


def test_researcher_independent_variant_contains_output_schema():
    """研究员传入事实清单时进入「独立论证」模式，应含 JSON 输出块。"""
    from agents import BearishResearcher, BullishResearcher

    sheet = {
        "meta": {"code": "600519", "company": "贵州茅台", "data_source": "eastmoney"},
        "quote": {"price": 1500.0, "change_pct": 1.2, "code": "600519", "name": "贵州茅台"},
        "news": [], "kline": [],
    }
    for cls in (BullishResearcher, BearishResearcher):
        agent = cls()
        base = agent.generate_prompt("600519", "贵州茅台")
        assert "600519" in base and len(base) > 200, f"{cls.__name__} 基础提示词异常"
        indep = agent.generate_prompt("600519", "贵州茅台", fact_sheet=sheet)
        assert "输出格式" in indep, f"{cls.__name__} 独立论证变体缺少输出格式块"


def test_pack_data_injects_rules_and_fact_sheet():
    """传入数据包时，提示词应包含【数据包】与【铁律】两块。"""
    from agents import pack_data

    sheet = {
        "meta": {"code": "600519", "company": "贵州茅台", "data_source": "eastmoney"},
        "quote": {"price": 1500.0, "change_pct": 1.2, "code": "600519", "name": "贵州茅台"},
        "news": [], "kline": [],
    }
    block = pack_data(sheet)
    assert "【数据包】" in block
    assert "铁律" in block
    # 空数据包应降级为不注入
    assert pack_data({}) == ""


# ---------------------------------------------------------------------------
# daily_stock_pick 门面兼容性
# ---------------------------------------------------------------------------

def test_daily_stock_pick_facade_reexports():
    """daily_stock_pick 应仍导出路径常量与主要函数。"""
    import daily_stock_pick as dsp

    for name in ["WORK_DIR", "WATCHLIST_FILE", "STATE_DIR", "CANDIDATE_FILE",
                 "POOL_STATE_FILE", "REPORT_DIR", "LOG_FILE", "CONFIG_FILE"]:
        assert isinstance(getattr(dsp, name, None), str), f"缺常量 {name}"
    for fn in ["score_stock", "update_watchlist", "build_industry_context",
               "apply_industry_context", "add_records_to_base", "send_push",
               "run_deep_analysis", "save_tracking_records", "save_unified_report",
               "load_watchlist", "load_config", "log", "main"]:
        assert callable(getattr(dsp, fn, None)), f"缺函数 {fn}"


def test_runtime_env_has_no_project_dependency():
    """runtime_env 是拆分的公共底座，不得反向依赖项目内其他模块。"""
    from runtime import runtime_env as _runtime_env
    with open(_runtime_env.__file__, encoding="utf-8") as f:
        src = f.read()
    forbidden = ["data_fetcher", "stock_scoring", "pool_manager",
                 "industry_context", "notify.lark_notify", "daily_stock_pick"]
    hits = [m for m in forbidden if f"import {m}" in src or f"from {m}" in src]
    assert hits == [], f"runtime_env 不应依赖: {hits}"


def test_scoring_has_no_io_side_effects():
    """stock_scoring 是纯打分模块，不应包含落盘/推送调用。"""
    with open("stock_scoring.py", encoding="utf-8") as f:
        src = f.read()
    for bad in ["open(", "subprocess", "lark-cli", "json.dump"]:
        assert bad not in src, f"stock_scoring 不应出现 {bad}"


# ---------------------------------------------------------------------------
# report_generator 拆分
# ---------------------------------------------------------------------------

def test_report_styles_is_the_single_css_source():
    """CSS 必须只存在于 report_styles，避免两处维护。"""
    from reporting import report_styles

    css = report_styles.REPORT_CSS
    assert css.startswith("<style>")
    assert css.rstrip().endswith("</style>")
    assert len(css) > 10_000, "CSS 长度异常，可能抽取不完整"

    from reporting import report_generator as _report_generator
    with open(_report_generator.__file__, encoding="utf-8") as f:
        gen_src = f.read()
    assert ":root {" not in gen_src, "report_generator 仍内嵌 CSS"


def test_markdown_to_html_is_pure_function():
    """markdown_to_html 不依赖实例状态，可直接调用。"""
    from reporting.report_markdown import markdown_to_html

    assert markdown_to_html("") == ""
    assert "<strong>" in markdown_to_html("**加粗**")
    assert "<li>" in markdown_to_html("- 项一")
    assert "&amp;" in markdown_to_html("A & B")


def test_report_generator_delegates_to_extracted_modules():
    """HTMLReportGenerator 应委托给抽出的模块，而非自行实现。"""
    from reporting import report_styles
    from orchestrator import create_workflow
    from reporting.report_generator import HTMLReportGenerator

    gen = HTMLReportGenerator(create_workflow("600519", "贵州茅台").session)
    assert gen._generate_styles() == report_styles.REPORT_CSS

    from reporting.report_markdown import markdown_to_html
    assert gen._markdown_to_html("**x**") == markdown_to_html("**x**")


# ---------------------------------------------------------------------------
# 拆分过程中发现并修复的缺陷（回归守卫）
# ---------------------------------------------------------------------------

def test_save_report_accepts_bare_filename(tmp_path, monkeypatch):
    """save() 传入裸文件名（无目录部分）时不应崩溃。

    原实现 `os.makedirs(os.path.dirname(filepath))` 在 dirname 为空串时
    抛 FileNotFoundError —— 模块自带的 __main__ 演示就会触发该问题。
    """
    from orchestrator import create_workflow
    from reporting.report_generator import HTMLReportGenerator

    monkeypatch.chdir(tmp_path)
    gen = HTMLReportGenerator(create_workflow("600519", "贵州茅台").session)
    out = gen.save("bare_report.html")          # 无目录部分
    assert os.path.exists(out)
    assert os.path.getsize(out) > 0


def test_save_session_accepts_bare_filename(tmp_path, monkeypatch):
    """save_session() 同样应支持裸文件名。"""
    import json as _json

    from orchestrator import create_workflow

    monkeypatch.chdir(tmp_path)
    orch = create_workflow("600519", "贵州茅台")
    out = orch.save_session("bare_session.json")
    assert os.path.exists(out)
    with open(out, encoding="utf-8") as f:
        assert _json.load(f)["stock_code"] == "600519"


def test_save_creates_nested_directories(tmp_path, monkeypatch):
    """含多级目录的路径应被自动创建（原有行为不得回退）。"""
    from orchestrator import create_workflow
    from reporting.report_generator import HTMLReportGenerator

    monkeypatch.chdir(tmp_path)
    gen = HTMLReportGenerator(create_workflow("600519", "贵州茅台").session)
    out = gen.save(os.path.join("a", "b", "c", "r.html"))
    assert os.path.exists(out)


def test_analysis_session_reports_are_not_shared():
    """analyst_reports 必须每个实例独立（default_factory，不能是可变默认值）。"""
    from agents import AnalysisResult
    from orchestrator import AnalysisSession

    s1 = AnalysisSession("600519", "贵州茅台")
    s2 = AnalysisSession("600519", "贵州茅台")
    assert s1.analyst_reports == {}
    s1.analyst_reports["analyst_fundamental"] = AnalysisResult(
        "基本面分析师", "📊", "fundamental", "内容")
    assert s2.analyst_reports == {}, "实例间共享了同一个 dict"


def test_analysis_session_autofills_identity_fields():
    """session_id / created_at 未提供时应自动生成。"""
    from orchestrator import AnalysisSession

    s = AnalysisSession("600519", "贵州茅台")
    assert s.session_id and "600519" in s.session_id
    assert s.created_at


def test_orchestrator_prompt_per_stage():
    """已推进到 Agent 阶段时能取到提示词；非 Agent 阶段返回 None。"""
    from orchestrator import create_workflow

    orch = create_workflow("600519", "贵州茅台")

    orch.session.current_stage = "analyst_fundamental"
    prompt = orch.get_next_prompt()
    assert prompt and "600519" in prompt

    # 非 Agent 阶段（如 waiting_input / completed）无提示词
    orch.session.current_stage = "waiting_input"
    assert orch.get_next_prompt() is None
    orch.session.current_stage = "completed"
    assert orch.get_next_prompt() is None


def test_all_eight_stages_produce_prompt():
    """8 个 Agent 阶段都应有可用提示词（含依赖前序报告的研究/决策阶段）。"""
    from agents import AnalysisResult
    from orchestrator import create_workflow

    orch = create_workflow("600519", "贵州茅台")
    orch.session.analyst_reports["analyst_fundamental"] = AnalysisResult(
        "基本面分析师", "📊", "fundamental", "基本面内容")
    orch.session.bullish_report = AnalysisResult("看多研究员", "🐂", "bullish", "看多内容")
    orch.session.bearish_report = AnalysisResult("看空研究员", "🐻", "bearish", "看空内容")
    orch.session.trade_proposal = AnalysisResult("交易员", "🧑‍💼", "trader", "交易内容")

    for stage in ["analyst_fundamental", "analyst_sentiment", "analyst_news",
                  "analyst_technical", "research_bullish", "research_bearish",
                  "decision_trade", "decision_risk"]:
        orch.session.current_stage = stage
        prompt = orch.get_next_prompt()
        assert prompt and "600519" in prompt, f"{stage} 未产出提示词"


# ---------------------------------------------------------------------------
# 仓库卫生
# ---------------------------------------------------------------------------

def test_line_endings_are_lf():
    """所有文本文件必须是 LF 行尾。

    背景：在 Windows 上用 Python 文本模式写文件会把 \\n 转成 \\r\\n，
    导致仓库出现混合行尾、产生大量无意义 diff。本测试守卫该问题。

    **CSV 的范围限定（2026-10-18 补）**：只对**输入/规范层**（`data/`、
    `reports/external_*`）要求 LF。`reports/` 下其余 csv 是日常流程产物，
    由 Windows `csv` 模块默认写成 CRLF 且已被 `.gitignore` 忽略；
    若一并纳入，守卫会在每次日常运行后恒红 —— 那等于把「规范」变成噪声。
    见 `tests/test_pit_snapshot_store.py:236` 对「规范层必须 LF」的同一口径。
    """
    exts = (".py", ".md", ".json", ".txt", ".yml", ".yaml", ".ini", ".toml")
    csv_lf_roots = ("data/", "reports/external_")
    offenders = []
    for path in glob.glob("**/*", recursive=True):
        if not os.path.isfile(path):
            continue
        norm = path.replace("\\", "/")
        is_text = norm.endswith(exts) or os.path.basename(norm) in (".gitignore", ".env.example")
        is_csv_scope = norm.endswith(".csv") and norm.startswith(csv_lf_roots)
        if not (is_text or is_csv_scope):
            continue
        with open(path, "rb") as f:
            raw = f.read()
        if b"\r\n" in raw:
            offenders.append(norm)
    assert offenders == [], f"以下文件含 CRLF 行尾: {offenders[:10]}"


def test_split_modules_are_importable_standalone():
    """拆分出的模块应可独立导入（不依赖导入顺序）。"""
    import importlib

    for mod in ["agents_base", "agents_analysts", "agents_researchers",
                "agents_decision", "runtime.runtime_env", "stock_scoring",
                "pool_manager", "industry_context", "notify.lark_notify",
                "reporting.report_styles", "reporting.report_markdown"]:
        importlib.import_module(mod)
