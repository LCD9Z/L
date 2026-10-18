# -*- coding: utf-8 -*-
"""A股交易成本规则的**权威口径**（单一事实来源）。

## 为什么有这个模块

同一套成本逻辑曾有**两份独立实现**，且状态不一致：

| 实现 | 日期比较 | 状态 |
|---|---|---|
| `backtest_engine._stamp_rate` | `_norm_date()` 归一化后比较 | 2026-10-13 已修 |
| `track/costs.TrackingCosts._stamp_rate` | `str(as_of) >= "2023-08-28"` 逐字符 | 缺陷 #15，未修 |

后者的根因：`'-'`(0x2D) < `'0'`(0x30)，故 `"20230825" >= "2023-08-28"`
**恒为 True** ⇒ 生效日前的记录按现行 0.5‰ 而非旧 1‰ 计费，
**单边成本低估 0.5‰**。由 `tests/test_track_costs.py` 暴露（HANDOVER §3 #15）。

本模块把「日期归一化 + 分段税率判定 + 计费」收敛为**一处**，
两处调用方一律 import。**不得再复制这段逻辑**——
复制一次，就会再产生一份可以独立腐化的副本。

## 权威出处（勿凭记忆改动）

- 印花税：财政部/税务总局公告，自 **2023-08-28** 起减半征收，卖出单边 **0.5‰**；
  此前为卖出单边 **1‰**。回测跨越生效日时**按交易日分段计费**。
- 过户费：中国结算公告，自 2022-04-29 起沪深两市 A 股统一按成交金额
  **0.01‰ 双向**收取。

## 与预注册的关系

见 `COST_AUTHORITY_AND_EMBARGO_PREREG.md` §二。该文件登记了作用对象检查
（修 #15 对 `tracking.db` 存量 13 行**零影响**）与判定标准 A-1~A-5。
"""
from typing import Optional

STAMP_DUTY_CHANGE_DATE = "2023-08-28"
STAMP_DUTY_SELL = 0.0005            # 现行：卖出单边 0.5‰（2023-08-28 起）
STAMP_DUTY_SELL_BEFORE = 0.001      # 旧：卖出单边 1‰（2023-08-28 之前）
TRANSFER_FEE_RATE = 0.00001         # 过户费 0.01‰ 双向（沪深两市均收）

__all__ = [
    "STAMP_DUTY_CHANGE_DATE", "STAMP_DUTY_SELL", "STAMP_DUTY_SELL_BEFORE",
    "TRANSFER_FEE_RATE", "norm_date", "stamp_rate", "trade_cost",
]


def norm_date(d) -> Optional[str]:
    """把日期统一成 `YYYYMMDD`（去横杠/斜杠，截断到 8 位）。

    `None` / 空值原样返回 `None`，由调用方决定「未提供日期」的口径。

    ⚠️ 这是本模块存在的理由：历史上直接 `str(as_of) >= "2023-08-28"`，
    而 `as_of` 可能来自 K 线的 `"20230825"`（不带横线）。
    字符串逐字符比较时 `'-'`(0x2D) < `'0'`(0x30) ⇒ 恒为 True
    ⇒ 印花税分段**完全失效**。
    """
    if d is None:
        return None
    s = str(d).strip()
    if not s:
        return None
    return s.replace("-", "").replace("/", "")[:8]


def stamp_rate(spec, as_of=None) -> float:
    """卖出印花税率：`as_of` 早于生效日用旧税率；未提供日期按现行税率。

    `spec` 需带 `stamp_duty_sell` / `stamp_duty_sell_before` /
    `stamp_duty_change_date` 属性（`Costs` 与 `TrackingCosts` 均自带默认值）。

    三种常见格式（`20230825` / `2023-08-25` / `2023/08/25`）结果一致，
    因为比较前先过 `norm_date()`。

    ⚠️ 语义与 `backtest_engine._stamp_rate` **逐分支一致**（这是工程收敛，
    不是口径变更）：`as_of` 或 `change_date` 为空时走现行税率，
    不因为「常量存在」就替调用方启用分段。
    """
    sell = getattr(spec, "stamp_duty_sell", STAMP_DUTY_SELL)
    before = getattr(spec, "stamp_duty_sell_before", STAMP_DUTY_SELL_BEFORE)
    change = getattr(spec, "stamp_duty_change_date", None)
    if not as_of or not change:
        return sell
    d = norm_date(as_of)
    if not d:
        # `as_of` 是非空但不可解析的串（如纯空格）⇒ 无可用日期，按现行税率。
        # 不能让 None 参与 `>=` 比较（会抛 TypeError）。
        return sell
    dc = norm_date(change)
    if not dc:
        # 类型收窄：norm_date 的签名是 Optional[str]，而走到这里 change 已通过
        # `not change` 校验（非空串）⇒ 运行时此分支不可达。保留是为了让 mypy
        # 不必假设 None；真出现时按「无分段点 ⇒ 现行税率」处理，与空值同语义。
        return sell
    return sell if d >= dc else before


def trade_cost(notional, side, spec, trade_date=None) -> float:
    """单笔交易成本（元）= 佣金 + 印花税（仅卖出）+ 过户费。

    与 `backtest_engine._trade_cost` 口径一致；本模块是权威实现。
    """
    commission = max(spec.min_commission, notional * spec.commission_rate)
    tax = notional * stamp_rate(spec, trade_date) if side == "sell" else 0.0
    transfer = notional * getattr(spec, "transfer_fee_rate", 0.0)
    return commission + tax + transfer
