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
    stamp_duty_sell: float = 0.0005   # 卖出印花税
    slippage_rate: float = 0.0005     # 滑点
    position_notional: float = 100_000.0   # 基准仓位（元），与 backtest_engine 默认初始资金一致

    def buy_cost(self, notional):
        """买入总成本 = 名义金额 + 佣金"""
        return notional + max(self.min_commission, notional * self.commission_rate)

    def sell_proceeds(self, notional):
        """卖出净收入 = 名义金额 - 佣金 - 印花税"""
        return notional - max(self.min_commission, notional * self.commission_rate) - notional * self.stamp_duty_sell

    def round_trip_cost_pct(self) -> float:
        """一次完整买卖的成本占基准仓位的比例（小数，如 0.0011 表示 0.11%）。"""
        n = self.position_notional
        if n <= 0:
            return 0.0
        buy_comm = max(self.min_commission, n * self.commission_rate)
        sell_comm = max(self.min_commission, n * self.commission_rate)
        stamp = n * self.stamp_duty_sell
        return (buy_comm + sell_comm + stamp) / n



def net_return_pct(rec_price, close_n, costs=None):
    """计算 N 日收益率（%）。

    costs=None  → **毛收益**：仅按收盘价计算，不含滑点与费用。
    costs=实例  → **净收益**：买入价加滑点、卖出价减滑点，再扣佣金与印花税。

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
    return round((gross - costs.round_trip_cost_pct()) * 100, 2)
