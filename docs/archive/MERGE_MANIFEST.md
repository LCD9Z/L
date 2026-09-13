# A股 AI 选股统一合并版

## 合并策略
- Phase29 作为主干版本，优先保留其更新后的数据、回测、执行与 Alpha 生存能力。
- Phase15 Governance 独有的治理/验证能力并入主干：performance、phase13_risk、phase15_governance、point_in_time、research_integrity、risk_engine、stress_test、validation_suite 及其对应测试。
- 对同名文件不做盲目覆盖；11 个有内容差异的同名文件以 Phase29 为主，因为其代码包含后续阶段的 A 股执行/数据能力。
- 加入 Crawl4AI 新闻/公告抓取适配层，带发布时间硬截断、去重和 Fact Sheet 注入接口。

## Crawl4AI
入口：`crawl4ai_fetcher.py`
安装：`pip install -r requirements-crawl4ai.txt`

注意：Crawl4AI 是网页抓取/渲染/清洗层，不负责新闻搜索。生产环境应由上层提供合法、稳定、允许抓取的公告/新闻 URL。

## 数据真实性
历史回测必须使用公告/新闻的 `published_at` 与回测 cutoff 进行时点过滤，不得以抓取时间替代发布时间；缺失发布时间时，在设置 cutoff 的历史回测场景下默认丢弃。
