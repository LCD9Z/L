# AI-Stock-God A-Share Unified v2

基础：Phase29 主线 + Phase15 治理/风险模块。

本轮升级：
- Crawl4AI 已接入 data_fetcher → Fact Sheet → Agent 主链路（可选，缺依赖自动降级）。
- 增加历史 cutoff_time / published_at 未来信息隔离。
- 增加 7 席专业评审委员会，并把委员会结果注入交易员阶段。
- 数据质量合并 OHLCV 检查与 PIT 检查，并保留 validate_bars 兼容接口。
- A股涨跌幅规则不再仅凭 is_st 硬编码 5%，优先读取逐日 limit_ratio/limit_pct。
- 新增 Crawl4AI mock/adapter 测试。

验证：
- `python -m compileall -q .` 通过。
- `python -m pytest -q`：63 passed。
- 当前环境未安装 Crawl4AI，因此真实浏览器抓取属于依赖门控项，不冒充已完成。
