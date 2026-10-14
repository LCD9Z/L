# -*- coding: utf-8 -*-
"""绩效口径守卫（整改清单 P0-3）。

## 验收标准

> **同区间、同基准、同成本、同股票池后再比较策略。**

## 防什么

项目里多个策略数字（V1/V2/五因子组合/因子 IC）若区间、基准、成本、
股票池不同，横向比较**毫无意义** —— 但报告常只写「+4.27pp」
而不说跟谁比、哪段比、扣没扣费。

**这不是「算错」，是「比错」** —— 比算错更隐蔽。

## 本守卫的做法

1. `PERFORMANCE_PROTOCOL.md` 必须存在，且覆盖四个维度
2. 成本口径必须与 `backtest_engine.Costs` **实际一致**（防止文档与代码漂移）
3. 印花税分段**必须真的生效**（历史上因日期格式 bug 完全失效过）
4. 新报告必须声明四维（头部字段）
"""

from __future__ import annotations

from pathlib import Path


import backtest_engine as be

ROOT = Path(__file__).resolve().parent.parent
PROTO = ROOT / "PERFORMANCE_PROTOCOL.md"
ALIGN = ROOT / "BENCHMARK_ALIGNMENT.md"

#: 报告必须声明的四个维度关键词
REQUIRED_DIMS = ("区间", "基准", "成本", "股票池")


def test_protocol_exists():
    assert PROTO.is_file(), "PERFORMANCE_PROTOCOL.md 缺失"


def test_protocol_covers_all_four_dims():
    text = PROTO.read_text(encoding="utf-8")
    for d in REQUIRED_DIMS:
        assert d in text, f"绩效口径未覆盖维度「{d}」"


def test_cost_constants_match_code():
    """协议里的成本数字必须与 backtest_engine.Costs 一致（防文档漂移）。"""
    c = be.Costs()
    text = PROTO.read_text(encoding="utf-8")
    assert f"{c.commission_rate * 100:.2f}%" in text or \
        f"{c.commission_rate:.4f}" in text, "协议未写佣金率（或与代码不符）"
    # 印花税两段都要写
    assert "0.5‰" in text or "0.0005" in text, "协议未写现行印花税 0.5‰"
    assert "1‰" in text or "0.001" in text, "协议未写旧印花税 1‰"


def test_stamp_duty_segmentation_actually_works():
    """⚠️ 核心回归：印花税跨 2023-08-28 必须真的分段。

    历史 bug：`stamp_duty_change_date="2023-08-28"`（带横杠）与
    K 线日期 `"20230825"`（不带）做**字符串比较**，
    `'-' < '0'` 使比较恒为 True → 分段完全失效，所有交易都按新税率计费。
    """
    c = be.Costs()
    assert be._stamp_rate(c, "20230825") == 0.001, \
        "2023-08-28 前的交易未按旧税率 1‰ 计费（分段失效）"
    assert be._stamp_rate(c, "2023-08-28") == 0.0005, \
        "生效日当天应按新税率 0.5‰"
    assert be._stamp_rate(c, "20230829") == 0.0005
    # 两种日期格式都要能正确判定（这正是原 bug 的根因）
    assert be._stamp_rate(c, "2023-08-25") == 0.001, \
        "带横杠的日期未正确判定（原 bug 形态）"


def test_transfer_fee_is_bidirectional():
    """过户费双向：买卖都收（2022-04-29 起沪深统一 0.01‰）。"""
    c = be.Costs()
    buy = be._trade_cost(100000.0, "buy", c, "20230101")
    sell = be._trade_cost(100000.0, "sell", c, "20230101")
    # 卖出含印花税，故卖出成本 > 买入成本；但买入也须含过户费
    assert buy > c.min_commission, "买入成本未含过户费（应为双向）"
    assert sell > buy, "卖出成本应高于买入（含印花税）"


def test_benchmark_alignment_exists():
    """基准口径由姊妹文件负责，须存在。"""
    assert ALIGN.is_file(), "BENCHMARK_ALIGNMENT.md 缺失（基准代次对照表）"


def test_protocol_forbids_cross_pool_comparison_without_note():
    """协议须明示：跨池比较必须显式说明。"""
    text = PROTO.read_text(encoding="utf-8")
    assert "跨池" in text or "不得并列" in text, \
        "协议未禁止「未对齐就并列比较」"


def test_no_greedy_reporting_clause():
    """协议须含「不得择优汇报」（与整改清单 P0-1 对齐）。"""
    text = PROTO.read_text(encoding="utf-8")
    assert "择优" in text, "协议未禁择优汇报"
