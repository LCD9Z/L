# -*- coding: utf-8 -*-
"""交易成本与回测收益率口径测试。

背景：tracking 曾把「每股价格」当作计费名义金额，导致 5 元最低佣金在高价股上
被放大到 0.33%（正确值约 0.03%），每笔收益率偏差约 0.6 个百分点 —— 足以让任何
策略在统计上"看起来不赚钱"。同时 `--gross` 开关因 `costs or TrackingCosts()`
被静默覆盖而失效。

本测试锁定：成本率与股价无关、毛/净口径可切换、最低佣金不主导成本。
"""
import sqlite3

import pytest

import tracking
from tracking import TrackingCosts, net_return_pct


# ---------------------------------------------------------------------------
# 成本率
# ---------------------------------------------------------------------------

def test_round_trip_cost_pct_matches_hand_calculation():
    """往返成本 = 双边佣金 + 卖出印花税 + 双边过户费，占基准仓位比例。"""
    c = TrackingCosts(position_notional=100_000.0)
    # 佣金 max(5, 100000*0.0003) = 30（双边 60）；印花税 100000*0.0005 = 50；
    # 过户费 100000*0.00001 = 1（双边 2，中国结算 2022-04-29 起 0.01‰ 沪深两市）
    expected = (30 + 30 + 50 + 2) / 100_000.0
    assert c.round_trip_cost_pct() == pytest.approx(expected)
    assert c.round_trip_cost_pct() == pytest.approx(0.00112)


def test_cost_is_independent_of_share_price():
    """核心性质：成本率不得随股价变化（这是原缺陷的根因）。"""
    c = TrackingCosts(position_notional=100_000.0)
    # 同一成本模型下，10 元股与 1500 元股的净收益率应完全一致
    low = net_return_pct(10.0, 10.1, c)          # +1.0% 毛
    high = net_return_pct(1500.0, 1515.0, c)     # +1.0% 毛
    assert low == high, f"成本随股价变化: 10元股 {low}% vs 1500元股 {high}%"


def test_min_commission_does_not_dominate():
    """高价股不得因最低佣金而被过度收费。"""
    c = TrackingCosts(position_notional=100_000.0)
    ret = net_return_pct(1500.0, 1515.0, c)
    # 毛涨 1.0%，成本 0.11%，滑点约 0.1% → 净收益应接近 0.79%
    assert 0.75 < ret < 0.85, f"净收益 {ret}% 偏离预期区间"


def test_small_notional_falls_back_to_min_commission():
    """基准仓位很小时，最低佣金应正确生效（而非被忽略）。"""
    c = TrackingCosts(position_notional=10_000.0)
    # 佣金 max(5, 3) = 5，双边 10；印花税 5；过户费 0.1（双边 0.2）
    # → 合计 15.2/10000 = 0.152%
    assert c.round_trip_cost_pct() == pytest.approx(0.00152)


def test_stamp_duty_is_piecewise_by_trade_date():
    """跨 2023-08-28 的回填必须按当时税率计印花税（减半前 1‰）。"""
    c = TrackingCosts(position_notional=100_000.0)
    # 旧税率：佣金 60 + 印花税 100 + 过户费 2 → 162/100000
    assert c.round_trip_cost_pct(as_of="2023-07-03") == pytest.approx(0.00162)
    # 生效日当天及以后：现行税率 0.5‰
    assert c.round_trip_cost_pct(as_of="2023-08-28") == pytest.approx(0.00112)
    # 未提供日期：按现行税率（向后兼容旧调用）
    assert c.round_trip_cost_pct() == pytest.approx(0.00112)


def test_zero_notional_does_not_divide_by_zero():
    """非法仓位应返回 0 成本而非抛异常。"""
    assert TrackingCosts(position_notional=0.0).round_trip_cost_pct() == 0.0
    assert TrackingCosts(position_notional=-1.0).round_trip_cost_pct() == 0.0


# ---------------------------------------------------------------------------
# 收益率口径
# ---------------------------------------------------------------------------

def test_gross_return_excludes_all_costs():
    """costs=None → 毛收益：仅按收盘价，不含滑点与费用。"""
    assert net_return_pct(100.0, 105.0, None) == pytest.approx(5.0)
    assert net_return_pct(100.0, 95.0, None) == pytest.approx(-5.0)


def test_net_return_is_lower_than_gross():
    """净收益必须低于毛收益（成本为正）。"""
    c = TrackingCosts()
    gross = net_return_pct(100.0, 105.0, None)
    net = net_return_pct(100.0, 105.0, c)
    assert net < gross
    # 差额 ≈ 往返成本 0.11% + 双边滑点 0.1%
    assert gross - net == pytest.approx(0.21, abs=0.03)


def test_net_return_includes_slippage():
    """滑点应体现在净收益中：零费率但非零滑点仍应降低收益。"""
    c = TrackingCosts(commission_rate=0.0, min_commission=0.0,
                      stamp_duty_sell=0.0, slippage_rate=0.001)
    net = net_return_pct(100.0, 100.0, c)   # 价格不变
    assert net < 0, "价格不变时滑点应导致亏损"


def test_net_return_handles_missing_data():
    """数据不足时返回 None，不得伪造 0。"""
    c = TrackingCosts()
    assert net_return_pct(None, 100.0, c) is None
    assert net_return_pct(100.0, None, c) is None
    assert net_return_pct(0.0, 100.0, c) is None
    assert net_return_pct(100.0, None, None) is None


