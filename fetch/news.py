# -*- coding: utf-8 -*-
"""新闻与事实数据包：东财新闻、Crawl4AI 可选增强、fact sheet 组装与文本化。

由 data_fetcher.py 拆分而来（对外 API 不变，实现下沉到 fetch/ 包）。
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional
from .common import (
    _fmt_amount,
    normalize_code,
)
from .kline import (
    fetch_kline,
)
from .quote import (
    fetch_quote,
)
from .transport import (
    _http_get,
)


# Crawl4AI 为可选依赖：未安装时主流程仍可使用原有东财/腾讯新闻。
_crawl4ai_fetch_news_sync: Optional[Callable[..., Any]] = None
try:
    from crawl4ai_fetcher import fetch_news_sync as _crawl4ai_fetch_news_sync
except Exception:
    _crawl4ai_fetch_news_sync = None



def fetch_news(keyword: str, limit: int = 5):
    """东财关键词新闻搜索，返回 [{date,title,media,url}]。失败返回 []。"""
    if not keyword:
        return []
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {
        "cb": "x",
        "param": json.dumps({
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default", "pageIndex": 1, "pageSize": limit, "preTag": "", "postTag": ""}},
        }, ensure_ascii=False),
    }
    full = f"{url}?{urllib.parse.urlencode(params)}"
    text = _http_get(full)
    if not text:
        return []
    start = text.find("(")
    end = text.rfind(")")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start + 1:end])
    except json.JSONDecodeError:
        return []
    items = (data.get("result") or {}).get("cmsArticleWebOld") or []
    out = []
    for it in items:
        out.append({
            "date": it.get("date", ""),
            "title": it.get("title", ""),
            "media": it.get("mediaName", ""),
            "url": it.get("url", ""),
        })
    return out



def _news_with_crawl4ai(
    news_rows,
    stock_code,
    cutoff_time=None,
    enabled=None,
):
    """把关键词检索得到的文章 URL 交给 Crawl4AI 做正文清洗。

    设计原则：Crawl4AI 只负责页面抓取/清洗，不负责搜索；搜索仍由现有数据源完成。
    若依赖未安装、未启用或全部页面抓取失败，则返回原始新闻结果。
    """
    if enabled is None:
        enabled = os.environ.get("CRAWL4AI_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or _crawl4ai_fetch_news_sync is None:
        return news_rows
    urls = [x.get("url") for x in (news_rows or []) if x.get("url")]
    if not urls:
        return news_rows
    try:
        crawled = _crawl4ai_fetch_news_sync(
            urls, stock_code=stock_code, cutoff_time=cutoff_time,
            headless=os.environ.get("CRAWL4AI_HEADLESS", "1") not in {"0", "false", "no"},
        )
    except Exception:
        return news_rows
    if not crawled:
        return news_rows

    # 保留搜索层字段，同时优先采用 Crawl4AI 的正文、发布时间和规范来源。
    by_url = {str(x.get("url")): x for x in crawled if x.get("url")}
    out = []
    for row in news_rows:
        url = str(row.get("url") or "")
        c = by_url.get(url)
        if c:
            out.append({
                "date": row.get("date", ""),
                "title": c.get("title") or row.get("title", ""),
                "media": c.get("source") or row.get("media", ""),
                "url": url,
                "published_at": c.get("published_at"),
                "crawled_at": c.get("crawled_at"),
                "content": c.get("content", ""),
                "summary": c.get("summary", ""),
                "stock_code": stock_code,
                "content_hash": c.get("content_hash", ""),
                "crawler": "crawl4ai",
            })
        else:
            out.append(dict(row))
    return out



def build_fact_sheet(code, news_limit=5, cutoff_time=None, use_crawl4ai=None, factor_window=60):
    """构建事实数据包：行情 + 新闻 + 近期K线。

    行情与K线无依赖关系，使用线程池并行取数以缩短总耗时；新闻依赖行情中的
    股票名称做关键词，故在行情返回后再取，避免多打一次无效请求。
    Crawl4AI 集成在新闻层：先由现有搜索接口发现文章 URL，再由 Crawl4AI 抓正文。
    cutoff_time 用于历史研究时的未来信息隔离；没有发布时间的网页在历史模式下会被丢弃。
    """
    std, _, _ = normalize_code(code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_quote = pool.submit(fetch_quote, code)
        fut_kline = pool.submit(fetch_kline, std, limit=factor_window)
        q = fut_quote.result()
        kline = fut_kline.result()
    name = q.get("name")
    try:
        from ashare.ashare_market import board_of
        q["board"] = board_of(std)
    except Exception:
        q["board"] = "未知"
    news_keyword = name if name else f"{std} 股票"
    news = fetch_news(news_keyword, limit=news_limit)
    news = _news_with_crawl4ai(
        news, stock_code=std, cutoff_time=cutoff_time, enabled=use_crawl4ai
    )
    try:
        from ashare.ashare_factor_engine import compute_factors, score_candidate
        factor_pack = compute_factors(kline)
        factor_score = score_candidate(factor_pack)
    except Exception as _factor_exc:  # factor layer must never break core data collection
        factor_pack = {"status": "error", "error": str(_factor_exc), "factors": {}}
        factor_score = {"score": None, "reasons": []}
    meta = {
        "code": std,
        "company": q.get("name") or std,
        "data_source": q.get("src") or "未知",
        "quote_time": q.get("quote_time") or "",
        "cutoff_time": cutoff_time or "",
        "crawl4ai_enabled": bool(use_crawl4ai if use_crawl4ai is not None else os.environ.get("CRAWL4AI_ENABLED", "0").lower() in {"1", "true", "yes", "on"}),
        "factor_window": factor_window,
        "note": q.get("note") or "",
    }
    return {"meta": meta, "quote": q, "news": news, "kline": kline,
            "quant_factors": factor_pack, "quant_score": factor_score}



def fact_sheet_to_text(sheet) -> str:
    """事实数据包 → 文本（供模型使用）。"""
    m = sheet["meta"]
    q = sheet["quote"]
    header = "【数据包】（来源：" + str(m.get("data_source", "未知"))
    if m.get("quote_time"):
        header += "，行情时间：" + str(m["quote_time"])
    if m.get("note"):
        header += "；" + str(m["note"])
    header += "）"
    lines = [header]
    lines.append(f"股票：{m.get('company')}（{m.get('code')}）")
    lines.append(
        f"现价 {q.get('price')} 元 | 涨跌幅 {q.get('change_pct')}% | "
        f"涨跌额 {q.get('change')} | 今开 {q.get('open')} | 昨收 {q.get('prev_close')}"
    )
    lines.append(
        f"最高 {q.get('high')} | 最低 {q.get('low')} | 成交量 {q.get('volume')} 手 | "
        f"成交额 {_fmt_amount(q.get('amount'))}"
    )
    lines.append(
        f"换手 {q.get('turnover')}% | 振幅 {q.get('amplitude')}% | "
        f"PE(TTM) {q.get('pe')} | PB {q.get('pb')}"
    )
    lines.append(
        f"总市值 {_fmt_amount(q.get('total_mv'))} | 流通市值 {_fmt_amount(q.get('float_mv'))}"
    )
    qf = sheet.get("quant_factors") or {}
    qs = sheet.get("quant_score") or {}
    if qf.get("factors"):
        lines.append("确定性量化因子（仅作为候选筛选证据，不是交易指令）：")
        for k, v in qf.get("factors", {}).items():
            lines.append(f"  {k}: {v}")
        if qs.get("score") is not None:
            lines.append(f"  deterministic_candidate_score: {qs.get('score')}")
    elif qf.get("status"):
        lines.append(f"确定性量化因子状态：{qf.get('status')}")
    kline = sheet.get("kline") or []
    if kline:
        n = len(kline)
        display_kline = kline[-12:]
        kline_src = getattr(kline, "source", None)
        if kline_src == "tdx_local_raw":
            lines.append(
                f"近{n}个交易日（日期 开盘 收盘 最高 最低 涨跌%）"
                "【⚠️ 本地不复权数据，跨除权日会跳价，仅供形态参考】"
            )
        else:
            lines.append(f"近{n}个交易日（日期 开盘 收盘 最高 最低 涨跌%）：")
        prev_close = None
        for r in display_kline:
            chg = ""
            if prev_close:
                chg = f" {round((r['close'] - prev_close) / prev_close * 100, 2)}%"
            lines.append(f"  {r['date']} {r['open']} {r['close']} {r['high']} {r['low']}{chg}")
            prev_close = r["close"]
    news = sheet.get("news") or []
    if news:
        lines.append(f"近期新闻（前{len(news)}条）：")
        for i, n in enumerate(news, 1):
            lines.append(f"  {i}. [{n.get('date')}] {n.get('title')}（{n.get('media')}）")
    else:
        lines.append("近期新闻：暂无")
    return "\n".join(lines)
