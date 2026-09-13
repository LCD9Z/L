# Phase 31 — V3 A股专业数据与量化增强

## 本轮目标

在 V2（Crawl4AI + PIT + 专业评审委员会）上增加一层稳定的 **A股 Data Bus / Quant Skill / Deterministic Factor** 架构，而不是直接复制第三方项目。

参考方向：
- `a-stock-data`：多数据源、主源/备源降级、A股数据覆盖。
- `finance-quant-skills`：把量化工具变成 Agent 可调用的技能，而不是把 Agent 写死在某个库上。
- `easy_tdx`：通达信行情/指标作为可选数据与技术分析能力。
- `tickflow-stock-panel`：选股、监控、回测工作台的工程化思路。
- `TradingAgents-Astock`：A股规则下的多 Agent 角色和辩论思路。

## 已实现

1. `data_contracts.py`
   - 统一 MarketBar / NewsItem / DataBundle / DataProvenance。
   - 保留 source、provider、published_at、retrieved_at、asof、URL、hash 等审计信息。
2. `provider_router.py`
   - Provider 注册与优先级路由。
   - 单数据源失败不会击穿整个分析流程。
3. `quant_skill_router.py`
   - 建立 market_data / technical_factors / factor_research / backtest / fundamental / event_research / execution 技能词汇。
   - 第三方技能仓库作为能力来源，不作为强制运行时依赖。
4. `ashare_factor_engine.py`
   - 在 LLM 之前计算 5日/20日动量、20日实现波动率、20日回撤、成交量/成交额比等确定性指标。
   - 缺失数据不填造；评分只是候选排序信号，不是交易建议。
5. `v3_data_bus.py`
   - 将 V2 的 `data_fetcher.build_fact_sheet()` 转换成 V3 DataBundle。
   - 保留 Crawl4AI 新闻能力和历史 cutoff。
6. `test_v3_architecture.py`
   - 验证确定性、provider fallback、skill routing、provenance。

## 明确不做

- 不直接复制第三方项目代码。
- 不把 LLM 的“评分”当成量化因子真值。
- 不因为接入更多数据源就绕过 PIT、停牌、涨跌停、T+1、幸存者偏差检查。
- 不把当前股票池当成历史全市场宇宙。

## 下一阶段

- 将 `v3_data_bus.py` 接到 `run_analysis.py` / `daily_stock_pick.py`。
- 将龙虎榜、资金流、公告、解禁等字段纳入 DataBundle 的 events/factors。
- 增加多源一致性检查：同一事实的 source disagreement 要进入委员会。
- 增加候选池的确定性预筛选，再交给多 Agent 做定性研究。
- Windows 10 + 8GB RAM 环境默认单浏览器、低并发 Crawl4AI。
