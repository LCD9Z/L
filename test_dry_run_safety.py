# -*- coding: utf-8 -*-
"""`--dry-run` 副作用守卫。

`--dry-run` 的语义是「只选股打分并打印，不产生任何持久化副作用」。
但 main() 曾在 dry-run 下仍调用 save_tracking_records()，把试运行的推荐写入
tracking.db —— 这些记录被 backfill 后会进入胜率校准样本，污染真实统计。

本测试锁定：dry-run 不得写 tracking、不得更新股票池、不得写飞书。
"""
import json
import sys

import pytest


@pytest.fixture
def stubbed_env(tmp_path, monkeypatch):
    """构造一个完全离线、路径隔离的每日选股环境。"""
    import data_fetcher

    klines = [
        {"date": "2026-%02d-%02d" % (m, d), "open": 100 + m + d, "close": 100 + m + d,
         "high": 105 + m + d, "low": 95 + m + d, "volume": 1000}
        for m in range(1, 4) for d in range(1, 25)
    ]

    class _K(list):
        data_quality = "high"
        source = "test"

    def fake_kline(code, limit=None, min_quality=None, **kw):
        return _K(klines[:limit or len(klines)])

    def fake_quote(code):
        return {"code": code, "name": "测试股", "price": 110.0, "change_pct": 1.5,
                "turnover": 2.0, "pe": 20.0, "pb": 2.0, "amount": 5e8,
                "open": 108.0, "prev_close": 108.4, "high": 111.0,
                "low": 107.0, "volume": 10000, "change": 1.6}

    monkeypatch.setattr(data_fetcher, "fetch_kline", fake_kline, raising=True)
    monkeypatch.setattr(data_fetcher, "fetch_quote", fake_quote, raising=True)

    import market_regime
    import a_share_risk
    monkeypatch.setattr(market_regime, "get_market_regime",
                        lambda: {"regime": "RANGE", "note": "测试"}, raising=True)
    monkeypatch.setattr(a_share_risk, "position_plan",
                        lambda bars, regime, risk: {"position_pct": 10.0, "atr": 1.0,
                                                    "atr_pct": 0.9, "stop_loss": 100.0,
                                                    "reason": "t"}, raising=True)

    import industry_strength
    monkeypatch.setattr(industry_strength, "rank_industries",
                        lambda *a, **k: [], raising=True)
    monkeypatch.setattr(industry_strength, "stock_industry_bonus",
                        lambda *a, **k: 0.0, raising=True)

    # 隔离路径：股票池 / 状态目录 / 报告目录
    wl = tmp_path / "watchlist.json"
    wl.write_text(json.dumps({
        "watchlist": [{"code": "600519", "name": "测试股", "note": "白酒·核心"}],
        "top_n_deep": 0, "push_enabled": False,
    }, ensure_ascii=False), encoding="utf-8")

    import runtime_env
    monkeypatch.setattr(runtime_env, "WATCHLIST_FILE", str(wl), raising=True)
    monkeypatch.setattr(runtime_env, "STATE_DIR", str(tmp_path), raising=True)
    monkeypatch.setattr(runtime_env, "CANDIDATE_FILE",
                        str(tmp_path / "candidate_pool.json"), raising=True)
    monkeypatch.setattr(runtime_env, "POOL_STATE_FILE",
                        str(tmp_path / "pool_state.json"), raising=True)
    monkeypatch.setattr(runtime_env, "REPORT_DIR", str(tmp_path / "reports"), raising=True)

    import daily_stock_pick
    monkeypatch.setattr(daily_stock_pick, "fetch_kline", fake_kline, raising=True)
    monkeypatch.setattr(daily_stock_pick, "get_market_regime",
                        lambda: {"regime": "RANGE", "note": "测试"}, raising=True)
    monkeypatch.setattr(daily_stock_pick, "position_plan",
                        lambda bars, regime, risk: {"position_pct": 10.0, "atr": 1.0,
                                                    "atr_pct": 0.9, "stop_loss": 100.0,
                                                    "reason": "t"}, raising=True)
    monkeypatch.setattr(daily_stock_pick, "REPORT_DIR", str(tmp_path / "reports"),
                        raising=True)

    import industry_context
    monkeypatch.setattr(industry_context, "fetch_kline", fake_kline, raising=True)
    monkeypatch.setattr(industry_context, "rank_industries",
                        lambda *a, **k: [], raising=True)
    monkeypatch.setattr(industry_context, "stock_industry_bonus",
                        lambda *a, **k: 0.0, raising=True)

    import stock_scoring
    monkeypatch.setattr(stock_scoring, "fetch_kline", fake_kline, raising=True)
    monkeypatch.setattr(stock_scoring, "fetch_quote", fake_quote, raising=True)

    return daily_stock_pick


