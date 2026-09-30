# -*- coding: utf-8 -*-
"""守卫：单季口径派生（`pit/pit_quarterly.py`）。

## 背景

2026-09-30 专家圆桌审查中，**财报研究员**指出「累计口径会把拐点往后拖 2-3 个季度」：

> Q1 净利同比 +50%（基数低）→ Q3 **累计**同比只剩 +8%（因 Q2/Q3 单季在恶化）。
> 系统在 Q3 看到的是"还在增长"。

数据源 `fundamentals.jsonl` 的 `net_profit`/`revenue`/`eps` 全是**年初至今累计**，
故必须差分出单季。本文件锁住差分规则与**诚实原则**（负基数不硬算）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pit.pit_quarterly import derive_quarterly  # noqa: E402


def _rec(code, period, net_profit, revenue=1000.0, eps=None):
    r = {"code": code, "report_period": period, "net_profit": net_profit,
         "revenue": revenue}
    if eps is not None:
        r["eps"] = eps
    return r


def _by_period(rows, code="000001"):
    return {r["report_period"]: r for r in rows if r["code"] == code}


# ---------------------------------------------------------------------------
# 差分规则
# ---------------------------------------------------------------------------

def test_q1_single_equals_cumulative():
    """Q1 单季 = Q1 累计。"""
    rows = derive_quarterly([_rec("000001", "2024-03-31", 100.0)])
    assert _by_period(rows)["2024-03-31"]["net_profit_q"] == 100.0


def test_q2_single_is_h1_minus_q1():
    rows = derive_quarterly([_rec("000001", "2024-03-31", 100.0),
                             _rec("000001", "2024-06-30", 250.0)])
    assert _by_period(rows)["2024-06-30"]["net_profit_q"] == 150.0


def test_q3_single_is_q3_minus_h1():
    rows = derive_quarterly([_rec("000001", "2024-03-31", 100.0),
                             _rec("000001", "2024-06-30", 250.0),
                             _rec("000001", "2024-09-30", 300.0)])
    assert _by_period(rows)["2024-09-30"]["net_profit_q"] == 50.0


def test_q4_single_is_fy_minus_q3():
    rows = derive_quarterly([_rec("000001", "2024-03-31", 100.0),
                             _rec("000001", "2024-06-30", 250.0),
                             _rec("000001", "2024-09-30", 300.0),
                             _rec("000001", "2024-12-31", 400.0)])
    assert _by_period(rows)["2024-12-31"]["net_profit_q"] == 100.0


def test_quarter_index_is_correct():
    rows = derive_quarterly([_rec("000001", p, v) for p, v in
                             (("2024-03-31", 1.0), ("2024-06-30", 2.0),
                              ("2024-09-30", 3.0), ("2024-12-31", 4.0))])
    got = {r["report_period"]: r["quarter"] for r in rows}
    assert got == {"2024-03-31": 1, "2024-06-30": 2,
                   "2024-09-30": 3, "2024-12-31": 4}


# ---------------------------------------------------------------------------
# 同比 / 环比
# ---------------------------------------------------------------------------

def test_yoy_uses_same_quarter_last_year():
    """⚠️ 核心：同比必须比**去年同期单季**，不是累计。"""
    rows = derive_quarterly([
        _rec("000001", "2023-03-31", 100.0), _rec("000001", "2023-06-30", 200.0),
        _rec("000001", "2024-03-31", 200.0), _rec("000001", "2024-06-30", 250.0)])
    m = _by_period(rows)
    # 2024Q1 单季 200 vs 2023Q1 单季 100 → +100%
    assert m["2024-03-31"]["net_profit_q_yoy_pct"] == pytest.approx(100.0)
    # 2024Q2 单季 = 250−200 = 50；2023Q2 单季 = 200−100 = 100 → −50%
    assert m["2024-06-30"]["net_profit_q"] == 50.0
    assert m["2024-06-30"]["net_profit_q_yoy_pct"] == pytest.approx(-50.0)


def test_qoq_uses_previous_quarter():
    rows = derive_quarterly([
        _rec("000001", "2024-03-31", 100.0), _rec("000001", "2024-06-30", 250.0)])
    assert _by_period(rows)["2024-06-30"]["net_profit_q_qoq_pct"] == pytest.approx(50.0)


def test_cumulative_yoy_is_misleading_demo():
    """演示财报研究员的论点：累计同比掩盖单季恶化。

    Q1 单季 100→200（+100%）；Q2 单季 100→50（**−50%**）。
    但 H1 **累计** 200→250 = **+25%** —— 看起来还在增长。
    """
    rows = derive_quarterly([
        _rec("000001", "2023-03-31", 100.0), _rec("000001", "2023-06-30", 200.0),
        _rec("000001", "2024-03-31", 200.0), _rec("000001", "2024-06-30", 250.0)])
    m = _by_period(rows)
    assert m["2024-06-30"]["net_profit_q_yoy_pct"] == pytest.approx(-50.0), "单季同比揭示恶化"
    # 累计同比（数据源原字段）仍是正增长
    cum_yoy = (250.0 / 200.0 - 1) * 100
    assert cum_yoy == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# 诚实原则：负基数不硬算
# ---------------------------------------------------------------------------

def test_negative_base_yoy_is_none_and_flagged():
    """⚠️ 核心守卫：基数 ≤ 0 时不硬算增速（否则 −1 → +1 会算出 −200%）。"""
    rows = derive_quarterly([
        _rec("000001", "2023-03-31", -100.0),
        _rec("000001", "2024-03-31", 100.0)])
    r = _by_period(rows)["2024-03-31"]
    assert r["net_profit_q_yoy_pct"] is None, "负基数下增速必须为 None，不得硬算"
    assert any("negative_base" in f for f in r["flags"])


def test_negative_base_qoq_is_none_and_flagged():
    rows = derive_quarterly([
        _rec("000001", "2024-03-31", -50.0), _rec("000001", "2024-06-30", 30.0)])
    r = _by_period(rows)["2024-06-30"]
    assert r["net_profit_q_qoq_pct"] is None
    assert any("negative_base" in f for f in r["flags"])


def test_missing_previous_cumulative_yields_none():
    """缺上一累计期（如只有 H1 没有 Q1）→ 单季值为 None，不猜。"""
    rows = derive_quarterly([_rec("000001", "2024-06-30", 250.0)])
    r = _by_period(rows)["2024-06-30"]
    assert r["net_profit_q"] is None
    assert any("missing" in f for f in r["flags"])


def test_missing_last_year_quarter_flagged():
    rows = derive_quarterly([_rec("000001", "2024-03-31", 100.0)])
    r = _by_period(rows)["2024-03-31"]
    assert r["net_profit_q_yoy_pct"] is None
    assert "missing_last_year_quarter" in r["flags"]


# ---------------------------------------------------------------------------
# 稳健性
# ---------------------------------------------------------------------------

def test_invalid_period_is_skipped():
    rows = derive_quarterly([_rec("000001", "2024-05-15", 1.0),
                             _rec("000001", "bad", 2.0)])
    assert rows == []


def test_codes_are_independent():
    rows = derive_quarterly([
        _rec("000001", "2024-03-31", 100.0), _rec("000001", "2024-06-30", 250.0),
        _rec("600000", "2024-03-31", 10.0), _rec("600000", "2024-06-30", 30.0)])
    a = {r["report_period"]: r for r in rows if r["code"] == "000001"}
    b = {r["report_period"]: r for r in rows if r["code"] == "600000"}
    assert a["2024-06-30"]["net_profit_q"] == 150.0
    assert b["2024-06-30"]["net_profit_q"] == 20.0


def test_empty_input():
    assert derive_quarterly([]) == []


def test_original_fields_preserved():
    """派生不得丢掉原始字段（`industry`/`name` 等下游仍要用）。"""
    r = _rec("000001", "2024-03-31", 100.0)
    r["industry"] = "银行Ⅱ"
    r["name"] = "平安银行"
    out = derive_quarterly([r])[0]
    assert out["industry"] == "银行Ⅱ"
    assert out["name"] == "平安银行"
    assert out["report_period"] == "2024-03-31"


# ---------------------------------------------------------------------------
# ⚠️ 字段命名冲突守卫（本模块首版差点犯的错）
#
# 数据源本来就有 `net_profit_yoy_pct` / `revenue_yoy_pct` —— 那是**累计**同比。
# 若派生值也用 `<field>_yoy_pct` 这个名字，会**静默覆盖源字段**，
# 且事后无法区分两种口径（属"不报错的失效"，与本项目反复出现的缺陷同类）。
# ---------------------------------------------------------------------------

def test_source_cumulative_yoy_not_overwritten():
    """⚠️ 核心守卫：源字段（累计同比）必须原样保留，不得被派生值覆盖。"""
    r = _rec("000001", "2024-03-31", 100.0)
    r["net_profit_yoy_pct"] = 8.12          # 数据源给的**累计**同比
    out = derive_quarterly([r])[0]
    assert out["net_profit_yoy_pct"] == 8.12, "源字段被覆盖了 —— 两种口径会混淆"


def test_derived_and_source_yoy_coexist():
    """派生字段（单季同比）与源字段（累计同比）必须**同时存在且可区分**。"""
    r = _rec("000001", "2023-03-31", 100.0)
    r["net_profit_yoy_pct"] = 99.9
    r2 = _rec("000001", "2024-03-31", 200.0)
    r2["net_profit_yoy_pct"] = 8.12
    out = {x["report_period"]: x for x in derive_quarterly([r, r2])}
    m = out["2024-03-31"]
    assert m["net_profit_yoy_pct"] == 8.12, "源字段（累计）"
    assert m["net_profit_q_yoy_pct"] == pytest.approx(100.0), "派生字段（单季）"
