# -*- coding: utf-8 -*-
"""
Crawl4AI A股新闻/公告抓取模块
--------------------------------
设计目标：
1. 用 Crawl4AI 统一处理 JS 页面、HTML -> Markdown、批量异步抓取。
2. 新闻必须保留 source_url / published_at / crawled_at，禁止把抓取时间当成发布时间。
3. 支持 cutoff_time，避免回测/历史选股时把未来新闻喂给 Agent。
4. 本模块只负责“抓取与清洗”，不让 LLM 自由生成新闻事实。
5. 与现有 data_fetcher/fact_sheet 结构兼容：输出 news 列表。

依赖：
    pip install -U crawl4ai beautifulsoup4
    crawl4ai-setup

Crawl4AI 当前推荐使用 AsyncWebCrawler + BrowserConfig + CrawlerRunConfig。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    CRAWL4AI_AVAILABLE = True
except ImportError:
    AsyncWebCrawler = BrowserConfig = CrawlerRunConfig = CacheMode = None
    CRAWL4AI_AVAILABLE = False


@dataclass
class CrawledNews:
    title: str
    url: str
    source: str
    published_at: Optional[str]
    crawled_at: str
    content: str
    summary: str = ""
    stock_code: Optional[str] = None
    content_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    # ISO / 常见中文时间格式
    candidates = [s, s.replace("Z", "+00:00")]
    for x in candidates:
        try:
            dt = datetime.fromisoformat(x)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass

    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _before_cutoff(published_at: Optional[str], cutoff_time: Optional[str]) -> bool:
    """没有发布时间时：默认不允许进入历史回测，避免未来信息泄漏。"""
    if not cutoff_time:
        return True
    cutoff = _normalize_dt(cutoff_time)
    if not cutoff:
        raise ValueError(f"invalid cutoff_time: {cutoff_time}")

    if not published_at:
        return False

    return published_at <= cutoff


def _clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text or "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _source_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def _hash_news(title: str, url: str, content: str) -> str:
    raw = f"{title}\n{url}\n{content[:5000]}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()


def _extract_published_at(result: Any) -> Optional[str]:
    """
    尽量从 Crawl4AI 结果/HTML metadata 中提取发布时间。
    注意：抓不到发布时间时返回 None，而不是用 crawled_at 冒充。
    """
    for attr in ("metadata", "meta", "response_headers"):
        obj = getattr(result, attr, None)
        if isinstance(obj, dict):
            for key in (
                "published_time", "publish_time", "datePublished",
                "article:published_time", "date", "published_at",
            ):
                value = obj.get(key)
                dt = _normalize_dt(value)
                if dt:
                    return dt

    html = getattr(result, "html", "") or getattr(result, "cleaned_html", "")
    if not html:
        return None

    # JSON-LD datePublished
    matches = re.findall(
        r'"datePublished"\s*:\s*"([^"]+)"', html, flags=re.I
    )
    for m in matches:
        dt = _normalize_dt(m)
        if dt:
            return dt

    # meta property/date
    patterns = [
        r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|publish_time|date)["\'][^>]+content=["\']([^"\']+)',
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        for m in re.findall(pattern, html, flags=re.I):
            dt = _normalize_dt(m)
            if dt:
                return dt

    return None


def _extract_title(result: Any, fallback_url: str) -> str:
    title = getattr(result, "title", None)
    if title:
        return _clean_text(str(title))

    html = getattr(result, "html", "") or ""
    if BeautifulSoup and html:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            return _clean_text(soup.title.string)

    return fallback_url


def _extract_content(result: Any) -> str:
    # filtered markdown 优先；没有则使用普通 markdown
    markdown = getattr(result, "fit_markdown", None) or getattr(result, "markdown", None)
    if markdown:
        return _clean_text(str(markdown))

    html = getattr(result, "cleaned_html", None) or getattr(result, "html", None) or ""
    if BeautifulSoup and html:
        return _clean_text(BeautifulSoup(html, "html.parser").get_text("\n"))

    return ""


def _make_summary(content: str, max_chars: int = 800) -> str:
    text = _clean_text(content)
    return text[:max_chars]


class AShareCrawler:
    """
    可长期复用的 Crawl4AI crawler。

    注意：
    - sources 必须是你合法获取、允许自动化访问的页面 URL。
    - 不绕过验证码、登录墙或网站访问控制。
    """

    def __init__(
        self,
        headless: bool = True,
        user_agent: Optional[str] = None,
        page_timeout: int = 60000,
    ):
        kwargs = {
            "browser_type": "chromium",
            "headless": headless,
            "text_mode": True,
            "viewport_width": 1440,
            "viewport_height": 900,
        }
        if user_agent:
            kwargs["user_agent"] = user_agent

        if not CRAWL4AI_AVAILABLE:
            raise RuntimeError("Crawl4AI is not installed; install requirements-crawl4ai.txt")
        self.browser_config = BrowserConfig(**kwargs)
        self.run_config = CrawlerRunConfig(
            cache_mode=CacheMode.ENABLED,
            word_count_threshold=30,
            excluded_tags=["nav", "footer", "aside", "script", "style"],
            exclude_external_links=True,
            remove_overlay_elements=True,
            wait_until="domcontentloaded",
            page_timeout=page_timeout,
        )

    async def crawl(
        self,
        urls: Iterable[str],
        stock_code: Optional[str] = None,
        cutoff_time: Optional[str] = None,
        max_chars: int = 12000,
    ) -> List[Dict[str, Any]]:
        urls = list(dict.fromkeys(u for u in urls if u))
        results: List[Dict[str, Any]] = []
        crawled_at = _now_iso()

        async with AsyncWebCrawler(config=self.browser_config) as crawler:
            # Crawl4AI 提供 arun_many；这里采用逐页 arun，便于逐条记录错误和时间过滤。
            for url in urls:
                try:
                    result = await crawler.arun(url=url, config=self.run_config)
                    if not getattr(result, "success", False):
                        continue

                    title = _extract_title(result, url)
                    content = _extract_content(result)
                    if not content:
                        continue

                    published_at = _extract_published_at(result)
                    if not _before_cutoff(published_at, cutoff_time):
                        continue

                    item = CrawledNews(
                        title=title,
                        url=url,
                        source=_source_from_url(url),
                        published_at=published_at,
                        crawled_at=crawled_at,
                        content=content[:max_chars],
                        summary=_make_summary(content),
                        stock_code=stock_code,
                    )
                    item.content_hash = _hash_news(item.title, item.url, item.content)
                    results.append(item.to_dict())
                except Exception:
                    # 单站点失败不影响其它新闻源；上层可记录日志。
                    continue

        return _dedupe_news(results)


def _dedupe_news(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        key = item.get("content_hash") or _hash_news(
            item.get("title", ""), item.get("url", ""), item.get("content", "")
        )
        if key in seen:
            continue
        seen.add(key)
        item["content_hash"] = key
        out.append(item)

    out.sort(
        key=lambda x: x.get("published_at") or x.get("crawled_at") or "",
        reverse=True,
    )
    return out


def fetch_news_sync(
    urls: Iterable[str],
    stock_code: Optional[str] = None,
    cutoff_time: Optional[str] = None,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """给现有同步 data_fetcher 调用方使用。"""
    crawler = AShareCrawler(headless=headless)
    return asyncio.run(
        crawler.crawl(
            urls=urls,
            stock_code=stock_code,
            cutoff_time=cutoff_time,
        )
    )


async def fetch_news(
    urls: Iterable[str],
    stock_code: Optional[str] = None,
    cutoff_time: Optional[str] = None,
) -> List[Dict[str, Any]]:
    crawler = AShareCrawler()
    return await crawler.crawl(
        urls=urls,
        stock_code=stock_code,
        cutoff_time=cutoff_time,
    )


def merge_news_into_fact_sheet(
    fact_sheet: Dict[str, Any],
    news: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    不破坏现有 fact_sheet，只增加/覆盖 news。
    agents.py 已经通过 pack_data 把 fact_sheet 注入各 Agent。
    """
    out = dict(fact_sheet or {})
    out["news"] = _dedupe_news(news)
    return out


def news_to_fact_sheet_text(news: List[Dict[str, Any]]) -> str:
    """可供现有 fact_sheet_to_text() 采用的新闻文本格式。"""
    if not news:
        return "【新闻数据】数据未获取"

    lines = ["【新闻数据】"]
    for i, item in enumerate(news, 1):
        lines.append(
            f"{i}. 标题：{item.get('title')}\n"
            f"   来源：{item.get('source')}\n"
            f"   发布时间：{item.get('published_at') or '数据未获取'}\n"
            f"   URL：{item.get('url')}\n"
            f"   摘要：{item.get('summary') or item.get('content', '')[:500]}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    # 示例：
    # python crawl4ai_fetcher.py
    # 实际项目中应由 data_fetcher/调度器传入合法新闻 URL。
    urls = [
        "https://example.com/",
    ]
    data = fetch_news_sync(urls, stock_code="000001")
    print(json.dumps(data, ensure_ascii=False, indent=2))
