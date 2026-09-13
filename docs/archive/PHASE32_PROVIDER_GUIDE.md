# Phase 32 Provider Guide

可选真实数据源：TuShare。运行环境设置 `TUSHARE_TOKEN` 后，可调用 `TuShareEventProvider` 获取：

- moneyflow：资金流
- top_list / top_inst：龙虎榜及机构席位
- forecast / express：业绩预告/快报
- share_float：解禁
- stk_holdertrade：股东增减持
- repurchase：回购

设计上每个 endpoint 独立失败，不会因为单一接口限流导致整条研究链崩溃；失败会进入 `errors`。这些数据进入回测前仍必须经过发布日期/PIT审计。

**重要：**该适配器不会伪造数据，也不会把“净流入”自动解释成“主力建仓”。
