# -*- coding: utf-8 -*-
"""守卫：`market_regime` 的离线路径与单指数降级。

## 为什么需要

2026-09-30 专家圆桌审查中，**信号派首席**点名该模块的离线阻塞：

> 「`market_regime.py` 依赖 `fetch_kline`（实时），**离线跑不了**」

修复时又发现一个**新的静默失效**：离线数据集 `benchmark.csv` **只有沪深300 一个指数**，
而原规则要求「≥2 个指数同时多头/空头」→ `bulls >= 2` **永远为假** →
**模块在离线场景下永远返回 RANGE，且不报错**。

这类「不报错的失效」是本项目反复出现的缺陷类型（参见 `_norm_date` 的 NaT、
`load_certified_csv` 丢 `turnover`）。故本文件锁住：
① 离线可跑；② 降级必须**显式标注**而非静默。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market_regime import MIN_BARS, get_market_regime  # noqa: E402


def _rising(n: int, start: float = 10.0, step: float = 0.1):
    return [{"date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
             "close": start + i * step} for i in range(n)]


def _falling(n: int, start: float = 100.0, step: float = 0.5):
    return [{"date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
             "close": start - i * step} for i in range(n)]


# ---------------------------------------------------------------------------
# 离线路径
# ---------------------------------------------------------------------------

def test_offline_mode_does_not_call_realtime():
    """传入 bars 时**不得**触碰实时接口（离线环境无 data_fetcher 也应可跑）。"""
    bars = {"sh000300": _rising(MIN_BARS + 30)}
    r = get_market_regime(bars)
    assert r["regime"] in ("STRONG", "RANGE", "WEAK")
    assert r["available_indices"] >= 1


def test_offline_single_index_marks_degraded():
    """⚠️ 核心守卫：只有 1 个指数时必须显式标注 ``degraded=True``。"""
    bars = {"sh000300": _rising(MIN_BARS + 30)}
    r = get_market_regime(bars)
    assert r["available_indices"] == 1
    assert r["degraded"] is True, "单指数降级必须显式标注，否则调用方无从得知"


def test_offline_two_indices_not_degraded():
    """≥2 个指数可用时走原多数规则，不标注降级。"""
    bars = {"sh000300": _rising(MIN_BARS + 30),
            "sh000001": _rising(MIN_BARS + 30)}
    r = get_market_regime(bars)
    assert r["available_indices"] == 2
    assert r["degraded"] is False


def test_offline_insufficient_history_not_available():
    """K 线不足 MIN_BARS → 该指数判不可用（不得硬算均线）。"""
    bars = {"sh000300": _rising(10)}
    r = get_market_regime(bars)
    assert r["regime"] == "UNKNOWN"
    assert all(not d.get("available") for d in r["details"])
    assert all(d.get("reason") == "insufficient_history" for d in r["details"])


def test_offline_empty_bars_is_unknown_not_crash():
    r = get_market_regime({})
    assert r["regime"] == "UNKNOWN"
    assert r["available_indices"] == 0


# ---------------------------------------------------------------------------
# 单指数规则方向
# ---------------------------------------------------------------------------

def test_single_index_bull_with_positive_ret_is_strong():
    """单指数：close>ma20>ma60 且 20 日涨幅 >2% → STRONG。"""
    bars = {"sh000300": _rising(MIN_BARS + 30, start=10.0, step=0.2)}
    r = get_market_regime(bars)
    assert r["regime"] == "STRONG"


def test_single_index_bear_with_negative_ret_is_weak():
    bars = {"sh000300": _falling(MIN_BARS + 30, start=200.0, step=0.5)}
    r = get_market_regime(bars)
    assert r["regime"] == "WEAK"


def test_degraded_note_mentions_weakness():
    """降级时 note 必须提示稳健性弱于三指数多数规则。"""
    bars = {"sh000300": _rising(MIN_BARS + 30, start=10.0, step=0.2)}
    r = get_market_regime(bars)
    assert "单指数降级" in r["note"]