def _run(monkeypatch, dsp, *argv):
    monkeypatch.setattr(sys, "argv", ["daily_stock_pick.py"] + list(argv), raising=True)
    dsp.main()


def test_dry_run_does_not_write_tracking(stubbed_env, monkeypatch):
    """dry-run 不得调用 save_tracking_records。"""
    dsp = stubbed_env
    calls = []
    monkeypatch.setattr(dsp, "save_tracking_records",
                        lambda stocks, *a, **k: calls.append(stocks), raising=True)

    _run(monkeypatch, dsp, "--dry-run", "--no-deep", "--no-pool-update")
    assert calls == [], "dry-run 仍写入了 tracking 记录"


def test_dry_run_does_not_push_or_write_feishu(stubbed_env, monkeypatch):
    """dry-run 不得写飞书表格、不得推送。"""
    dsp = stubbed_env
    pushed, based = [], []
    monkeypatch.setattr(dsp, "send_push",
                        lambda stocks, note="": pushed.append(stocks), raising=True)
    monkeypatch.setattr(dsp, "add_records_to_base",
                        lambda stocks: based.append(stocks), raising=True)

    _run(monkeypatch, dsp, "--dry-run", "--no-deep", "--no-pool-update")
    assert pushed == [] and based == [], "dry-run 仍执行了飞书写表或推送"


def test_dry_run_does_not_update_watchlist(stubbed_env, monkeypatch):
    """dry-run 下 update_watchlist 必须以 dry=True 调用（只预览不改文件）。"""
    dsp = stubbed_env
    seen = []

    def spy(stocks, dry=False):
        seen.append(dry)
        return ([], [])

    monkeypatch.setattr(dsp, "update_watchlist", spy, raising=True)
    _run(monkeypatch, dsp, "--dry-run", "--no-deep")
    assert seen == [True], f"update_watchlist 的 dry 参数应为 True，实际 {seen}"


def test_non_dry_run_does_write_tracking(stubbed_env, monkeypatch):
    """对照组：非 dry-run 时应正常写入 tracking（确保守卫没有过度拦截）。"""
    dsp = stubbed_env
    calls = []
    monkeypatch.setattr(dsp, "save_tracking_records",
                        lambda stocks, *a, **k: calls.append(stocks), raising=True)
    monkeypatch.setattr(dsp, "send_push", lambda *a, **k: "", raising=True)
    monkeypatch.setattr(dsp, "add_records_to_base", lambda *a, **k: True, raising=True)

    _run(monkeypatch, dsp, "--no-deep", "--no-pool-update")
    assert len(calls) == 1, "非 dry-run 应写入 tracking 记录"


def test_dry_run_still_produces_report(stubbed_env, tmp_path, monkeypatch):
    """dry-run 应保留本地报告产物，便于人工检查。"""
    dsp = stubbed_env
    _run(monkeypatch, dsp, "--dry-run", "--no-deep", "--no-pool-update")
    reports = list((tmp_path / "reports").glob("screening_*.json"))
    assert reports, "dry-run 未产出日报 JSON"
    data = json.loads(reports[0].read_text(encoding="utf-8"))
    assert data["stocks"], "日报中无个股记录"
