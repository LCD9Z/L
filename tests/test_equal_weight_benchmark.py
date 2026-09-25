# -*- coding: utf-8 -*-
"""等权全市场基准（`validation.benchmark.equal_weight_returns`）的行为守卫。

这些用例锁的是**口径**，不是实现细节——每一条都对应一个会静默改变结论的
口径选择：

* 停牌股按 0 收益持有（剔出分母会系统性高估基准）；
* 数据未覆盖的成员**不计入分母**（否则覆盖缺口被误读成"全市场不涨"）；
* 成分以 PIT 快照为准（用今天的池子回填历史 = 幸存者偏差）；
* 复牌跳空落在复牌日（丢弃会低估波动）。
"""
import pytest

from validation.benchmark import (
    daily_returns_by_code,
    equal_weight_diagnostics,
    equal_weight_returns,
)


def _bars(*pairs):
    return [{"date": d, "close": c} for d, c in pairs]


D1, D2, D3 = "2024-01-02", "2024-01-03", "2024-01-04"


# ---------------------------------------------------------------------------
# daily_returns_by_code
# ---------------------------------------------------------------------------

def test_first_bar_yields_no_return():
    ret = daily_returns_by_code({"A": _bars((D1, 100.0), (D2, 110.0))})
    assert ret["A"] == {D2: pytest.approx(0.1)}


def test_invalid_close_does_not_break_the_chain():
    """中间出现 close<=0 的脏行时，下一条有效记录仍相对**上一条有效收盘价**。"""
    ret = daily_returns_by_code({"A": _bars((D1, 100.0), (D2, 0.0), (D3, 120.0))})
    assert ret["A"] == {D3: pytest.approx(0.2)}


def test_missing_close_key_is_skipped():
    ret = daily_returns_by_code({"A": [{"date": D1, "close": 100.0},
                                       {"date": D2},
                                       {"date": D3, "close": 150.0}]})
    assert ret["A"] == {D3: pytest.approx(0.5)}


def test_empty_input_returns_empty_mapping():
    assert daily_returns_by_code({}) == {}
    assert daily_returns_by_code({"A": []}) == {"A": {}}


# ---------------------------------------------------------------------------
# equal_weight_returns —— 分母口径
# ---------------------------------------------------------------------------

def test_equal_weight_of_two_movers():
    data = {"A": _bars((D1, 100.0), (D2, 110.0)),
            "B": _bars((D1, 100.0), (D2, 90.0))}
    out = equal_weight_returns(data, {D2: ["A", "B"]}, dates=[D2])
    assert out[D2] == pytest.approx(0.0)


def test_suspended_member_is_held_at_zero_return():
    """B 停牌（当日无行情）→ 按 0 收益计入分母，而不是被剔除。"""
    data = {"A": _bars((D1, 100.0), (D2, 110.0)),
            "B": _bars((D1, 100.0))}
    out = equal_weight_returns(data, {D2: ["A", "B"]}, dates=[D2])
    assert out[D2] == pytest.approx(0.05)  # (0.10 + 0.00) / 2


def test_member_without_any_data_is_excluded_from_denominator():
    """C 完全不在 data 中（采样未覆盖）→ 不进分母，否则等于凭空加入一个 0 收益成分。"""
    data = {"A": _bars((D1, 100.0), (D2, 110.0)),
            "B": _bars((D1, 100.0))}
    out = equal_weight_returns(data, {D2: ["A", "B", "C"]}, dates=[D2])
    assert out[D2] == pytest.approx(0.05)  # 分母是 2 而非 3


def test_pit_membership_is_respected():
    """B 已不在当日 PIT 池中 → 其当日涨幅不得进入基准。"""
    data = {"A": _bars((D1, 100.0), (D2, 110.0)),
            "B": _bars((D1, 100.0), (D2, 150.0))}
    out = equal_weight_returns(data, {D2: ["A"]}, dates=[D2], min_members=1)
    assert out[D2] == pytest.approx(0.1)


def test_resume_day_gap_lands_on_the_resume_date():
    """停牌 1 日后复牌跳空 20%：停牌日收益 0，跳空落在复牌日。"""
    data = {"A": _bars((D1, 100.0), (D3, 120.0))}
    uni = {D1: ["A"], D2: ["A"], D3: ["A"]}
    out = equal_weight_returns(data, uni, dates=[D1, D2, D3], min_members=1)
    assert out[D1] == pytest.approx(0.0)   # 序列首日无前收 → 记 0 收益（不是缺失）
    assert out[D2] == pytest.approx(0.0)   # 停牌日按最后收盘价持有
    assert out[D3] == pytest.approx(0.2)   # 跳空落在复牌日


def test_date_is_omitted_when_below_min_members():
    """成员数不足时**不产出该日**（而不是补一个 0，那会被读成"全市场持平"）。"""
    data = {"A": _bars((D1, 100.0), (D2, 110.0))}
    assert equal_weight_returns(data, {D2: ["A"]}, dates=[D2], min_members=2) == {}
    assert D2 in equal_weight_returns(data, {D2: ["A"]}, dates=[D2], min_members=1)


def test_dates_without_universe_snapshot_are_skipped():
    data = {"A": _bars((D1, 100.0), (D2, 110.0))}
    assert equal_weight_returns(data, {}, dates=[D2]) == {}


def test_returns_are_not_cumulative():
    """返回的是**日收益**，不是累计曲线——调用方自行复合。"""
    data = {"A": _bars((D1, 100.0), (D2, 110.0), (D3, 121.0))}
    out = equal_weight_returns(data, {D2: ["A"], D3: ["A"]}, dates=[D2, D3], min_members=1)
    assert out[D2] == pytest.approx(0.1)
    assert out[D3] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# equal_weight_diagnostics
# ---------------------------------------------------------------------------

def test_diagnostics_reports_coverage_ratio():
    data = {"A": _bars((D1, 100.0), (D2, 110.0)),
            "B": _bars((D1, 100.0), (D2, 90.0))}
    diag = equal_weight_diagnostics(data, {D2: ["A", "B", "C", "D"]}, dates=[D2])
    assert diag["dates"] == 1
    assert diag["members_min"] == diag["members_max"] == 2
    assert diag["universe_coverage"] == pytest.approx(0.5)  # 2 / 4


def test_diagnostics_empty_when_nothing_aligns():
    diag = equal_weight_diagnostics({}, {}, dates=[D2])
    assert diag["dates"] == 0
    assert diag["universe_coverage"] is None
