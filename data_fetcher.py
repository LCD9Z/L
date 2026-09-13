# -*- coding: utf-8 -*-
"""L2 数据管道 · 门面模块（向后兼容）。

历史上全部取数逻辑集中在本文件（807 行）。现按职责拆分到 `fetch/` 包：

    fetch/transport.py  HTTP 传输：SSL 复用 / 缓存 / 令牌桶限流 / 统一 GET
    fetch/common.py     公共常量与纯函数（字段表、代码规范化、数值解析）
    fetch/quote.py      实时行情（东财 + 腾讯兜底）
    fetch/kline.py      历史日K（东财 / 腾讯 / 通达信本地，不复权）
    fetch/news.py       新闻与事实数据包（含 Crawl4AI 可选增强）
    fetch/cli.py        命令行入口

本模块重新导出全部既有符号，**`from data_fetcher import X` /
`import data_fetcher; data_fetcher.X` 的用法完全不变**。
新代码可直接从 `fetch.*` 子模块导入以减少依赖面。

本地日K兜底：默认读 `D:\\new_tdx\\vipdoc\\{sh,sz,bj}\\lday\\*.day`（可用 TDX_ROOT 覆盖），
为**不复权**数据，返回包中会标注以提示下游。

用法：
    python data_fetcher.py 600519 --news 5     # 打印事实数据包
    python data_fetcher.py sh600519 --json     # 输出 JSON 结构
"""

from fetch.cli import (
    main,
)
from fetch.common import (
    QUOTE_FIELDS,
    _d,
    _days_ago,
    _empty_quote,
    _fmt_amount,
    _safe_float,
    normalize_code,
)
from fetch.kline import (
    KlineList,
    _TDX_ROOT,
    _fetch_kline_eastmoney,
    _fetch_kline_tdx,
    _fetch_kline_tencent,
    _validate_kline_rows,
    fetch_close_on,
    fetch_kline,
)
from fetch.news import (
    _news_with_crawl4ai,
    build_fact_sheet,
    fact_sheet_to_text,
    fetch_news,
)
from fetch.quote import (
    fetch_quote,
    fetch_quote_eastmoney,
    fetch_quote_tencent,
)
from fetch.transport import (
    _RATE_LIMITER,
    _SSL_CTX,
    _TokenBucket,
    _cache_get,
    _cache_set,
    _http_get,
)

__all__ = [
    "QUOTE_FIELDS",
    "_RATE_LIMITER",
    "_SSL_CTX",
    "_TDX_ROOT",
    "KlineList",
    "_TokenBucket",
    "_cache_get",
    "_cache_set",
    "_d",
    "_days_ago",
    "_empty_quote",
    "_fetch_kline_eastmoney",
    "_fetch_kline_tdx",
    "_fetch_kline_tencent",
    "_fmt_amount",
    "_http_get",
    "_news_with_crawl4ai",
    "_safe_float",
    "_validate_kline_rows",
    "build_fact_sheet",
    "fact_sheet_to_text",
    "fetch_close_on",
    "fetch_kline",
    "fetch_news",
    "fetch_quote",
    "fetch_quote_eastmoney",
    "fetch_quote_tencent",
    "main",
    "normalize_code",
]


if __name__ == "__main__":
    main()
