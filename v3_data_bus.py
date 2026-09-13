# -*- coding: utf-8 -*-
"""V3 facade: legacy fetcher + normalized contract + deterministic factors."""
from typing import Optional

from ashare.ashare_factor_engine import compute_factors, score_candidate
from ashare.ashare_market import event_flags, execution_constraints
from candidate_prefilter import prefilter_fact_sheet
from ashare.ashare_event_engine import build_event_risk_pack
from ashare.ashare_flow_engine import moneyflow_features, top_list_features
from data_contracts import DataBundle, DataProvenance, MarketBar, NewsItem
import data_fetcher


def build_v3_bundle(code: str, news_limit: int = 5, cutoff_time: Optional[str] = None,
                    use_crawl4ai: Optional[bool] = None) -> DataBundle:
    fact = data_fetcher.build_fact_sheet(
        code, news_limit=news_limit, cutoff_time=cutoff_time,
        use_crawl4ai=use_crawl4ai,
    )
    bundle = DataBundle(
        code=str(fact.get("code") or code),
        asof=cutoff_time or fact.get("meta", {}).get("cutoff_time"),
        quote=fact.get("quote") or {},
        provider_trace=[],
    )
    bars = fact.get("kline", []) or fact.get("history", {}).get("bars", []) or fact.get("bars", []) or []
    for row in bars:
        bundle.bars.append(MarketBar(
            code=bundle.code,
            trade_date=str(row.get("date") or row.get("trade_date") or ""),
            open=row.get("open"), high=row.get("high"), low=row.get("low"), close=row.get("close"),
            volume=row.get("volume"), amount=row.get("amount"), turnover=row.get("turnover"),
            limit_ratio=row.get("limit_ratio") or row.get("limit_pct"),
            is_suspended=row.get("is_suspended"), is_st=row.get("is_st"),
            adjusted=str(row.get("adjusted") or "unknown"),
            provenance=DataProvenance(source=str(row.get("src") or "unknown"), provider=str(row.get("src") or "unknown")),
        ))
    for row in fact.get("news", []) or []:
        bundle.news.append(NewsItem(
            code=bundle.code, title=str(row.get("title") or ""),
            published_at=row.get("published_at"), source=str(row.get("source") or row.get("src") or "unknown"),
            url=row.get("url"), content=row.get("content"), summary=row.get("summary"),
            crawled_at=row.get("crawled_at"), content_hash=row.get("content_hash"),
            provenance=DataProvenance(source=str(row.get("source") or "unknown"), provider="crawl4ai" if row.get("crawled_at") else str(row.get("src") or "unknown"),
                                      published_at=row.get("published_at"), asof=cutoff_time, source_url=row.get("url"), content_hash=row.get("content_hash")),
        ))
    raw_bars = [b.to_dict() for b in bundle.bars]
    bundle.factors = compute_factors(raw_bars)
    bundle.events["news_count"] = len(bundle.news)
    # V3.2事件/资金层：只消费已由上游提供且带PIT信息的数据；缺失时保持空状态。
    raw_events = fact.get("events") or []
    bundle.events["event_risk"] = build_event_risk_pack(raw_events, cutoff_time)
    bundle.events["moneyflow"] = moneyflow_features(fact.get("moneyflow") or [])
    bundle.events["top_list"] = top_list_features(fact.get("top_list") or [])
    bundle.events["market_constraints"] = execution_constraints(bundle.code, bundle.quote)
    bundle.events["price_structure"] = event_flags(bundle.code, raw_bars)
    bundle.events["prefilter"] = prefilter_fact_sheet(fact)
    bundle.events["crawl4ai_enabled"] = fact.get("meta", {}).get("crawl4ai_enabled")
    bundle.quality = fact.get("quality") or fact.get("meta", {}).get("quality") or {}
    if bundle.quote.get("src"):
        bundle.provider_trace.append(bundle.quote["src"])
    if bundle.news:
        bundle.provider_trace.append("news")
    bundle.events["deterministic_candidate_score"] = score_candidate(bundle.factors)
    return bundle
