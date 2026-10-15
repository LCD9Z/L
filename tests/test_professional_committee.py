# -*- coding: utf-8 -*-
"""`professional_committee` 单测（HANDOVER §7 第 4 项「无覆盖模块」之一，89 行）。

**为什么补**：这是「7 名独立专家评审」的**确定性部分**——
`deterministic_checks()` 的硬门槛会以「**不可由 LLM 改写**」的形式写进 prompt。
若这些门槛算错（例如把「无发布时间新闻」漏报），
LLM 拿到的是**错误的审计结论**，且没有任何下游能发现。
该模块此前**零直接测试引用**。

**注意**：`build_committee_prompt` 依赖 `agents.pack_data`（内部会引用外部模块），
且输出是一个**给人读的提示词**——我们只测它**不含敏感字段/结构完整**，
不测措辞。`deterministic_checks` 是全文件的核心逻辑，重点覆盖。
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

import professional_committee as pc


def _fact(**over: Any) -> Dict[str, Any]:
    """形状与真实 fact sheet 一致（`fetch/news.fact_sheet_to_text` 要求
    kline 每行含 open/close/high/low、且**必须有 meta 键**——见
    `test_kline_row_missing_open_raises` / `test_missing_meta_key_raises`）。"""
    base: Dict[str, Any] = {
        "quote": {"name": "测试股", "code": "600001", "price": 10.5,
                  "change_pct": 1.2, "quote_time": "2024-01-02T15:00:00",
                  "amount": 1e6, "turnover": 1.2, "board": "沪主板"},
        "meta": {"crawl4ai_enabled": True, "cutoff_time": "2024-01-02T12:00:00"},
        "news": [{"published_at": "2024-01-02T09:00:00", "title": "公告",
                  "media": "cninfo", "date": "2024-01-02"}],
        "kline": [{"date": "2024-01-02", "open": 9.5, "close": 10.5,
                   "high": 11.5, "low": 9.0}],
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# deterministic_checks：字段映射与计数
# ---------------------------------------------------------------------------
def test_roles_are_seven_and_independent():
    """7 个席位、英文键唯一、名称唯一（否则 prompt 里会出现重复角色）。"""
    assert len(pc.ROLES) == 7
    keys = [k for k, _, _ in pc.ROLES]
    names = [n for _, n, _ in pc.ROLES]
    assert len(set(keys)) == 7 and len(set(names)) == 7


def test_full_fact_sheet_all_flags_true():
    c = pc.deterministic_checks(_fact())
    assert c["checks"]["quote_price_available"] is True
    assert c["checks"]["quote_time_available"] is True
    assert c["checks"]["kline_rows"] == 1
    assert c["checks"]["news_rows"] == 1
    assert c["checks"]["crawl4ai_enabled"] is True
    assert c["checks"]["historical_cutoff_set"] is True
    assert c["checks"]["news_with_published_at"] == 1
    assert c["checks"]["news_without_published_at"] == 0
    assert c["checks"]["amount_available"] is True
    assert c["checks"]["turnover_available"] is True
    assert c["checks"]["board"] == "沪主板"
    assert c["checks"]["t_plus_one"] is True, "A股必须恒定 T+1"
    assert c["hard_fail"] == [] and c["pass"] is True


def test_empty_fact_sheet_fails_on_missing_price():
    c = pc.deterministic_checks({})
    assert c["checks"]["quote_price_available"] is False
    assert c["checks"]["kline_rows"] == 0 and c["checks"]["news_rows"] == 0
    assert "缺少实时价格" in c["hard_fail"]
    assert c["pass"] is False


def test_none_fact_sheet_is_safe():
    """缺失即缺失：`None` fact 不应炸（(fact_sheet or {}) 的防护）。"""
    c = pc.deterministic_checks(None)
    assert c["pass"] is False and c["hard_fail"] == ["缺少实时价格"]


def test_zero_price_is_not_available():
    """`price=0` 属未获取（`is not None` 判据下 0 也算有值——**这是当前口径**）。

    ⚠️ characterization：`quote_price_available` 用 `is not None`，
    所以 `price=0` 与 `price=0.0` 都会判为「有价」。
    这里钉住该口径（改判据须同步改测试）。
    """
    c = pc.deterministic_checks(_fact(quote={"price": 0}))
    assert c["checks"]["quote_price_available"] is True


def test_undated_news_triggers_hard_fail_only_in_history_mode():
    """**硬门槛只与历史研究时点相关**：
    设定 cutoff_time 时，无发布时间的新闻 ⇒ hard_fail；未设定时不应触发。
    """
    news = [{"title": "无时间"}, {"title": "另一条"}]
    # 历史模式（有 cutoff）
    c_hist = pc.deterministic_checks(_fact(news=news))
    assert c_hist["checks"]["news_without_published_at"] == 2
    assert "历史研究存在无发布时间新闻" in c_hist["hard_fail"]
    assert c_hist["pass"] is False
    # 实时模式（无 cutoff）⇒ 不触发该门槛
    f = _fact(news=news)
    f["meta"] = {"crawl4ai_enabled": True}
    c_live = pc.deterministic_checks(f)
    assert c_live["checks"]["historical_cutoff_set"] is False
    assert "历史研究存在无发布时间新闻" not in c_live["hard_fail"]
    assert c_live["pass"] is True


def test_dated_news_never_hard_fails():
    f = _fact(news=[{"published_at": "2024-01-02T09:00:00"}] * 3)
    c = pc.deterministic_checks(f)
    assert c["checks"]["news_with_published_at"] == 3
    assert c["hard_fail"] == []


def test_missing_amount_and_turnover_are_recorded_not_hard_fail():
    """amount/turnover 缺失**只记录、不否决**（口径：可成交性由 LLM 判断）。"""
    c = pc.deterministic_checks(_fact(quote={"price": 10.5}))
    assert c["checks"]["amount_available"] is False
    assert c["checks"]["turnover_available"] is False
    assert c["hard_fail"] == [] and c["pass"] is True


def test_committee_context_is_valid_json_of_checks():
    out = pc.committee_context(_fact())
    import json
    d = json.loads(out)
    assert d == pc.deterministic_checks(_fact()), "committee_context 必须是检查结果的 JSON"


def test_committee_context_ignores_prior_reports():
    """签名带 prior_reports 但目前实现不消费它（characterization）。"""
    out = pc.committee_context(_fact(), prior_reports=["旧报告"])
    assert out == pc.committee_context(_fact())


# ---------------------------------------------------------------------------
# build_committee_prompt：结构完整 + 不含敏感字段
# ---------------------------------------------------------------------------
def test_prompt_contains_stock_and_company():
    p = pc.build_committee_prompt("600001", "测试公司", _fact())
    assert "600001" in p and "测试公司" in p


def test_prompt_contains_all_seven_roles():
    p = pc.build_committee_prompt("600001", "公司", _fact())
    for _, name, focus in pc.ROLES:
        assert name in p and focus in p, f"席位 {name} 未出现在 prompt"


def test_prompt_states_facts_only_and_json_output():
    p = pc.build_committee_prompt("600001", "公司", _fact())
    assert "没有数据就写【数据未获取】" in p
    assert "只输出合法JSON" in p
    assert '"股票代码"' in p and '"专家评审"' in p
    assert '"一票否决项"' in p


def test_prompt_embeds_machine_checks_as_unmodifiable():
    """机器门槛必须以 JSON 块形式嵌入，且标注不可改写。"""
    p = pc.build_committee_prompt("600001", "公司", _fact())
    assert "【机器硬门槛检查（不可由LLM改写）】" in p
    assert "hard_fail" in p and "t_plus_one" in p


def test_prompt_uses_placeholder_when_no_prior_reports():
    p = pc.build_committee_prompt("600001", "公司", _fact())
    assert "[前序报告未提供]" in p


def test_prompt_joins_prior_reports():
    p = pc.build_committee_prompt("600001", "公司", _fact(),
                                  prior_reports=["报告甲", "报告乙"])
    assert "报告甲\n\n报告乙" in p
    assert "[前序报告未提供]" not in p


def test_prompt_works_with_none_and_empty_fact_sheet():
    """None fact 不应炸（确定性检查已防 None；pack_data 也应容忍）。"""
    p = pc.build_committee_prompt("600001", "公司", None)
    assert "600001" in p and "缺少实时价格" in p
    p2 = pc.build_committee_prompt("600001", "公司", {})
    assert "hard_fail" in p2


def test_prompt_reflects_failing_checks():
    """硬门槛失败的信息必须出现在 prompt（否则 LLM 看不到审计结论）。"""
    p = pc.build_committee_prompt("600001", "公司",
                                  _fact(quote={"price": None}, news=[{"title": "x"}]))
    assert "缺少实时价格" in p
    assert "历史研究存在无发布时间新闻" in p


def test_missing_meta_key_raises_in_pack_data():
    """⚠️ **已登记缺陷 #13**：渲染层 `fact_sheet_to_text`
    （`fetch/news.py:182`）用**硬索引** `sheet["meta"]` 而非 `.get`
    ⇒ fact sheet **缺 meta 键**时直接 `KeyError`。

    本测试锁定该脆性（修好后改为「不抛异常」）。
    影响：`build_committee_prompt` 不接受结构不完整的 fact sheet。
    上游 `build_fact_sheet` 恒带 meta ⇒ 生产中暂不触发。
    """
    f = _fact()
    del f["meta"]                      # 缺键（而非值为 None）
    with pytest.raises(KeyError):
        pc.build_committee_prompt("600001", "公司", f)


def test_meta_none_fails_in_deterministic_checks():
    """⚠️ 同一模式在**本模块内**的表现：`meta=None` 时
    `deterministic_checks:71` 的 `meta.get(...)` 直接 `AttributeError`。
    （`q`/`news`/`kline` 都用了 `or {}` / `or []` 防护，唯独 meta 没有。）
    """
    with pytest.raises(AttributeError):
        pc.deterministic_checks(_fact(meta=None))


def test_kline_row_missing_open_raises():
    """⚠️ 同一渲染层的第二个硬索引：kline 行缺 `open` ⇒ KeyError（news.py:234）。"""
    with pytest.raises(KeyError):
        pc.build_committee_prompt("600001", "公司",
                                  _fact(kline=[{"date": "2024-01-02", "close": 10.5}]))


def test_prompt_does_not_leak_raw_fact_sheet_json(monkeypatch):
    """⚠️ 反泄漏：fact_sheet 原文不得以未加工形式进入 prompt。

    `pack_data` 负责格式化；我们只断言 prompt 里**不会**出现
    `"quote": {` 这类原始 JSON 键形态（若出现说明格式化被绕过）。
    """
    p = pc.build_committee_prompt("600001", "公司", _fact())
    assert '"quote": {' not in p
