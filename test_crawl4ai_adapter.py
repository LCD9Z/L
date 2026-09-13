import unittest
from unittest.mock import patch

import data_fetcher
from crawl4ai_fetcher import _before_cutoff, _dedupe_news


class TestCrawl4AIAdapter(unittest.TestCase):
    def test_cutoff_rejects_missing_publish_time(self):
        self.assertFalse(_before_cutoff(None, "2026-09-06T00:00:00+00:00"))

    def test_cutoff_rejects_future_news(self):
        self.assertFalse(_before_cutoff("2026-09-07T00:00:00+00:00", "2026-09-06T00:00:00+00:00"))
        self.assertTrue(_before_cutoff("2026-09-05T00:00:00+00:00", "2026-09-06T00:00:00+00:00"))

    def test_dedupe(self):
        rows = [
            {"title":"A", "url":"u", "content":"x"},
            {"title":"A", "url":"u", "content":"x"},
        ]
        self.assertEqual(len(_dedupe_news(rows)), 1)

    def test_data_fetcher_falls_back_when_crawl4ai_unavailable(self):
        rows = [{"date":"2026-09-06", "title":"A", "media":"M", "url":"https://x/a"}]
        with patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", None):
            out = data_fetcher._news_with_crawl4ai(rows, "000001", enabled=True)
        self.assertEqual(out, rows)


# ---------------------------------------------------------------------------
# 启用分支覆盖（crawl4ai 未安装时用 mock 注入抓取器，驱动被启用的代码路径）
# ---------------------------------------------------------------------------

def _original_rows():
    return [
        {"date": "2026-09-06", "title": "原始标题A", "media": "原始媒体", "url": "https://x/a"},
        {"date": "2026-09-06", "title": "原始标题B", "media": "原始媒体", "url": "https://x/b"},
    ]


def test_enabled_path_prefers_crawled_title_media_and_content():
    """启用时以抓取结果为准，同时保留搜索层的日期字段。"""
    crawled = [{
        "url": "https://x/a", "title": "清洗后标题A", "source": "清洗后来源",
        "published_at": "2026-09-05T10:00:00+00:00", "crawled_at": "2026-09-06T00:00:00+00:00",
        "content": "正文A", "summary": "摘要A", "content_hash": "h" * 64,
    }]
    with patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", lambda urls, **kw: crawled):
        out = data_fetcher._news_with_crawl4ai(_original_rows(), "000001", enabled=True)

    assert len(out) == 2
    a, b = out
    assert a["title"] == "清洗后标题A"
    assert a["media"] == "清洗后来源"
    assert a["content"] == "正文A"
    assert a["crawler"] == "crawl4ai"
    assert a["stock_code"] == "000001"
    assert a["date"] == "2026-09-06"
    # 未被抓取到的行原样保留，不得凭空补造 content
    assert b == _original_rows()[1]
    assert "content" not in b


def test_enabled_path_falls_back_when_crawler_raises():
    def boom(urls, **kw):
        raise RuntimeError("browser crashed")

    with patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", boom):
        out = data_fetcher._news_with_crawl4ai(_original_rows(), "000001", enabled=True)
    assert out == _original_rows()


def test_enabled_path_falls_back_on_empty_crawl_result():
    with patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", lambda urls, **kw: []):
        out = data_fetcher._news_with_crawl4ai(_original_rows(), "000001", enabled=True)
    assert out == _original_rows()


def test_rows_without_url_short_circuit_without_launching_crawler():
    called = []

    def spy(urls, **kw):
        called.append(urls)
        return []

    rows = [{"date": "2026-09-06", "title": "无链接", "media": "M"}]
    with patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", spy):
        out = data_fetcher._news_with_crawl4ai(rows, "000001", enabled=True)
    assert out == rows
    assert called == [], "无 URL 时不应启动浏览器"


def test_enabled_flag_reads_environment(monkeypatch):
    """enabled=None 时应回落到 CRAWL4AI_ENABLED 环境变量。"""
    seen = []

    def spy(urls, **kw):
        seen.append(list(urls))
        return []

    monkeypatch.delenv("CRAWL4AI_ENABLED", raising=False)
    with patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", spy):
        data_fetcher._news_with_crawl4ai(_original_rows(), "000001")
    assert seen == [], "环境变量未开启时不应调用抓取器"

    monkeypatch.setenv("CRAWL4AI_ENABLED", "1")
    with patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", spy):
        data_fetcher._news_with_crawl4ai(_original_rows(), "000001")
    assert seen == [["https://x/a", "https://x/b"]]


def test_cutoff_time_is_passed_through_to_crawler():
    """PIT 纪律：cutoff_time 必须透传到抓取层，否则历史研究会引入未来信息。"""
    received = {}

    def spy(urls, **kw):
        received.update(kw)
        return []

    with patch.object(data_fetcher, "_crawl4ai_fetch_news_sync", spy):
        data_fetcher._news_with_crawl4ai(
            _original_rows(), "000001", cutoff_time="2026-09-06T00:00:00+00:00", enabled=True)
    assert received.get("cutoff_time") == "2026-09-06T00:00:00+00:00"
    assert received.get("stock_code") == "000001"


if __name__ == "__main__":
    unittest.main()
