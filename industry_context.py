# -*- coding: utf-8 -*-
"""每日选股 · 行业相对强度集成（Phase 8）。

由 daily_stock_pick.py 拆分而来（1.0）。仅使用当前已获取的历史 K 线构建
行业相对强度，数据不足时降级为空排名，不阻塞每日任务。

注意：行业分类必须使用历史时点分类，不能用今天的归属回填历史。
"""
from data_fetcher import fetch_kline
from industry_strength import rank_industries, stock_industry_bonus
from runtime_env import log


def _industry_from_item(item):
    """优先使用显式行业字段，兼容旧版 note。"""
    return item.get("industry") or (item.get("note") or "未知行业").split("·")[0]


def build_industry_context(watchlist):
    """Phase 8 集成：仅使用当前已获取的历史K线构建行业相对强度。
    数据不足时降级为空排名，不阻塞每日任务。
    """
    bars, industry_map = {}, {}
    for item in watchlist:
        code = item["code"]
        industry_map[code] = _industry_from_item(item)
        try:
            rows = fetch_kline(code, limit=70, min_quality="medium")
            if rows:
                bars[code] = list(rows)
        except Exception as exc:
            log("行业数据跳过 %s: %s" % (code, exc))
    rankings = rank_industries(bars, industry_map, min_members=1) if bars else []
    return rankings, industry_map


def apply_industry_context(stock, rankings, industry_map):
    code = stock.get("股票代码")
    bonus = stock_industry_bonus(code, rankings, industry_map) if code else 0.0
    industry = industry_map.get(code, stock.get("行业", "未知行业"))
    row = next((x for x in rankings if x.get("industry") == industry), None)
    if row:
        stock["行业"] = industry
        stock["行业排名"] = row.get("rank")
        stock["行业强度百分位"] = row.get("percentile")
        stock["综合评分"] = round(max(0, min(10, (stock.get("综合评分") or 0) + bonus / 10.0)), 1)
        stock["核心逻辑"] = (stock.get("核心逻辑") or "") + "；行业强度%s%%(排名%d)，评分调整%+.1f" % (row.get("percentile"), row.get("rank"), bonus / 10.0)
    else:
        stock["行业"] = industry
    return stock
