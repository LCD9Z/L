# -*- coding: utf-8 -*-
"""`track/costs` 单测（HANDOVER §7 第 4 项「无覆盖模块」之一，81 行）。

**为什么补**：这是**交易成本模型**——与本次跨线重算（印花税分段口径）
**同源**的逻辑。成本算错会让任何策略「看起来不赚钱」，且没有任何
下游能发现（收益数字本身看起来完全正常）。此前零直接测试引用。

**本文件最有价值的产出**：`_stamp_rate` 用**字符串比较**判日期，
对 `YYYYMMDD`（无连字符）格式**恒判为现行税率**（缺陷 #15）。
"""
from __future__ import annotations

import pytest

from track.costs import TrackingCosts, net_return_pct


# ---------------------------------------------------------------------------
# _stamp_rate：印花税分段
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("as_of,expect", [
    ("2022-01-03", 0.001),      # 生效日前 → 旧税率
    ("2023-08-27", 0.001),
    ("2023-08-28", 0.0005),     # 生效日当天 → 现行（>=）
    ("2024-01-02", 0.0005),
    (None, 0.0005),             # 未提供 → 按现行
    ("", 0.0005),
])
def test_stamp_rate_dashed_format(as_of, expect):
    """`YYYY-MM-DD` 格式下分段正确（这是默认路径，`_today()` 产此格式）。"""
    assert TrackingCosts()._stamp_rate(as_of) == expect


@pytest.mark.parametrize("as_of", ["20230103", "20230827"])
def test_stamp_rate_undashed_format_is_wrong(as_of):
    """⚠️ **已登记缺陷 #15**：`YYYYMMDD`（无连字符）被**恒判为现行税率**。

    根因：`str(as_of) >= "2023-08-28"` 是**字符串**比较。
    `"20230103"` 与 `"2023-08-28"` 逐字符比，第 5 位 `'0'`(0x30) > `'-'`(0x2D)
    ⇒ 恒为 True ⇒ 走现行税率分支。

    **影响方向明确**：跨生效日前的记录若以该格式传入，印花税按 0.05%
    而非 0.1% ⇒ **成本低估 0.05%**（单边）。

    **当前影响面**：`track/store._today()` 产出 `YYYY-MM-DD`，默认路径
    **不触发**；但 `rec_date` 可由调用方传入（`track/stats.backfill_pending`
    原样 `as_of=r["rec_date"]`），若上游给 YYYYMMDD 即触发。

    本测试按 characterization **锁定当前（错误的）行为**；
    修好后须改为 `== 0.001`。
    """
    assert TrackingCosts()._stamp_rate(as_of) == 0.0005, "现状：无连字符格式被误判为现行税率"


def test_stamp_rate_change_date_empty_means_always_current():
    """`stamp_duty_change_date` 置空 ⇒ 恒按现行税率（关闭分段）。"""
    c = TrackingCosts(stamp_duty_change_date="")
    assert c._stamp_rate("2020-01-01") == 0.0005


# ---------------------------------------------------------------------------
# buy_cost / sell_proceeds
# ---------------------------------------------------------------------------
def test_buy_cost_includes_max_commission_and_transfer_fee():
    c = TrackingCosts(position_notional=100_000.0)
    # 10 万：佣金 30 > 最低 5 ⇒ 用 30；过户费 1
    assert c.buy_cost(100_000.0) == pytest.approx(100_000 + 30 + 1)


def test_buy_cost_uses_min_commission_on_small_notional():
    c = TrackingCosts()
    # 1000 元：佣金 0.3 < 最低 5 ⇒ 用 5；过户费 0.01
    assert c.buy_cost(1000.0) == pytest.approx(1000 + 5 + 0.01)


def test_sell_proceeds_deducts_commission_stamp_transfer():
    c = TrackingCosts()
    # 10 万卖出（现行税率 0.0005）：佣金 30 + 印花税 50 + 过户费 1
    got = c.sell_proceeds(100_000.0, as_of="2024-01-02")
    assert got == pytest.approx(100_000 - 30 - 50 - 1)


