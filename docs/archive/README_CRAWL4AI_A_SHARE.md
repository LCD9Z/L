# Crawl4AI 接入说明

## 目标架构

现有项目：
    data_fetcher -> fact_sheet -> agents.py -> 多空研究 -> Trader -> RiskManager

改造后：
    合法新闻/公告 URL
          ↓
    Crawl4AI
          ↓
    crawl4ai_fetcher.py
          ↓
    {title,url,source,published_at,crawled_at,content,summary,...}
          ↓
    data_fetcher / fact_sheet["news"]
          ↓
    agents.py
          ↓
    NewsAnalyst + SentimentAnalyst

## 安装

    pip install -r requirements-crawl4ai.txt
    crawl4ai-setup

## 最小调用

    from crawl4ai_fetcher import fetch_news_sync

    news = fetch_news_sync(
        urls=[
            "合法的新闻列表/公告页面URL",
        ],
        stock_code="600519",
        cutoff_time="2026-09-05T00:00:00+00:00",
    )

然后：

    fact_sheet["news"] = news

现有 agents.py 的 pack_data() 会继续把 fact_sheet 注入 Agent；NewsAnalyst 已经明确要求：
- 使用数据包中的新闻列表
- 区分直接相关与关键词匹配
- 没有新闻时写“数据未获取”
因此这里无需让 LLM 自己联网搜索。

## 关键设计

### 1. 防未来函数

`cutoff_time` 是强制的历史数据闸门：
- 有发布时间且 published_at <= cutoff_time：允许进入
- 没有发布时间：历史回测默认丢弃
- published_at > cutoff_time：丢弃

绝不能把 `crawled_at` 当成 `published_at`。

### 2. 不把 Crawl4AI 当成“新闻搜索引擎”

Crawl4AI 负责浏览器渲染、抓取、清洗和结构化提取；项目仍需要上层决定“哪些合法 URL 是新闻源/公告源”。

### 3. A股适配

情绪模块建议围绕：
- 涨停/跌停结构
- 连板高度
- 炸板率
- 成交额/换手率
- 市场宽度
- 板块强弱
- 资金指标

而不是以 Twitter/Reddit/VIX 为核心。

### 4. 生产环境进一步建议

- URL 白名单和来源优先级
- robots.txt / 网站条款遵守
- 每站点限速和失败重试
- SQLite/Redis 去重缓存
- 新闻正文哈希
- 发布时间字段质量监控
- 公告与新闻分开存储
- 交易日历与 cutoff_time 统一采用交易所时区
- 回测保存 crawl snapshot，保证结果可复现
