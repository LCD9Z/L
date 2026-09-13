# Phase 37 — Stage-2 Alpha 消融实验框架

## 目标

验证 Stage-2 的资金流、龙虎榜、微观结构、事件风险是否对 Stage-1 提供**独立增量信息**，而不是因为增加复杂度就看起来更强。

## 实验模型

- `stage1`
- `stage1 + flow`
- `stage1 + top_list`
- `stage1 + microstructure`
- `stage1 + event_risk`
- `stage2_full`

每个模型均在同一交易日横截面内做 rank，再与 Stage-1 按显式 overlay weight 混合。默认 overlay weight 为 35%。

## 指标

对 T+1 / T+3 / T+5 / T+10 / T+20 分别计算：

- IC mean
- RankIC mean
- ICIR
- RankICIR
- IC / RankIC 正向比例
- Top 20% - Bottom 20% 平均收益差
- Top 20% > Bottom 20% 胜率
- 相对 Stage-1 的 RankIC 增量
- 相对 Stage-1 的分组收益差增量

## 防泄漏边界

- 因子只使用 t 日及之前的字段。
- forward return 严格使用 t+h 之后的收盘价。
- 横截面排名在同一交易日内完成。
- 缺失值不填假值。
- 不把合成模型的实验结果直接写回生产权重。

## 当前验证

工程测试：91 passed。

当前测试使用的是小型 synthetic fixture，仅验证实验机械逻辑，不代表真实 A 股 Alpha。

## 下一阶段

拿到严格认证的 Point-in-Time A 股历史数据后，先跑完整消融，再进行 Walk-Forward / OOS 验证。只有某个 Stage-2 组件在 OOS 中产生稳定增量，才允许进入生产权重；否则降权或删除。
