# -*- coding: utf-8 -*-
"""交易成本模型（TrackingCosts）与净收益率换算。

由 tracking.py 拆分而来（对外 API 不变，实现下沉到 track/ 包）。
"""
from dataclasses import dataclass



@dataclass
class TrackingCosts:
    """回测交易成本参数，与 backtest_engine.Costs 口径一致。

    **计费基数**：backtest_engine / walk_forward / portfolio_backtest 均以
    「股数 × 价格」（100 股整手）作为名义金额计费。tracking 只记录单只推荐的
    收益率、没有组合资金概念，因此以 position_notional 作为基准仓位换算成本占比。

    这一点很关键：若直接用「每股价格」当名义金额，5 元最低佣金在高价股上会被
    放大到 0.33%（贵州茅台 1500 元时），而正确值约 0.03% —— 每笔收益率偏差
    可达 0.6 个百分点，足以让任何策略在统计上"看起来不赚钱"。
    """
    commission_rate: float = 0.0003   # 双边佣金费率
    min_commission: float = 5.0       # 单笔最低佣金（元）
    stamp_duty_sell: float = 0.0005   # 卖出印花税（现行：2023-08-28 起减半征收 0.5‰）
    slippage_rate: float = 0.0005     # 滑点
    transfer_fee_rate: float = 0.00001  # 过户费 0.01‰ 双向（中国结算 2022-04-29 起，沪深两市均收）
    stamp_duty_change_date: str = "2023-08-28"  # 印花税减半生效日
    stamp_duty_sell_before: float = 0.001       # 旧税率：卖出单边 1‰
    position_notional: float = 100_000.0   # 基准仓位（元），与 backtest_engine 默认初始资金一致

    def _stamp_rate(self, as_of=None) -> float:
        """卖出印花税率：as_of 早于生效日用旧税率；未提供日期按现行税率。"""
        if not as_of or not self.stamp_duty_change_date or str(as_of) >= self.stamp_duty_change_date:
            return self.stamp_duty_sell
        return self.stamp_duty_sell_before

    def buy_cost(self, notional):
        """买入总成本 = 名义金额 + 佣金 + 过户费"""
        return notional + max(self.min_commission, notional * self.commission_rate) + notional * self.transfer_fee_rate

    def sell_proceeds(self, notional, as_of=None):
        """卖出净收入 = 名义金额 - 佣金 - 印花税 - 过户费"""
        return (notional - max(self.min_commission, notional * self.commission_rate)
                - notional * self._stamp_rate(as_of) - notional * self.transfer_fee_rate)

    def round_trip_cost_pct(self, as_of=None) -> float:
        """一次完整买卖的成本占基准仓位的比例（小数，如 0.0011 表示 0.11%）。

        as_of：推荐日（YYYY-MM-DD）。回填跨 2023-08-28 前的记录应传入该日，
        以便印花税按当时税率（0.1%）计费。
        """
        n = self.position_notional
        if n <= 0:
            return 0.0
        buy_comm = max(self.min_commission, n * self.commission_rate)
        sell_comm = max(self.min_commission, n * self.commission_rate)
        stamp = n * self._stamp_rate(as_of)
        transfer = n * self.transfer_fee_rate * 2
        return (buy_comm + sell_comm + stamp + transfer) / n



def net_return_pct(rec_price, close_n, costs=None, as_of=None):
    """计算 N 日收益率（%）。

    costs=None  → **毛收益**：仅按收盘价计算，不含滑点与费用。
    costs=实例  → **净收益**：买入价加滑点、卖出价减滑点，再扣佣金、印花税与过户费。
    as_of：推荐日（YYYY-MM-DD），用于印花税分段计费；缺省按现行税率。

    返回 None 表示数据不足，不参与统计。
    """
    if not rec_price or close_n is None:
        return None
    if costs is None:
        return round((close_n / rec_price - 1) * 100, 2)
    buy_px = rec_price * (1 + costs.slippage_rate)
    sell_px = close_n * (1 - costs.slippage_rate)
    if not buy_px:
        return None
    gross = (sell_px - buy_px) / buy_px
    return round((gross - costs.round_trip_cost_pct(as_of=as_of)) * 100, 2)