def test_sell_proceeds_uses_old_stamp_rate_before_cut():
    c = TrackingCosts()
    got = c.sell_proceeds(100_000.0, as_of="2023-01-03")
    assert got == pytest.approx(100_000 - 30 - 100 - 1)   # 印花税 100（1‰）


# ---------------------------------------------------------------------------
# round_trip_cost_pct
# ---------------------------------------------------------------------------
def test_round_trip_cost_pct_current_rate():
    c = TrackingCosts()
    # (30 + 30 + 50 + 2) / 100000 = 0.00112
    assert c.round_trip_cost_pct("2024-01-02") == pytest.approx(0.00112)


def test_round_trip_cost_pct_old_rate_is_higher():
    """旧税率下往返成本更高（1‰ vs 0.5‰）。"""
    c = TrackingCosts()
    old = c.round_trip_cost_pct("2023-01-03")
    new = c.round_trip_cost_pct("2024-01-02")
    assert old > new
    assert old == pytest.approx(0.00162)      # +50/100000


def test_round_trip_cost_pct_zero_notional():
    assert TrackingCosts(position_notional=0).round_trip_cost_pct() == 0.0


def test_round_trip_cost_pct_negative_notional():
    assert TrackingCosts(position_notional=-1).round_trip_cost_pct() == 0.0


# ---------------------------------------------------------------------------
# net_return_pct
# ---------------------------------------------------------------------------
def test_gross_return_without_costs():
    assert net_return_pct(100.0, 110.0) == 10.0
    assert net_return_pct(100.0, 90.0) == -10.0


def test_gross_return_zero_price_returns_none():
    """⚠️ `rec_price` 为 0（falsy）⇒ 返回 None（缺失即缺失）。"""
    assert net_return_pct(0, 110.0) is None
    assert net_return_pct(None, 110.0) is None


def test_gross_return_missing_close_returns_none():
    assert net_return_pct(100.0, None) is None


def test_net_return_is_lower_than_gross():
    """净收益必须低于毛收益（成本与滑点都是扣项）。"""
    c = TrackingCosts()
    assert net_return_pct(100.0, 110.0, c, as_of="2024-01-02") < 10.0


def test_net_return_applies_two_sided_slippage():
    """滑点**双向**：买入价上浮、卖出价下浮。"""
    c = TrackingCosts(slippage_rate=0.01, commission_rate=0.0,
                      min_commission=0.0, stamp_duty_sell=0.0,
                      transfer_fee_rate=0.0)
    # 买 101、卖 108.9 ⇒ (108.9-101)/101 = 7.82%
    assert net_return_pct(100.0, 110.0, c) == pytest.approx(7.82, abs=0.01)


def test_net_return_deducts_round_trip_cost():
    c = TrackingCosts(slippage_rate=0.0)
    got = net_return_pct(100.0, 110.0, c, as_of="2024-01-02")
    # 毛 10% − 往返成本 0.112% = 9.888%
    assert got == pytest.approx(9.89, abs=0.01)


def test_net_return_old_rate_lower_than_new():
    """同一笔交易：生效日前的净收益**更低**（旧税率更贵）。"""
    c = TrackingCosts()
    before = net_return_pct(100.0, 110.0, c, as_of="2023-01-03")
    after = net_return_pct(100.0, 110.0, c, as_of="2024-01-02")
    assert before < after
    assert after - before == pytest.approx(0.05, abs=0.01)   # 印花税差 0.05%


def test_net_return_negative_case():
    c = TrackingCosts()
    got = net_return_pct(100.0, 90.0, c, as_of="2024-01-02")
    assert got < -10.0, "亏损时成本应使净收益更差"


def test_net_return_rounds_to_two_decimals():
    got = net_return_pct(100.0, 103.0)
    assert got == round(got, 2)
