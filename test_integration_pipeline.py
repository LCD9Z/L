# -*- coding: utf-8 -*-
"""主流水线端到端集成测试（不依赖网络、不调用 LLM）。

覆盖 V3.7 全市场筛选链路：
    universe → 硬门槛 → 横截面因子排序 → Top-N
    → Stage2 增强 → Stage2 打分排序 → AI 候选

并验证：断点续跑确定性、原子写入、硬门槛否决、错误容忍、金额过滤。
"""
import json
import os

import pytest

from screen_pipeline import ScreenConfig, run_screen


# --------------------------------------------------------------------------
# 测试夹具
# --------------------------------------------------------------------------

def _make_row(code, *, price=100.0, amount=5e8, turnover=1.2,
              momentum_5d=0.03, momentum_20d=0.10, vol=0.30, dd=-0.05,
              vr=1.2, ar=1.1, **quote_extra):
    """构造一行合法的候选数据（含行情 + 因子）。"""
    quote = {"price": price, "amount": amount, "turnover": turnover}
    quote.update(quote_extra)
    return {
        "code": code,
        "quote": quote,
        "factors": {
            "momentum_5d": momentum_5d,
            "momentum_20d": momentum_20d,
            "realized_vol_20d": vol,
            "drawdown_20d": dd,
            "volume_ratio_5d": vr,
            "amount_ratio_5d": ar,
        },
    }


def _make_universe(n=60):
    """生成 n 只沪主板股票的模拟全市场快照，因子强弱呈梯度分布。"""
    rows = []
    for i in range(n):
        # 让动量随序号递增，确保横截面排序有确定的强弱顺序
        rows.append(_make_row(
            "600%03d" % (i + 1),
            momentum_5d=-0.05 + 0.002 * i,
            momentum_20d=-0.10 + 0.005 * i,
            vol=0.20 + 0.005 * i,
            dd=-0.15 + 0.002 * i,
        ))
    return rows


@pytest.fixture
def cfg():
    return ScreenConfig(stage1_keep=20, stage2_keep=10, ai_keep=5,
                        checkpoint_every=10)


# --------------------------------------------------------------------------
# 主链路
# --------------------------------------------------------------------------

def test_full_pipeline_stage_sizes_and_ordering(tmp_path, cfg):
    """全链路跑通：各阶段数量收敛，排序单调不增。"""
    result = run_screen(_make_universe(60), str(tmp_path), cfg)

    assert result["version"] == "3.7"
    assert result["counts"]["seen"] == 60
    assert result["counts"]["eligible"] == 60
    assert result["counts"]["errors"] == 0

    # 阶段收敛
    assert len(result["stage1"]) == 20
    assert len(result["stage2"]) <= 10
    assert len(result["ai_candidates"]) <= 5
    assert len(result["ai_candidates"]) <= len(result["stage2"]) <= len(result["stage1"])

    # stage1 按横截面得分降序
    s1 = [r["cross_section_score"] for r in result["stage1"]]
    assert s1 == sorted(s1, reverse=True), "stage1 未按得分降序排列"


def test_pipeline_writes_snapshot_and_checkpoint(tmp_path, cfg):
    """产物落盘：快照与检查点均存在且可解析。"""
    out = tmp_path / "run"
    run_screen(_make_universe(30), str(out), cfg)

    snap = out / "screen_snapshot.json"
    ckpt = out / "checkpoint.json"
    assert snap.exists() and ckpt.exists()

    data = json.loads(snap.read_text(encoding="utf-8"))
    assert data["counts"]["seen"] == 30
    assert data["resumable"] is True

    state = json.loads(ckpt.read_text(encoding="utf-8"))
    assert state["status"] == "complete"
    assert state["processed"] == 30


def test_no_temp_files_left_behind(tmp_path, cfg):
    """原子写入不得残留 .checkpoint_ / .json_ 临时文件。"""
    out = tmp_path / "run"
    run_screen(_make_universe(30), str(out), cfg)
    leftovers = [p for p in os.listdir(out)
                 if p.startswith(".checkpoint_") or p.startswith(".json_")]
    assert leftovers == [], f"存在未清理的临时文件: {leftovers}"


# --------------------------------------------------------------------------
# 硬门槛
# --------------------------------------------------------------------------

def test_hard_gates_reject_ineligible_rows(tmp_path, cfg):
    """停牌 / 缺价格 / 退市 / B股 应被硬门槛否决，不进入候选。"""
    universe = _make_universe(5)
    universe += [
        _make_row("600101", is_suspended=True),          # 停牌
        {"code": "600102", "quote": {"amount": 1e8}, "factors": {}},  # 缺价格
        _make_row("600103", delisted=True),              # 退市
        _make_row("900901"),                             # 沪B股
        _make_row("200011"),                             # 深B股
    ]
    result = run_screen(universe, str(tmp_path), cfg)

    assert result["counts"]["seen"] == 10
    assert result["counts"]["eligible"] == 5, "被否决的行不应计入 eligible"

    kept = {r["code"] for r in result["stage1"]}
    assert kept == {"600001", "600002", "600003", "600004", "600005"}


def test_risk_warning_untradeable_is_vetoed(tmp_path, cfg):
    """风险警示且不可交易应被否决。"""
    universe = _make_universe(3) + [
        _make_row("600201", risk_warning=True, risk_warning_tradeable=False),
    ]
    result = run_screen(universe, str(tmp_path), cfg)
    assert result["counts"]["eligible"] == 3
    assert "600201" not in {r["code"] for r in result["stage1"]}


