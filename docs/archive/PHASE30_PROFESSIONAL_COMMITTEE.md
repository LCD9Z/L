# Phase 30 — 专业评审委员会 + Crawl4AI 主链路

## 本轮完成
- Crawl4AI 从“独立模块”升级为 `data_fetcher -> Fact Sheet -> Agent` 可选主链路。
- `CRAWL4AI_ENABLED=1` 或 `run_analysis.py --crawl4ai` 时，先由现有搜索接口发现 URL，再由 Crawl4AI 抓取正文。
- 历史研究可传 `--cutoff-time`；没有 `published_at` 的新闻不会作为历史信息进入 Crawl4AI 历史模式。
- 7席专业评审委员会：量化、基本面、A股交易、微观结构、风控、数据审计、事件舆情。
- 交易员阶段自动接收委员会报告，避免只做“分析师平均分”。
- 数据质量同时检查 OHLCV、日期、重复、异常跳变与 PIT 时间门禁。
- 交易规则不再仅凭 `is_st` 硬编码 5%；优先要求逐日数据提供真实 `limit_ratio`/`limit_pct`，否则采用品种默认值。

## 当前限制
- 当前执行环境未安装 Crawl4AI，因此只能完成适配层、mock 测试和静态验证；安装 `requirements-crawl4ai.txt` 后才能做真实浏览器抓取。
- Crawl4AI 本身不是搜索引擎，URL 发现仍由上层数据源负责。
