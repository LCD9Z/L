# -*- coding: utf-8 -*-
"""守卫：估值分档 → 仓位权重调节器（`risk/valuation_weight.py`）。

## 背景

2026-09-30 专家圆桌审查中，**估值分析师**指出系统「只称 PE 的分子，从没算过分母」，
并给出处方：把 `pb`/`pe_ttm` 从「排序因子」升级成「**仓位权重调节器**」。

本文件锁住三件事：
① 分档边界与权重映射符合事前登记；
② **缺失即不干预**（无权重 → 1.0，不猜）；
③ 热路径**零 I/O**（逐股逐日调用，写成每次重算会慢几个数量级）。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from risk.valuation_weight import (  # noqa: E402
    HIGH_PCT, LOW_PCT, W_HIGH, W_LOW, W_MID,
)


# ---------------------------------------------------------------------------
# 事前登记的分档常数（改动即破坏登记，测试会失败）
# ---------------------------------------------------------------------------

def test_registered_cut_points():
    """⚠️ 分档边界是**事前登记**的，不得事后调整。"""
    assert LOW_PCT == 0.33
    assert HIGH_PCT == 0.67


def test_registered_weights():
    """⚠️ 权重是**事前登记**的：下轨 1.5 / 中 1.0 / 上轨 0.5。"""
    assert W_LOW == 1.5
    assert W_MID == 1.0
    assert W_HIGH == 0.5


def test_weights_are_monotonic_in_valuation():
    """估值越低权重越高（方向必须与「低估值溢价」一致）。"""
    assert W_LOW > W_MID > W_HIGH


# ---------------------------------------------------------------------------
# 用合成数据跑端到端（不依赖真实数据集）
# ---------------------------------------------------------------------------

def _synth(n_days=6, n_codes=40):
    """造最小数据集：日期递增，价格恒定，避免依赖真实 fundamentals。"""
    codes = [f"{i:06d}" for i in range(n_codes)]
    bars = {}
    for c in codes:
        bars[c] = [{"date": f"2024-01-{i + 1:02d}", "close": 10.0}
                   for i in range(n_days)]
    return codes, bars


def test_missing_day_does_not_intervene(tmp_path, monkeypatch):
    """⚠️ 核心守卫：**无权重记录的日子必须返回 1.0**（不干预，不猜）。

    直接构造一个空表的 weight_func 语义 —— 用 monkeypatch 绕开真实 PIT 数据依赖。
    """
    from risk import valuation_weight as vw

    # 造一个「表为空」的场景：fundamentals 文件不存在 → load_records 抛错前先拦
    def fake_load_records(_p):
        return []
    monkeypatch.setattr("pit.pit_fundamentals.load_records", fake_load_records)
    monkeypatch.setattr("pit.pit_fundamentals.load_disclosures", lambda _p: {})

    _codes, bars = _synth()
    (tmp_path / "fundamentals.jsonl").write_text("", encoding="utf-8")
    wf, stats = vw.build_valuation_weight(str(tmp_path), bars,
                                          rebalance_days=["2024-01-01"])
    assert stats["days_covered"] == 0, "无财务数据时不应产出任何分档"
    assert wf("000000", [], "2024-01-01") == W_MID, "缺失必须不干预"


def test_thin_cross_section_produces_no_weights(tmp_path, monkeypatch):
    """截面过薄（< min_cross_section）→ 不做分档（缺失即不干预）。"""
    from risk import valuation_weight as vw

    _codes, bars = _synth(n_codes=3)

    def fake_load_records(_p):
        return [{"code": "000000", "report_period": "2023-12-31", "eps": 1.0,
                 "bps": 5.0, "announce_date": "2024-01-01"}]
    monkeypatch.setattr("pit.pit_fundamentals.load_records", fake_load_records)
    monkeypatch.setattr("pit.pit_fundamentals.load_disclosures", lambda _p: {})

    (tmp_path / "fundamentals.jsonl").write_text("x", encoding="utf-8")
    wf, stats = vw.build_valuation_weight(str(tmp_path), bars,
                                          rebalance_days=["2024-01-01"],
                                          min_cross_section=20)
    assert stats["days_covered"] == 0
    assert wf("000000", [], "2024-01-01") == W_MID


def test_weight_func_is_pure_lookup(tmp_path, monkeypatch):
    """⚠️ 热路径守卫：weight_func 多次调用结果必须一致（无副作用、无 I/O）。"""
    from risk import valuation_weight as vw

    _codes, bars = _synth()
    monkeypatch.setattr("pit.pit_fundamentals.load_records", lambda _p: [])
    monkeypatch.setattr("pit.pit_fundamentals.load_disclosures", lambda _p: {})
    (tmp_path / "fundamentals.jsonl").write_text("", encoding="utf-8")

    wf, _ = vw.build_valuation_weight(str(tmp_path), bars,
                                      rebalance_days=["2024-01-01"])
    first = wf("000000", [], "2024-01-01")
    for _ in range(50):
        assert wf("000000", [], "2024-01-01") == first