def test_min_amount_filter(tmp_path):
    """min_amount 应过滤掉成交额不足的标的。"""
    cfg = ScreenConfig(stage1_keep=10, stage2_keep=5, ai_keep=3,
                       min_amount=1e9, checkpoint_every=1000)
    # 4 只成交额 20 亿（通过），1 只 0.5 亿（低于 10 亿阈值，被过滤）
    universe = [_make_row("600%03d" % (i + 1), amount=2e9) for i in range(4)]
    universe.append(_make_row("600301", amount=5e7))
    result = run_screen(universe, str(tmp_path), cfg)

    assert result["counts"]["eligible"] == 4, "低于阈值的标的不应计入 eligible"
    assert "600301" not in {r["code"] for r in result["stage1"]}


# --------------------------------------------------------------------------
# Stage2 增强
# --------------------------------------------------------------------------

def test_enrichment_path_applies_stage2_scoring(tmp_path):
    """提供 enrich 回调时，应走 Stage2 打分并产出 alpha 字段。"""
    cfg = ScreenConfig(stage1_keep=6, stage2_keep=3, ai_keep=2,
                       checkpoint_every=1000)

    def fake_enrich(row):
        # 模拟资金流/龙虎榜/微结构/事件风险四类 Stage2 输入
        code = row["code"]
        strong = code.endswith("6")
        return {
            "moneyflow": {"net_flow_mean": 10.0 if strong else -10.0,
                          "net_flow_positive_ratio": 1.0 if strong else 0.0},
            "top_list": {"net_buy_total": 10.0 if strong else -10.0,
                         "net_buy_positive_ratio": 1.0 if strong else 0.0},
            "microstructure": {"max_limit_up_streak": 2 if strong else 0,
                               "limit_down_days": 0 if strong else 2,
                               "failed_limit_up_proxy_days": 0},
            "event_risk": {"high_risk_flags": [] if strong else ["share_float"]},
        }

    result = run_screen(_make_universe(6), str(tmp_path), cfg, enrich=fake_enrich)

    assert all("stage2_alpha_score" in r for r in result["stage2"])
    # Stage2 得分应降序
    s2 = [r["stage2_alpha_score"] for r in result["stage2"]]
    assert s2 == sorted(s2, reverse=True)


def test_enrichment_failure_does_not_break_batch(tmp_path):
    """单个 enrich 抛错时，批次应继续并记录 enrich_error。"""
    cfg = ScreenConfig(stage1_keep=5, stage2_keep=5, ai_keep=3,
                       checkpoint_every=1000)

    def flaky_enrich(row):
        if row["code"].endswith("3"):
            raise RuntimeError("模拟数据源故障")
        return {"moneyflow": {"net_flow_mean": 1.0}}

    result = run_screen(_make_universe(5), str(tmp_path), cfg, enrich=flaky_enrich)

    failed = [r for r in result["stage2"] if "enrich_error" in r]
    assert len(failed) == 1, "失败行应保留并标注 enrich_error"
    assert "模拟数据源故障" in failed[0]["enrich_error"]
    assert len(result["stage2"]) == 5, "其余行不应被丢弃"


# --------------------------------------------------------------------------
# 断点续跑
# --------------------------------------------------------------------------

def test_resume_is_deterministic(tmp_path):
    """续跑结果应与一次性跑完完全一致（不重复、不遗漏、排序稳定）。"""
    cfg = ScreenConfig(stage1_keep=20, stage2_keep=10, ai_keep=5,
                       checkpoint_every=7)
    universe = _make_universe(40)
    out = str(tmp_path / "run")

    first = run_screen(universe, out, cfg)
    resumed = run_screen(universe, out, cfg, resume=True)

    assert [r["code"] for r in first["stage1"]] == [r["code"] for r in resumed["stage1"]]
    assert resumed["counts"]["seen"] == first["counts"]["seen"]
    assert len(resumed["stage1"]) == len(first["stage1"])


def test_checkpoint_persists_midway_progress(tmp_path):
    """中途检查点应保存已筛选行，供续跑复用。"""
    cfg = ScreenConfig(stage1_keep=20, stage2_keep=10, ai_keep=5,
                       checkpoint_every=5)
    out = tmp_path / "run"

    def short_circuit():
        # 只喂前 12 行，检查点应在第 10 行处落盘
        for raw in _make_universe(12):
            yield raw

    run_screen(short_circuit(), str(out), cfg)
    state = json.loads((out / "checkpoint.json").read_text(encoding="utf-8"))
    assert state["processed"] == 12
    assert len(state["eligible_rows"]) == 12


# --------------------------------------------------------------------------
# 错误容忍
# --------------------------------------------------------------------------

def test_too_many_row_errors_aborts(tmp_path):
    """行错误超过 max_errors 时应快速失败，而不是静默产出残缺结果。"""
    cfg = ScreenConfig(stage1_keep=10, stage2_keep=5, ai_keep=3,
                       checkpoint_every=1000, max_errors=3)
    # factors 为非映射类型，_factor_row 解析时会抛错，制造真实行错误
    bad_universe = [{"code": "600001", "quote": {"price": 1.0}, "factors": 12345}
                    for _ in range(10)]

    with pytest.raises(RuntimeError, match="too many row errors"):
        run_screen(bad_universe, str(tmp_path), cfg)