# ---------------------------------------------------------------------------
# backfill_pending 口径开关
# ---------------------------------------------------------------------------

class _FakeKline(list):
    data_quality = "high"
    source = "test"


@pytest.fixture
def patched_fetcher(monkeypatch):
    """注入固定 K 线，避免联网。"""
    klines = [
        {"date": "2026-01-05", "close": 100.0},
        {"date": "2026-01-06", "close": 101.0},
        {"date": "2026-01-07", "close": 102.0},
        {"date": "2026-01-08", "close": 103.0},
        {"date": "2026-01-09", "close": 104.0},
        {"date": "2026-01-12", "close": 105.0},
    ]

    def fake_fetch_kline(code, beg=None, end=None, **kw):
        return _FakeKline(klines)

    import data_fetcher
    monkeypatch.setattr(data_fetcher, "fetch_kline", fake_fetch_kline, raising=True)
    return klines


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    tracking.init_db(conn)
    return conn


def test_backfill_gross_actually_excludes_costs(patched_fetcher):
    """apply_costs=False 必须真的不扣成本（原 --gross 开关失效的回归守卫）。"""
    conn = _make_db()
    tracking.add_recommendation(conn, {
        "code": "600519", "name": "贵州茅台", "rec_date": "2026-01-05",
        "horizon": 5, "stance": "看多", "score": 8.0, "logic": "测试",
    })
    done, still = tracking.backfill_pending(
        conn, today="2026-01-12", apply_costs=False)

    assert done == 1 and still == 0
    row = conn.execute("SELECT * FROM recommendations").fetchone()
    # 基准 100.0 → 105.0，毛收益 = +5.0%
    assert row["return_pct"] == pytest.approx(5.0), "毛收益口径仍扣了成本"
    conn.close()


def test_backfill_net_deducts_costs(patched_fetcher):
    """apply_costs=True（默认）应扣除滑点与费用。"""
    conn = _make_db()
    tracking.add_recommendation(conn, {
        "code": "600519", "name": "贵州茅台", "rec_date": "2026-01-05",
        "horizon": 5, "stance": "看多", "score": 8.0, "logic": "测试",
    })
    done, _ = tracking.backfill_pending(conn, today="2026-01-12")

    assert done == 1
    row = conn.execute("SELECT * FROM recommendations").fetchone()
    assert row["return_pct"] < 5.0, "净收益应低于毛收益"
    assert row["return_pct"] == pytest.approx(
        net_return_pct(100.0, 105.0, TrackingCosts()))
    conn.close()


def test_backfill_gross_and_net_differ(patched_fetcher):
    """两种口径必须产出不同结果（防止开关再次变成 no-op）。"""
    results = {}
    for apply_costs in (True, False):
        conn = _make_db()
        tracking.add_recommendation(conn, {
            "code": "600519", "name": "贵州茅台", "rec_date": "2026-01-05",
            "horizon": 5, "stance": "看多", "score": 8.0, "logic": "测试",
        })
        tracking.backfill_pending(conn, today="2026-01-12", apply_costs=apply_costs)
        results[apply_costs] = conn.execute(
            "SELECT return_pct FROM recommendations").fetchone()["return_pct"]
        conn.close()

    assert results[True] != results[False], "毛/净口径结果相同，开关未生效"
    assert results[False] > results[True]


def test_backfill_marks_incomplete_as_pending(monkeypatch):
    """K 线不足 N 根时应保持待回填，不写入收益率。"""
    import data_fetcher
    monkeypatch.setattr(data_fetcher, "fetch_kline",
                        lambda code, beg=None, end=None, **kw: _FakeKline([
                            {"date": "2026-01-05", "close": 100.0},
                            {"date": "2026-01-06", "close": 101.0},
                        ]), raising=True)

    conn = _make_db()
    tracking.add_recommendation(conn, {
        "code": "600519", "name": "贵州茅台", "rec_date": "2026-01-05",
        "horizon": 5, "stance": "看多", "score": 8.0, "logic": "测试",
    })
    done, still = tracking.backfill_pending(conn, today="2026-01-06")
    assert done == 0 and still == 1
    row = conn.execute("SELECT * FROM recommendations").fetchone()
    assert row["backfilled"] == 0
    assert row["return_pct"] is None
    conn.close()


def test_backfill_handles_empty_kline(monkeypatch):
    """取不到 K 线时应计入待回填，不崩溃。"""
    import data_fetcher
    monkeypatch.setattr(data_fetcher, "fetch_kline",
                        lambda code, beg=None, end=None, **kw: [], raising=True)

    conn = _make_db()
    tracking.add_recommendation(conn, {
        "code": "600519", "name": "贵州茅台", "rec_date": "2026-01-05",
        "horizon": 5, "stance": "看多", "score": 8.0, "logic": "测试",
    })
    done, still = tracking.backfill_pending(conn, today="2026-01-12")
    assert done == 0 and still == 1
    conn.close()


def test_db_path_stays_at_project_root():
    """拆分后 `_DB_PATH` 必须仍指向项目根目录的 tracking.db。

    `_DB_PATH` 由 `__file__` 推导，实现一旦下沉到 `track/` 子包，
    若不调整表达式，数据库会静默迁到 `<root>/track/tracking.db`
    —— 旧记录"消失"且不报错，属于典型的静默失败，故固化为守卫。
    """
    import os

    import tracking

    project_root = os.path.dirname(os.path.abspath(tracking.__file__))
    assert os.path.dirname(os.path.abspath(tracking._DB_PATH)) == project_root
