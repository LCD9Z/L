# -*- coding: utf-8 -*-
"""纯历史 Cycle of Price Action 阶段识别，无网络/状态依赖。"""
# Cycle of Price Action 六阶段（Oliver Kell）：1反转扩展 2楔形突破 3均线回穿 4底部+突破 5衰竭扩展 6楔形下跌
_STAGE_SCORE = {1: 4, 2: 8, 3: 6, 4: 3, 5: -8, 6: -10}
_STAGE_RISK = {1: -1, 2: 0, 3: 0, 4: 1, 5: 2, 6: 2}


def _ema(values, period):
    if not values:
        return None
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def locate_cycle_phase(closes, highs, lows):
    """基于 Cycle of Price Action 定位当前阶段。

    输入为按时间正序的收盘/最高/最低序列（含当日），长度需 >= 30，否则返回 None。
    规则透明：EMA10/EMA20、距均线扩展度、近20日高点突破、更高低点、波动收窄。
    优先级：衰竭扩展 → 楔形突破 → 均线回穿 → 底部+突破 → 反转扩展 → 楔形下跌。
    """
    n = len(closes)
    if n < 30:
        return None
    close = closes[-1]
    ema10 = _ema(closes[-20:], 10)
    ema20 = _ema(closes[-30:], 20)
    if not ema10 or not ema20 or ema10 == 0 or ema20 == 0:
        return None
    ext10 = (close - ema10) / ema10 * 100.0
    ext20 = (close - ema20) / ema20 * 100.0

    hh20 = max(highs[-21:-1]) if len(highs) > 21 else max(highs[:-1])
    ll10 = min(lows[-11:-1]) if len(lows) > 11 else min(lows[:-1])
    ll_prev = min(lows[-21:-11]) if len(lows) > 21 else ll10

    uptrend = ema10 > ema20 and close > ema20
    breakout = close >= hh20 and hh20 > 0
    higher_low = ll10 > ll_prev

    c0 = closes[-6] if n >= 6 else closes[0]
    chg5 = (close - c0) / c0 * 100.0 if c0 else 0.0

    rng_recent = max(highs[-5:]) - min(lows[-5:])
    rng_prior = max(highs[-20:-5]) - min(lows[-20:-5])
    contraction = rng_prior > 0 and rng_recent / rng_prior < 0.75

    if ext10 > 12.0:
        return (5, "衰竭扩展", "距10日线+%.1f%%、近5日涨%.1f%%，高潮顶止盈区" % (ext10, chg5))
    if breakout and uptrend:
        return (2, "楔形突破", "站上10/20日线并创近20日新高，最佳做多入场区")
    if uptrend and -2.5 <= ext10 <= 2.5:
        return (3, "均线回穿", "多头结构中回踩10日线附近(偏离%.1f%%)，低风险加仓点" % ext10)
    if uptrend and contraction:
        return (4, "底部+突破", "均线上方波动收窄整理，等突破延续(偏晚)")
    if not uptrend and higher_low and ext20 < -5.0:
        return (1, "反转扩展", "低位更高低点(近10日低点%.2f>前期%.2f)，底部反转初期" % (ll10, ll_prev))
    if not uptrend:
        return (6, "楔形下跌", "跌破20日线、空头结构，回避")
    return (4, "底部+突破", "多头结构整理延续，偏晚区")
