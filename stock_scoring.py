# -*- coding: utf-8 -*-
"""每日选股 · 透明规则打分。

由 daily_stock_pick.py 拆分而来（1.0）。纯打分逻辑：输入行情 + K 线，
输出结构化评分记录；**不做任何落盘、推送或状态修改**，便于单独测试与复用。

打分维度：当日涨跌幅 / 换手率 / 近5日趋势与突破 / 估值风险提示 /
Cycle of Price Action 阶段 / 市场环境统一风控。
"""
from datetime import datetime

from data_fetcher import fetch_kline, fetch_quote
from risk.a_share_risk import regime_adjustment
from cycle_price_action import _STAGE_RISK, _STAGE_SCORE, locate_cycle_phase


def _ema(values, period):
    """指数移动平均（从序列首值起迭代，纯标准库）。"""
    if not values:
        return None
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def score_stock(item, market=None):
    """单股透明规则打分，返回结构化记录。"""
    code = item["code"]
    q = fetch_quote(code)
    # 拉取 70 根日K（前复权）：既算近5日趋势，也用于 Cycle of Price Action 阶段定位
    k = fetch_kline(code, limit=70, min_quality="medium")
    if not k:
        return {"股票代码": code, "股票名称": item.get("name") or code, "综合评分": 0.0, "风险等级": 9.0, "建议": "数据不足", "评分逻辑": ["K线数据质量不足，拒绝评分"], "数据质量": "LOW"}

    logic = []
    score = 50.0
    risk = 5.0

    price = q.get("price")
    pct = q.get("change_pct")
    name = q.get("name") or item.get("name") or code
    turnover = q.get("turnover")
    pe = q.get("pe")
    pb = q.get("pb")

    # 1) 当日涨跌幅
    if pct is not None:
        if 0 < pct <= 3:
            score += pct * 2
            logic.append("当日温和上涨 %.2f%%" % pct)
        elif pct > 3:
            score += min(6 + (pct - 3) * 0.5, 10)
            risk = min(risk + 1, 9)
            logic.append("当日涨幅 %.2f%%，趋势强但追高风险上升" % pct)
        else:
            score -= min(abs(pct) * 2, 20)
            logic.append("当日下跌 %.2f%%" % pct)
        if pct >= 5:
            risk = min(risk + 2, 9)
        elif pct <= -5:
            risk = min(risk + 3, 9)
    else:
        logic.append("无实时涨跌幅")

    # 2) 换手率
    if turnover is not None:
        if 1.0 <= turnover <= 8.0:
            score += 10
            logic.append("换手 %.2f%% 活跃适中" % turnover)
        elif turnover > 8.0:
            score += 5
            risk = min(risk + 1, 9)
            logic.append("换手 %.2f%% 偏热" % turnover)
        else:
            score -= 5
            logic.append("换手 %.2f%% 偏冷清" % turnover)

    # 3) 近 5 日趋势（用 K 线收盘）
    closes = [r["close"] for r in k if r.get("close") is not None]
    if len(closes) >= 5:
        c0 = closes[-6] if len(closes) >= 6 else closes[0]
        c5 = closes[-1]
        trend = (c5 - c0) / c0 * 100 if c0 else 0.0
        if 5 < trend <= 12:
            score += 10
            logic.append("近5日累计涨 %.2f%% 趋势向上" % trend)
        elif trend > 12:
            score += 4
            risk = min(risk + 2, 9)
            logic.append("近5日累计涨 %.2f%%，短期扩张过快" % trend)
        elif trend > 0:
            score += 8
            logic.append("近5日累计涨 %.2f%%" % trend)
        elif trend < -5:
            score -= 15
            risk = min(risk + 2, 9)
            logic.append("近5日累计跌 %.2f%% 趋势偏弱" % trend)
        else:
            score -= 5
            logic.append("近5日累计 %.2f%% 震荡" % trend)
        # 突破判断：最新收盘价高于近5日最高（除当日外）
        highs = [r["high"] for r in k[-6:-1] if r.get("high") is not None]
        if highs and c5 >= max(highs):
            score += 10
            logic.append("收盘站上近5日高点（突破信号）")

    # 4) 估值风险提示（不计分，仅标注）
    # 注：此前该处把提示写入局部变量 pe_note 后从未使用，估算注记被静默丢弃。
    # 现直接写入 logic（→ 输出的「核心逻辑」），恢复注释所述的"标注"语义。
    if pe is not None:
        if pe < 0:
            logic.append("PE为负（亏损）")
        elif pe > 200:
            logic.append("PE %.1f 极高" % pe)
            risk = min(risk + 1, 9)
        elif pe > 60:
            logic.append("PE %.1f 偏高" % pe)
        else:
            logic.append("PE %.1f" % pe)
    if pb is not None and pb > 15:
        risk = min(risk + 1, 9)

    # 5) Cycle of Price Action 阶段定位（Oliver Kell 六阶段）
    highs_all = [r.get("high") for r in k if r.get("high") is not None]
    lows_all = [r.get("low") for r in k if r.get("low") is not None]
    if len(closes) >= 30 and len(highs_all) >= 30 and len(lows_all) >= 30:
        stage = locate_cycle_phase(closes, highs_all, lows_all)
        if stage:
            sid, sname, sdesc = stage
            score += _STAGE_SCORE.get(sid, 0)
            risk += _STAGE_RISK.get(sid, 0)
            logic.append("周期阶段：%s（%s）" % (sname, sdesc))
    elif len(closes) < 30:
        logic.append("周期阶段：数据不足（仅%d根K线，未判阶段）" % len(closes))

    # 6) 市场环境统一风控：避免个股强势掩盖系统性风险
    regime = (market or {}).get("regime", "UNKNOWN")
    score, risk, regime_note = regime_adjustment(regime, score, risk)
    logic.append("市场环境[%s]：%s" % (regime, regime_note))

    score = round(max(0.0, min(100.0, score)), 1)
    risk = round(max(1.0, min(9.0, risk)), 1)
    comp = round(score / 10.0, 1)

    if comp >= 7.5:
        advice = "重点关注"
    elif comp >= 6.0:
        advice = "关注"
    else:
        advice = "观望"

    return {
        "股票代码": code,
        "股票名称": name,
        "所属板块": item.get("note", ""),
        "行业": item.get("industry") or (item.get("note", "") or "未知行业").split("·")[0],
        "当前价格": price,
        "涨跌幅": pct,
        "PE(TTM)": pe,
        "PB": pb,
        "换手率%": turnover,
        "综合评分": comp,
        "风险等级": risk,
        "数据质量": getattr(k, "data_quality", "unknown"),
        "K线来源": getattr(k, "source", "unknown"),
        "投资建议": advice,
        "核心逻辑": "；".join(logic) if logic else "数据不足，仅作形态参考",
        "分析日期": int(datetime.now().timestamp() * 1000),
        "报告链接": "",
        "深析决策": "",
    }
