# -*- coding: utf-8 -*-
"""守卫：市场级风险门（`risk/market_risk_gate.py`）。

## 为什么需要

该模块是 2026-09-30 六人专家圆桌审查的落地产物 —— **三个席位各自独立**提出
「系统缺市场级状态门」。这类指标最容易出的问题是：

1. **前视**：用当日数据算当日分位（自我参照），或跌停判定用了未来价格；
2. **静默失效**：`limit_ratio` 缺失时判不出跌停却**不报错**（与项目此前的
   「换手率分项静默失效」同类）；
3. **缺失被当 0**：无状态的日期若返回「不干预」以外的值，会凭空改变回测。

本文件把这三点锁住。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from risk.market_risk_gate import (  # noqa: E402
    ELEVATED_LIMIT_DOWN_RATIO,
    EXTREME_LIMIT_DOWN_RATIO,
    build_market_gate,
    compute_market_risk,
)


def _bar(date, close, amount=1e8, limit_ratio="0.10"):
    b = {"date": date, "close": close, "amount": amount}
    if limit_ratio is not None:
        b["limit_ratio"] = limit_ratio
    return b


def _mk(codes_n: int, days: list, close_of=None, lr="0.10"):
    """构造 ``codes_n`` 只股票、每只都走 ``days`` 的合成面板。"""
    out = {}
    for i in range(codes_n):
        out[f"{i:06d}"] = [
            _bar(d, (close_of(d) if close_of else 10.0), limit_ratio=lr) for d in days
        ]
    return out


# ---------------------------------------------------------------------------
# 跌停判定
# ---------------------------------------------------------------------------

def test_limit_down_detected_at_exact_limit_price():
    """收盘恰为跌停价（round(prev×(1−lr),2)）→ 判跌停。"""
    bars = {"000001": [_bar("2024-01-02", 10.0), _bar("2024-01-03", 9.0)]}
    r = compute_market_risk(bars, min_cross_section=1)
    assert r["2024-01-03"]["limit_down_count"] == 1


def test_non_limit_down_not_counted():
    """跌 5% 但未触及跌停价（10%）→ 不计跌停。"""
    bars = {"000001": [_bar("2024-01-02", 10.0), _bar("2024-01-03", 9.5)]}
    r = compute_market_risk(bars, min_cross_section=1)
    assert r["2024-01-03"]["limit_down_count"] == 0


def test_missing_limit_ratio_does_not_fake_limit_down():
    """⚠️ `limit_ratio` 缺失时**不得**判跌停（否则会凭空造出风险信号）。"""
    bars = {"000001": [_bar("2024-01-02", 10.0, limit_ratio=None),
                       _bar("2024-01-03", 1.0, limit_ratio=None)]}
    r = compute_market_risk(bars, min_cross_section=1)
    assert r["2024-01-03"]["limit_down_count"] == 0


def test_st_limit_ratio_5pct_is_respected():
    """ST 的 5% 档：跌 5% 即跌停（用逐日 `limit_ratio` 而非硬编码 10%）。"""
    bars = {"000001": [_bar("2024-01-02", 10.0, limit_ratio="0.05"),
                       _bar("2024-01-03", 9.5, limit_ratio="0.05")]}
    r = compute_market_risk(bars, min_cross_section=1)
    assert r["2024-01-03"]["limit_down_count"] == 1


def test_price_gap_breaks_prev_close():
    """行情缺口（close 缺失）后不得用隔日价判跌停。"""
    bars = {"000001": [_bar("2024-01-02", 10.0), _bar("2024-01-03", 10.0),
                       {"date": "2024-01-04", "close": None, "amount": 1e8,
                        "limit_ratio": "0.10"},
                       _bar("2024-01-05", 9.0)]}
    r = compute_market_risk(bars, min_cross_section=1)
    assert r["2024-01-05"]["limit_down_count"] == 0, "缺口后应断开前收，不得判跌停"


# ---------------------------------------------------------------------------
# 状态阈值
# ---------------------------------------------------------------------------

def test_extreme_state_at_threshold():
    days = ["2024-01-02", "2024-01-03"]
    # 100 只中 25 只跌停 = 25% ≥ 20%
    bars = {}
    for i in range(100):
        bars[f"{i:06d}"] = [_bar(days[0], 10.0),
                            _bar(days[1], 9.0 if i < 25 else 10.0)]
    r = compute_market_risk(bars, min_cross_section=50)
    assert r[days[1]]["limit_down_ratio"] == 0.25
    assert r[days[1]]["state"] == "EXTREME"


def test_elevated_state_between_thresholds():
    days = ["2024-01-02", "2024-01-03"]
    bars = {}
    for i in range(100):
        bars[f"{i:06d}"] = [_bar(days[0], 10.0),
                            _bar(days[1], 9.0 if i < 10 else 10.0)]
    r = compute_market_risk(bars, min_cross_section=50)
    assert r[days[1]]["state"] == "ELEVATED"
    assert ELEVATED_LIMIT_DOWN_RATIO <= 0.10 < EXTREME_LIMIT_DOWN_RATIO


def test_normal_state_when_few_limit_downs():
    days = ["2024-01-02", "2024-01-03"]
    bars = {}
    for i in range(100):
        bars[f"{i:06d}"] = [_bar(days[0], 10.0),
                            _bar(days[1], 9.0 if i < 2 else 10.0)]
    r = compute_market_risk(bars, min_cross_section=50)
    assert r[days[1]]["state"] == "NORMAL"


def test_thin_cross_section_yields_no_state():
    """截面过薄的日期 → 状态为 None（不得硬判）。"""
    bars = {"000001": [_bar("2024-01-02", 10.0), _bar("2024-01-03", 9.0)]}
    r = compute_market_risk(bars, min_cross_section=50)
    assert r["2024-01-03"]["state"] is None


# ---------------------------------------------------------------------------
# 前视检查
# ---------------------------------------------------------------------------

def test_amount_percentile_excludes_current_day():
    """⚠️ 前视守卫：成交额分位必须用**不含当日**的历史窗。

    构造 3 天成交额 = 1e8 / 2e8 / 1.5e8（第 3 天**回落**），使两种口径可分：

    * **不含当日**（正确）：历史窗 = [1e8, 2e8]，1.5e8 在其中的分位 = 1/2 = **0.5**
    * 含当日（错误）：窗 = [1e8, 2e8, 1.5e8]，分位 = 1/3 ≈ 0.333

    同时验证首日：历史窗为空 → 必须为 ``None``，**不得**用当日自己算出 0.0/1.0。
    """
    bars = {}
    for i in range(60):
        bars[f"{i:06d}"] = [
            _bar("2024-01-02", 10.0, amount=1e8),
            _bar("2024-01-03", 10.0, amount=2e8),
            _bar("2024-01-04", 10.0, amount=1.5e8),
        ]
    r = compute_market_risk(bars, min_cross_section=50)
    assert r["2024-01-02"]["amount_percentile"] is None, "首日无历史窗，不得自我参照"
    assert r["2024-01-03"]["amount_percentile"] == 1.0, "历史窗只有 1e8，2e8 高于它"
    assert r["2024-01-04"]["amount_percentile"] == 0.5, (
        "不含当日的历史窗 = [1e8, 2e8] → 分位 1/2；若为 0.333 说明把当日算进了窗（前视）"
    )


# ---------------------------------------------------------------------------
# gate 行为
# ---------------------------------------------------------------------------

def test_gate_blocks_extreme_and_scales_elevated():
    risk = {"2024-02-05": {"state": "EXTREME"},
            "2024-10-09": {"state": "ELEVATED"},
            "2024-01-02": {"state": "NORMAL"}}
    g = build_market_gate(risk)
    assert g("2024-02-05") == 0.0
    assert g("2024-10-09") == 0.5
    assert g("2024-01-02") == 1.0


def test_gate_unknown_date_does_not_intervene():
    """⚠️ 缺失即不干预 —— 未知日期必须返回 1.0，不得猜测。"""
    g = build_market_gate({"2024-02-05": {"state": "EXTREME"}})
    assert g("1999-01-01") == 1.0
    assert g("") == 1.0


def test_gate_none_state_does_not_intervene():
    g = build_market_gate({"2024-01-02": {"state": None}})
    assert g("2024-01-02") == 1.0


def test_empty_input_is_safe():
    assert compute_market_risk({}) == {}


# ---------------------------------------------------------------------------
# 冷却期（2026-09-30 实测教训）
#
# 首版 gate 只按「当日状态」缩放，而 position_scaler 只在当日生效、
# 策略每 20 日才调仓一次 → EXTREME 日落在调仓日的概率仅约 1/20。
# 实测 A/B：窗口内含 2 个 EXTREME 日，但 Δ = +0.00pp、交易数与回撤完全相同 ——
# **门根本没被触发**。故加 cooldown_days，并在此锁住其语义。
# ---------------------------------------------------------------------------

_DAYS = [f"2024-01-{i:02d}" for i in range(1, 21)]


def test_cooldown_zero_is_previous_behaviour():
    """cooldown_days=0 → 行为与首版一致（只当日生效）。"""
    risk = {"2024-01-05": {"state": "EXTREME"}}
    g = build_market_gate(risk, cooldown_days=0)
    assert g("2024-01-05") == 0.0
    assert g("2024-01-06") == 1.0, "无冷却时次日应恢复"


def test_cooldown_blocks_subsequent_trading_days():
    """⚠️ 核心守卫：冷却期内的交易日必须同样被阻断。"""
    risk = {"2024-01-05": {"state": "EXTREME"}}
    g = build_market_gate(risk, cooldown_days=3, trading_days=_DAYS)
    assert g("2024-01-05") == 0.0
    assert g("2024-01-06") == 0.0
    assert g("2024-01-08") == 0.0, "冷却第 3 个交易日仍应阻断"
    assert g("2024-01-09") == 1.0, "冷却结束后应恢复"


def test_cooldown_covers_non_rebalance_days():
    """冷却的实质：把「只有 1/20 概率被命中」变成「一定被命中」。

    构造一个 EXTREME 日不在调仓日上、但其后调仓日落在冷却窗内的场景。
    """
    risk = {"2024-01-05": {"state": "EXTREME"}}
    # 调仓日 = 2024-01-10（在 10 日冷却窗内）
    g = build_market_gate(risk, cooldown_days=10, trading_days=_DAYS)
    assert g("2024-01-10") == 0.0, "调仓日落在冷却窗内 → 必须被阻断"


def test_cooldown_requires_trading_days():
    """未传 trading_days 时冷却不生效（不得凭空猜测交易日序列）。"""
    risk = {"2024-01-05": {"state": "EXTREME"}}
    g = build_market_gate(risk, cooldown_days=10)
    assert g("2024-01-06") == 1.0


def test_cooldown_does_not_leak_beyond_series():
    """冷却窗不得越出交易日序列尾部（防索引越界与凭空延伸）。"""
    risk = {"2024-01-20": {"state": "EXTREME"}}
    g = build_market_gate(risk, cooldown_days=10, trading_days=_DAYS)
    assert g("2024-01-20") == 0.0
    assert g("2024-02-15") == 1.0, "序列外日期不得被判为冷却中"


# ---------------------------------------------------------------------------
# 过滤器形态（candidate_filter）
#
# 用户要求「转成过滤器」。⚠️ 关键：filter 与 gate（position_scaler）**语义不同**：
#   gate   → 新开仓预算=0 → 当日**不建仓**（空仓）
#   filter → 该股不进候选池 → 系统**顺位选下一只**（换股）
# 只有「排除全池」时两者才等价。本组测试把差异锁住，防日后误用。
# ---------------------------------------------------------------------------

from risk.market_risk_gate import build_market_filter  # noqa: E402


def test_filter_excludes_blocked_day_for_all_codes():
    """全池阻断：任何 code 在阻断日都返回 False。"""
    risk = {"2024-02-05": {"state": "EXTREME"}}
    f = build_market_filter(risk)
    assert f("000001", [], "2024-02-05") is False
    assert f("600519", [], "2024-02-05") is False


def test_filter_allows_normal_day():
    risk = {"2024-02-05": {"state": "EXTREME"}, "2024-01-02": {"state": "NORMAL"}}
    f = build_market_filter(risk)
    assert f("000001", [], "2024-01-02") is True


def test_filter_unknown_day_does_not_block():
    """⚠️ 缺失即不干预 —— 未知日期必须放行。"""
    f = build_market_filter({"2024-02-05": {"state": "EXTREME"}})
    assert f("000001", [], "1999-01-01") is True


def test_filter_does_not_distinguish_codes():
    """市场级 filter 是**全池**判定 —— 不得因个股不同而给出不同结果。"""
    risk = {"2024-02-05": {"state": "EXTREME"}}
    f = build_market_filter(risk)
    assert f("000001", [{"close": 1}], "2024-02-05") == f("600519", [], "2024-02-05")


def test_filter_cooldown_blocks_subsequent_days():
    risk = {"2024-01-05": {"state": "EXTREME"}}
    f = build_market_filter(risk, cooldown_days=3, trading_days=_DAYS)
    assert f("000001", [], "2024-01-05") is False
    assert f("000001", [], "2024-01-08") is False
    assert f("000001", [], "2024-01-09") is True


def test_filter_and_gate_agree_on_blocked_day():
    """阻断日：filter 放行集合为空 ≡ gate 预算为 0（两者都导致当日不建仓）。"""
    risk = {"2024-02-05": {"state": "EXTREME"}}
    f = build_market_filter(risk)
    g = build_market_gate(risk)
    assert f("000001", [], "2024-02-05") is False
    assert g("2024-02-05") == 0.0


def test_filter_is_side_effect_free():
    """⚠️ 回测热路径逐股逐日调用 → filter 内**不得有 I/O**。多次调用结果必须一致。"""
    risk = {"2024-02-05": {"state": "EXTREME"}}
    f = build_market_filter(risk)
    first = f("000001", [], "2024-02-05")
    for _ in range(50):
        assert f("000001", [], "2024-02-05") == first
