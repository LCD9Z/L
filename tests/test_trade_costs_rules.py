# -*- coding: utf-8 -*-
"""A股交易成本规则守卫测试。

规则口径与出处（改动前先核对，勿凭记忆调整数值）：
- 印花税：财政部/税务总局公告，自 2023-08-28 起减半征收，卖出单边 0.5‰；
  此前为卖出单边 1‰ → 回测跨越生效日必须按交易日分段计费。
- 过户费：中国结算公告，自 2022-04-29 起沪深两市 A股统一按成交金额 0.01‰
  双向收取（此前沪深 0.02‰ / 北交所 0.025‰）。
- 佣金：双向收取，单笔最低 5 元保底。
"""
import pytest

from backtest_engine import (
    Costs,
    STAMP_DUTY_CHANGE_DATE,
    STAMP_DUTY_SELL_BEFORE,
    TRANSFER_FEE_RATE,
    _stamp_rate,
    _trade_cost,
)


def test_cost_defaults_match_current_rules():
    c = Costs()
    assert c.stamp_duty_sell == pytest.approx(0.0005)   # 现行 0.5‰
    assert c.stamp_duty_sell_before == pytest.approx(0.001)  # 旧税率 1‰
    assert c.stamp_duty_change_date == "2023-08-28"
    assert c.transfer_fee_rate == pytest.approx(0.00001)     # 0.01‰
    assert c.commission_rate == pytest.approx(0.0003)
    assert c.min_commission == pytest.approx(5.0)
    # 常量与字段必须一致，防止只改一处
    assert STAMP_DUTY_CHANGE_DATE == "2023-08-28"
    assert pytest.approx(0.001) == STAMP_DUTY_SELL_BEFORE
    assert pytest.approx(0.00001) == TRANSFER_FEE_RATE


def test_stamp_rate_is_piecewise_by_date():
    c = Costs()
    assert _stamp_rate(c, "2023-08-27") == pytest.approx(0.001)    # 生效日前 → 旧税率
    assert _stamp_rate(c, "2023-08-28") == pytest.approx(0.0005)   # 生效日起 → 现行
    assert _stamp_rate(c, "2024-01-02") == pytest.approx(0.0005)
    assert _stamp_rate(c, None) == pytest.approx(0.0005)           # 未传日期 → 现行（兼容）


def test_trade_cost_buy_has_no_stamp_duty():
    c = Costs()
    # 买入：佣金 30（10万×0.03%）+ 过户费 1（10万×0.01‰），无印花税
    assert _trade_cost(100_000.0, "buy", c, "2024-01-02") == pytest.approx(31.0)


def test_trade_cost_sell_includes_stamp_and_transfer():
    c = Costs()
    # 卖出：佣金 30 + 印花税 50（现行 0.5‰）+ 过户费 1
    assert _trade_cost(100_000.0, "sell", c, "2024-01-02") == pytest.approx(81.0)
    # 生效日前卖出：印花税 100（旧税率 1‰）
    assert _trade_cost(100_000.0, "sell", c, "2023-07-03") == pytest.approx(131.0)


def test_min_commission_floor_applies():
    c = Costs()
    # 3000 元小额：佣金 max(5, 0.9)=5 + 过户费 0.03
    assert _trade_cost(3_000.0, "buy", c, "2024-01-02") == pytest.approx(5.03)


def test_transfer_fee_can_be_disabled_for_legacy_comparison():
    c = Costs(transfer_fee_rate=0.0, stamp_duty_change_date="0001-01-01")
    # 还原旧成本模型：无过户费、全程 0.5‰ 印花税（生效日设为最早，任何日期都用现行税率）
    assert _trade_cost(100_000.0, "sell", c, "2023-07-03") == pytest.approx(80.0)


@pytest.mark.parametrize("trade_date,expected", [
    ("20230825", 0.001),    # 无横杠（通达信原生 .day 形态）——修复前会触发的形态
    ("2023-08-25", 0.001),  # 带横杠（certified CSV 形态，现有全部数据通道）
    ("20230829", 0.0005),
    ("2023-08-29", 0.0005),
    (None, 0.0005),         # 未传日期 → 现行（缺陷 #16 曾长期走此分支）
    ("", 0.0005),
])
def test_stamp_rate_invariant_to_date_format(trade_date, expected):
    """日期形态无关性（2026-10-17 裁定 D）。

    带横杠与不带横杠必须同判；`_norm_date` 修复后两形态一致。
    无横杠分支保留为**形态守卫**：防未来原生 `.day` 直接接入成本链。
    """
    assert _stamp_rate(Costs(), trade_date) == pytest.approx(expected)
