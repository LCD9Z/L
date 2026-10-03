# -*- coding: utf-8 -*-
"""tdx_native 包守卫测试（全合成夹具，零真实 TDX 数据依赖）。

背景
----
``tdx_native/`` 是 2026-09-30 新增的原生数据 / 推荐模块（12 个文件），
但此前**没有任何 pytest 覆盖**：它的自测脚本 ``smoke_test.py`` 位于包内
而非 ``tests/``，pytest 默认只收集 ``test_*.py``，因此长期未被质量门禁保护。
新模块在门禁之外，正是本项目最警惕的「静默失效」土壤。

本文件把关键不变量固化为断言：

1. ``.day`` 二进制格式（struct ``<IIIIIfII``）写→读往返
2. 代码分类与涨跌停幅度 —— 板块判错会让 V2 跳空过滤静默失效
3. 前复权因子必须消除除权缺口 —— 复权错会让 ret20 被权息污染
4. 跟踪回填的 T+1 / T+5 / T+20 日期口径与停牌顺延三态
5. gbbq 权息缓存解析、五因子分位合成、风险标签
"""
from __future__ import annotations

import csv
import struct

import pytest

from tdx_native import adjust
from tdx_native import backfill
from tdx_native import daily_report
from tdx_native import day_reader
from tdx_native import five_factor
from tdx_native import gbbq_reader
from tdx_native import run_daily
from tdx_native import screen as screen_mod

REC = struct.Struct("<IIIIIfII")


# ---------------------------------------------------------------------------
# 合成夹具
# ---------------------------------------------------------------------------

def _write_day(path: str, rows) -> None:
    """写合成 .day 文件。rows: [(date, open, high, low, close, amount, volume)]。"""
    with open(path, "wb") as f:
        for d, o, h, l, c, a, v in rows:
            f.write(REC.pack(int(d), round(o * 100), round(h * 100),
                             round(l * 100), round(c * 100), float(a), int(v), 0))


def _flat_rows(dates, close: float = 10.0, amount: float = 3e8):
    """生成价格恒定的 bar 序列（便于精确断言）。"""
    return [(d, close, close, close, close, amount, 1_000_000) for d in dates]


def _bar(date: str, close: float) -> dict:
    return {"date": date, "open": close, "high": close, "low": close,
            "close": close, "amount": 3e8, "volume": 1e6}


# ---------------------------------------------------------------------------
# 1. day_reader —— 二进制解析与代码分类
# ---------------------------------------------------------------------------

def test_day_binary_roundtrip(tmp_path):
    """`.day` 写→读往返：日期为字符串、价格已除以 100。"""
    path = str(tmp_path / "sh600000.day")
    rows = [(20260101, 10.0, 10.2, 9.9, 10.1, 3e8, 1_000_000),
            (20260102, 10.1, 10.5, 10.0, 10.4, 3e8, 1_100_000)]
    _write_day(path, rows)

    bars = day_reader.read_day_all(path)
    assert len(bars) == 2
    assert bars[0]["date"] == "20260101"        # 日期必须是 str，不是 float
    assert isinstance(bars[0]["date"], str)
    assert bars[1]["close"] == pytest.approx(10.4)
    assert bars[1]["amount"] == pytest.approx(3e8)


def test_day_reader_skips_nonpositive_close(tmp_path):
    """close <= 0 的记录必须被跳过（否则会污染收益率序列）。"""
    path = str(tmp_path / "sh600000.day")
    _write_day(path, [(20260101, 10.0, 10.0, 10.0, 0.0, 3e8, 1e6),
                      (20260102, 10.0, 10.0, 10.0, 10.0, 3e8, 1e6)])
    bars = day_reader.read_day_all(path)
    assert [b["date"] for b in bars] == ["20260102"]


def test_day_reader_tail_limits_count(tmp_path):
    """read_day_tail 只取尾部 n 根，且保持升序。"""
    path = str(tmp_path / "sh600000.day")
    _write_day(path, _flat_rows([20260101 + i for i in range(10)]))
    bars = day_reader.read_day_tail(path, 3)
    assert [b["date"] for b in bars] == ["20260108", "20260109", "20260110"]


@pytest.mark.parametrize("code,market,expected", [
    ("600519", "sh", True),     # 沪市主板
    ("688981", "sh", True),     # 科创板
    ("300750", "sz", True),     # 创业板
    ("000001", "sz", True),     # 深市主板
    ("430047", "bj", True),     # 北交所（老代码段）
    ("920001", "bj", True),     # 北交所（新代码段）
    ("880001", "sh", False),    # 通达信板块指数
    ("000300", "sh", False),    # 沪深300 指数（与深市主板代码重叠，靠 market 消歧）
    ("399001", "sz", False),    # 深证成指
    ("123456", "sz", False),    # 非法代码段
])
def test_is_a_share_stock(code, market, expected):
    """代码分类必须同时看代码段与 market（否则 000300 会被误当股票）。"""
    assert day_reader.is_a_share_stock(code, market) is expected


@pytest.mark.parametrize("code,board,limit", [
    ("600519", "sh_main", 0.10),
    ("000001", "sz_main", 0.10),
    ("688981", "star", 0.20),
    ("300750", "chinext", 0.20),
    ("430047", "bse", 0.30),
])
def test_board_and_limit(code, board, limit):
    """板块与涨跌停幅度 —— V2 跳空过滤的阈值就建立在此之上。"""
    assert day_reader.board_of(code) == board
    assert day_reader.limit_pct(code) == pytest.approx(limit)


def test_load_names_parses_and_zero_pads(tmp_path):
    """名称表：表头被消费、代码补零到 6 位。"""
    p = tmp_path / "names.csv"
    p.write_text("code,name\n600519,贵州茅台\n1,平安银行\n", encoding="utf-8")
    names = day_reader.load_names(str(p))
    assert names["600519"] == "贵州茅台"
    assert names["000001"] == "平安银行"          # 补零
    assert day_reader.load_names("") == {}        # 空路径不抛异常
    assert day_reader.load_names(str(tmp_path / "nope.csv")) == {}


def test_scan_paths_finds_stocks(tmp_path):
    """scan_paths 返回 (code, market, path)，并过滤非股票代码。"""
    lday = tmp_path / "sh" / "lday"
    lday.mkdir(parents=True)
    _write_day(str(lday / "sh600000.day"), _flat_rows([20260101]))
    _write_day(str(lday / "sh880001.day"), _flat_rows([20260101]))   # 板块指数，应剔除
    found = day_reader.scan_paths(str(tmp_path))
    assert [c for c, _m, _p in found] == ["600000"]


# ---------------------------------------------------------------------------
# 2. adjust —— 前复权
# ---------------------------------------------------------------------------

def test_event_factor_cash_dividend():
    """纯现金分红 0.5 元/股：k = (10 - 0.5) / 10 = 0.95。"""
    ev = ("20260105", 0.5, 0.0, 0.0, 0.0)     # date, cash, bonus, rights_price, rights_ps
    assert adjust.event_factor(10.0, ev) == pytest.approx(0.95)


def test_event_factor_bonus_and_rights():
    """10 送 2 派 0.5：k = (10 - 0.5) / (10 × 1.2)。"""
    ev = ("20260105", 0.5, 0.2, 0.0, 0.0)
    assert adjust.event_factor(10.0, ev) == pytest.approx(9.5 / 12.0)


def test_event_factor_guards_against_bad_input():
    """非法输入（前收 <= 0 / 因子非正）一律返回 1.0，不做破坏性调整。"""
    assert adjust.event_factor(0.0, ("20260105", 1.0, 0.0, 0.0, 0.0)) == 1.0
    assert adjust.event_factor(10.0, ("20260105", 20.0, 0.0, 0.0, 0.0)) == 1.0


def test_apply_qfq_removes_ex_dividend_gap():
    """核心正确性：复权后，除权日**之前**的价格应下调，使缺口消失。

    构造：除权日前收 10.0，除权日现金分红 0.5 元/股 → 理论参考价 9.5。
    复权后除权日前的收盘应变为 9.5，与除权日实际收盘衔接（无跳空）。
    """
    bars = [_bar("20260101", 10.0), _bar("20260102", 10.0),
            _bar("20260105", 9.5), _bar("20260106", 9.6)]
    events = [("20260105", 0.5, 0.0, 0.0, 0.0)]
    out = adjust.apply_qfq(bars, events)
    assert out[0]["close"] == pytest.approx(9.5)     # 除权日之前被下调
    assert out[2]["close"] == pytest.approx(9.5)     # 除权日及之后不变
    # 复权后 20260102 → 20260105 的收益率不再含权息缺口
    r = out[2]["close"] / out[1]["close"] - 1
    assert abs(r) < 1e-9


def test_apply_qfq_without_events_is_identity():
    """无事件时原样返回（同一对象，零开销）。"""
    bars = [_bar("20260101", 10.0)]
    assert adjust.apply_qfq(bars, []) is bars


def test_qfq_factors_before_earliest_event():
    """早于最早事件（或事件日之前无 bar）的日期因子为 1.0。"""
    bars = [_bar("20260110", 10.0), _bar("20260111", 10.0)]
    # 事件日 20260101 早于全部 bar —— 找不到「事件日之前最后一个交易日」
    fac = adjust.qfq_factors(bars, [("20260101", 1.0, 0.0, 0.0, 0.0)])
    assert all(v == pytest.approx(1.0) for v in fac.values())


# ---------------------------------------------------------------------------
# 3. backfill —— 跟踪回填
# ---------------------------------------------------------------------------

def test_last_close_before_respects_after_bound():
    """回溯必须落在 (after, date] 区间内。"""
    bars = {"20260101": {"close": 9.0}, "20260103": {"close": 11.0}}
    assert backfill._last_close_before(bars, "20260105", after="20260102") == 11.0
    assert backfill._last_close_before(bars, "20260105", after="20260104") is None
    assert backfill._last_close_before(bars, "20260102") == 9.0


def test_ret_at_three_states():
    """_ret_at 三态：正常 / 停牌顺延 / 无 bar 可回溯（pending）。"""
    cal = ["20260101", "20260102", "20260103", "20260104", "20260105", "20260106"]
    bars = {"20260101": {"close": 10.0}, "20260102": {"close": 10.5}}

    # 未到期：i + k 超出日历
    assert backfill._ret_at(cal, bars, 0, 6, "20260102", 10.5) is None

    # 正常：cal[2] = 20260103 有 bar
    bars_full = dict(bars, **{"20260103": {"close": 11.0}})
    assert backfill._ret_at(cal, bars_full, 0, 2, "20260102", 10.5) == (
        "20260103", 11.0, 11.0 / 10.5 - 1, 2)

    # 停牌顺延：目标日 cal[4] = 20260105 无 bar，
    # 且存在「严格晚于建仓日 20260102」的最后一根（20260103）可回溯。
    # date 必须回传**实际使用的那一根**（20260103），不能是 None——
    # 否则 t20_date 落空 → _due_exits 跳过 → 持仓永不提示卖出（2026-10-02 审计）
    bars_susp = dict(bars, **{"20260103": {"close": 11.0}})
    assert backfill._ret_at(cal, bars_susp, 0, 4, "20260102", 10.5) == (
        "20260103", 11.0, 11.0 / 10.5 - 1, None)

    # pending：目标日无 bar，且建仓日之后无任何 bar 可回溯
    # （注意 after 是**严格**边界：等于建仓日的 bar 不算）
    only_entry = {"20260101": {"close": 10.0}}
    assert backfill._ret_at(cal, only_entry, 0, 3, "20260101", 10.0) == (
        "pending", None, None, None)


def test_backfill_run_fills_t1_t5_t20(tmp_path):
    """端到端：T+1 开盘建仓、T+5 / T+20 收盘，日期口径 = 主日历偏移。"""
    lday = tmp_path / "vipdoc" / "sh" / "lday"
    lday.mkdir(parents=True)
    cal_dates = [20260101 + i for i in range(30)]
    _write_day(str(lday / "sh000001.day"), _flat_rows(cal_dates, close=3000.0))

    # 个股：价格恒定 10.0，便于精确断言收益率为 0
    _write_day(str(lday / "sh600000.day"), _flat_rows(cal_dates, close=10.0))

    tracking = tmp_path / "tracking.csv"
    tracking.write_text("as_of,code\n20260101,600000\n", encoding="utf-8")
    out = tmp_path / "filled.csv"

    summary = backfill.run(str(tmp_path / "vipdoc"), str(tracking), str(out))
    assert summary["filled_t20"] == 1
    assert summary["pending"] == 0

    with open(out, encoding="utf-8", newline="") as f:
        row = next(csv.DictReader(f))
    assert row["t1_date"] == "20260102"        # cal[i+1]
    assert row["t5_date"] == "20260106"        # cal[i+5]
    assert row["t20_date"] == "20260121"       # cal[i+20]
    assert float(row["t20_ret"]) == pytest.approx(0.0, abs=1e-9)   # CSV 取值为字符串
    assert row["status"] == "filled"


def test_backfill_run_marks_as_of_not_in_calendar(tmp_path):
    """as_of 不在主日历（如客户端数据未更新）→ 标记而非崩溃。"""
    lday = tmp_path / "vipdoc" / "sh" / "lday"
    lday.mkdir(parents=True)
    _write_day(str(lday / "sh000001.day"), _flat_rows([20260101 + i for i in range(30)]))
    _write_day(str(lday / "sh600000.day"), _flat_rows([20260101 + i for i in range(30)]))

    tracking = tmp_path / "tracking.csv"
    tracking.write_text("as_of,code\n20991231,600000\n", encoding="utf-8")
    out = tmp_path / "filled.csv"

    summary = backfill.run(str(tmp_path / "vipdoc"), str(tracking), str(out))
    assert summary["skipped"] == 1


# ---------------------------------------------------------------------------
# 4. gbbq_reader —— 权息缓存
# ---------------------------------------------------------------------------

def test_load_events_parses_and_sorts(tmp_path):
    """缓存解析为 {code: [Event...]}，同股按日期升序。"""
    p = tmp_path / "gbbq_events.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "date", "cash", "bonus", "rights_price", "rights_shares"])
        w.writerow(["600000", "20260110", "0.5", "0.2", "0.0", "0.0"])
        w.writerow(["600000", "20250610", "0.3", "0.0", "0.0", "0.0"])   # 更早
        w.writerow(["1", "20260101", "0.1", "0.0", "0.0", "0.0"])        # 需补零

    ev = gbbq_reader.load_events(str(p))
    assert set(ev) == {"600000", "000001"}
    assert [e[0] for e in ev["600000"]] == ["20250610", "20260110"]      # 升序
    assert ev["000001"][0][1] == pytest.approx(0.1)                      # cash 已转 float


def test_load_events_missing_file_returns_empty():
    """缓存缺失时返回空 dict（主路径零依赖，不应抛异常）。"""
    assert gbbq_reader.load_events("") == {}
    assert gbbq_reader.load_events("no_such_file.csv") == {}


# ---------------------------------------------------------------------------
# 5. five_factor —— 因子与合成分
# ---------------------------------------------------------------------------

def test_pct_rank_is_average_rank_percentile():
    """分位排名：严格递增序列应为 1/n, 2/n, ..., 1.0。"""
    assert five_factor.pct_rank([1.0, 2.0, 3.0]) == pytest.approx([1 / 3, 2 / 3, 1.0])


def test_pct_rank_ties_share_average_rank():
    """并列值取平均秩。"""
    # 两个并列最小值 → 平均秩 1.5 / 3；最大值 → 3 / 3
    assert five_factor.pct_rank([1.0, 1.0, 5.0]) == pytest.approx([0.5, 0.5, 1.0])


def test_compute_factors_rejects_insufficient_history():
    """历史不足 22 根必须返回 None（否则 ret20 会用到越界下标）。"""
    assert five_factor.compute_factors([]) is None
    assert five_factor.compute_factors([_bar("20260101", 10.0)] * 21) is None


def test_compute_factors_rejects_illiquid():
    """20 日均成交额低于 1 亿必须返回 None（流动性门槛）。"""
    bars = [_bar(f"2026010{i % 9 + 1}", 10.0) for i in range(25)]
    for b in bars:
        b["amount"] = 1e6          # 远低于 LIQ_MIN
    assert five_factor.compute_factors(bars) is None


def test_composite_score_direction_is_respected():
    """反向因子取 1-rank、正向因子取 rank —— 方向搞反会翻转整个策略。"""
    # 两个候选：A 的 ret20 更高（反向因子，应得低分）
    a = {"ret20": 0.2, "vol20": 0.1, "amihud20": 0.1, "loga20": 1.0, "maxret20": 0.1}
    b = {"ret20": 0.0, "vol20": 0.1, "amihud20": 0.1, "loga20": 1.0, "maxret20": 0.1}
    five_factor.composite_score([a, b])
    assert a["score"] < b["score"]
    assert 0.0 <= a["score"] <= 1.0 and 0.0 <= b["score"] <= 1.0


# ---------------------------------------------------------------------------
# 6. daily_report —— 风险标签
# ---------------------------------------------------------------------------

def test_risk_flags_detect_board_and_liquidity():
    """板块标签与低流动性标签。"""
    flags = daily_report._risk_flags("430047", "bj", 1e8, [_bar("20260101", 10.0)])
    assert any("北交所" in f for f in flags)
    assert any("流动性偏低" in f for f in flags)


def test_risk_flags_detect_recent_limit_jump():
    """回溯 21 根内出现超过涨跌停幅度的跳空 → 打标（与 V2 过滤同源）。"""
    bars = [_bar("20260101", 10.0), _bar("20260102", 12.0)]   # +20% > 主板 10%
    flags = daily_report._risk_flags("600000", "sh", 3e8, bars)
    assert any("跳空" in f for f in flags)


def test_risk_flags_clean_stock_has_no_board_flag():
    """主板、高流动性、无跳空 → 不应产生板块/流动性标签。"""
    bars = [_bar(f"2026010{i}", 10.0 + i * 0.01) for i in range(1, 6)]
    flags = daily_report._risk_flags("600000", "sh", 5e8, bars)
    assert not any("北交所" in f or "双创" in f or "流动性偏低" in f for f in flags)


# ---------------------------------------------------------------------------
# 6. run_daily —— 到期卖出提示（闭环的"离场"一侧）
# ---------------------------------------------------------------------------

def _write_filled(path: str, rows) -> None:
    """写合成 tracking_filled.csv。

    rows: [(as_of, code, name, t20_date, t20_ret)]
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["as_of", "code", "name", "t1_date", "t1_open",
                    "t20_date", "t20_ret", "risk_flags"])
        for as_of, code, name, t20d, ret in rows:
            w.writerow([as_of, code, name, "20260602", "10.0000",
                        t20d, ret, ""])


def test_due_exits_covers_overdue_window(tmp_path):
    """不仅覆盖「今日到期」，也要捞回容忍窗口内已逾期的项。

    动机：到期日当天任务可能没跑（数据未更新 / 关机 / 节假日）。
    只匹配当天会让这些持仓**永远不被提示**，用户就错过了离场时点。
    """
    p = str(tmp_path / "filled.csv")
    _write_filled(p, [
        ("20260601", "600000", "浦发银行", "20260630", "-0.050000"),  # 今日到期
        ("20260601", "000001", "平安银行", "20260625", "0.010000"),   # 逾期 5 天
        ("20260601", "300750", "宁德时代", "20260501", "-0.020000"),  # 逾期 60 天 → 超窗
        ("20260601", "600519", "贵州茅台", "", ""),                    # 未到期
    ])
    got = run_daily._due_exits(p, "20260630")
    assert [r["code"] for r in got] == ["600000", "000001"]
    assert [r["_overdue_days"] for r in got] == [0, 5]


def test_due_exits_excludes_not_yet_due(tmp_path):
    """到期日在 today 之后的持仓不进清单。"""
    p = str(tmp_path / "filled.csv")
    _write_filled(p, [("20260601", "600000", "浦发银行", "20260730", "-0.05")])
    assert run_daily._due_exits(p, "20260630") == []


def test_due_exits_missing_file_returns_empty(tmp_path):
    """回填产物不存在时不抛错（首次运行 / 数据未更新被跳过的场景）。"""
    assert run_daily._due_exits(str(tmp_path / "nope.csv"), "20260630") == []


def test_export_exits_writes_table_with_return(tmp_path):
    """有到期持仓时写出表格，收益按百分比格式呈现。"""
    rows = [{"code": "600000", "name": "浦发银行", "t1_date": "20260602",
             "t1_open": "10.0000", "t20_date": "20260630",
             "t20_ret": "-0.050000", "_overdue_days": 0}]
    p = run_daily.export_exits(rows, str(tmp_path), "20260630")
    text = open(p, encoding="utf-8").read()
    assert "600000" in text
    assert "-5.00%" in text
    assert "今日到期" in text
    assert "不构成投资建议" in text


def test_export_exits_marks_overdue_items(tmp_path):
    """逾期项要显式标注天数，并说明"补跑会自动捞回"。"""
    rows = [{"code": "000001", "name": "平安银行", "t1_date": "20260602",
             "t1_open": "10.0000", "t20_date": "20260625",
             "t20_ret": "0.010000", "_overdue_days": 5}]
    p = run_daily.export_exits(rows, str(tmp_path), "20260630")
    text = open(p, encoding="utf-8").read()
    assert "逾期 5 天" in text
    assert "已逾期" in text


def test_export_exits_empty_writes_notice(tmp_path):
    """无到期持仓时明确写「今日无到期持仓」，而不是留空文件。"""
    p = run_daily.export_exits([], str(tmp_path), "20260701")
    text = open(p, encoding="utf-8").read()
    assert "今日无到期持仓" in text


# ---------------------------------------------------------------------------
# 7. screen.preflight —— 写入前的数据完整性闸门（防「静默失效」）
# ---------------------------------------------------------------------------

def test_preflight_flags_empty_directory(tmp_path):
    """目录空空 → 必须报问题。残缺池绝不能静默通过。"""
    pf = screen_mod.preflight(str(tmp_path))
    assert pf["stocks_found"] == 0
    assert pf["problems"]


def test_preflight_flags_small_universe(tmp_path):
    """股票池远小于阈值（数据没下全）→ 报问题。"""
    d = tmp_path / "sh" / "lday"
    d.mkdir(parents=True)
    for i in range(10):
        _write_day(str(d / f"sh60000{i}.day"),
                   _flat_rows([20260101 + j for j in range(30)]))
    pf = screen_mod.preflight(str(tmp_path))
    assert pf["stocks_found"] == 10
    assert any("股票池仅" in p for p in pf["problems"])


def test_preflight_passes_when_fresh(tmp_path, monkeypatch):
    """池规模达标 + 全部数据新鲜 → 通过（无 problems）。"""
    monkeypatch.setattr(screen_mod, "MIN_UNIVERSE_STOCKS", 5)
    d = tmp_path / "sh" / "lday"
    d.mkdir(parents=True)
    dates = [20260101 + i for i in range(30)]
    for i in range(6):
        _write_day(str(d / f"sh60000{i}.day"), _flat_rows(dates))
    pf = screen_mod.preflight(str(tmp_path))
    assert pf["problems"] == []
    assert pf["fresh_ratio"] == 1.0
    assert pf["as_of"] == "20260130"


def test_preflight_flags_stale_data(tmp_path, monkeypatch):
    """部分标的数据滞后 → 报「下载未完成」（比只看文件数量可靠）。"""
    monkeypatch.setattr(screen_mod, "MIN_UNIVERSE_STOCKS", 5)
    monkeypatch.setattr(screen_mod, "MIN_FRESH_RATIO", 0.9)
    d = tmp_path / "sh" / "lday"
    d.mkdir(parents=True)
    fresh = [20260101 + i for i in range(30)]      # 到 20260130
    stale = [20251201 + i for i in range(30)]      # 停在 20251230
    for i in range(8):
        _write_day(str(d / f"sh60000{i}.day"), _flat_rows(fresh))
    for i in range(8, 10):
        _write_day(str(d / f"sh60000{i}.day"), _flat_rows(stale))
    pf = screen_mod.preflight(str(tmp_path))
    assert pf["fresh_ratio"] == 0.8
    assert any("下载未完成" in p for p in pf["problems"])


# ---------------------------------------------------------------------------
# 2026-10-02 独立审计新增回归（详见 AUDIT_2026_10_02_REPORT.md）
# 三条都是「不报错但产出错误结果」的静默失效，必须锁死
# ---------------------------------------------------------------------------


def test_stale_exclude_uses_trading_days_not_calendar_days(tmp_path):
    """停牌剔除必须按**交易日**计数，不能用 int(YYYYMMDD) 日历差。

    回归缺陷：int("20261009") - int("20260930") = 79，把只停牌 7 个交易日的
    标的误判为「停牌过久」而静默剔除——恰好在长假后开盘首日损失候选。
    """
    dates = [20260918, 20260919, 20260922, 20260923, 20260924, 20260925,
             20260926, 20260929, 20260930]          # as_of = 20260930
    # 只停到 20260922：落后 20260923/24/25/26/29/30 共 6 个交易日 → 应保留
    short_suspend = [d for d in dates if d <= 20260922]
    # 停到 20260918：落后 8 个交易日 → 仍保留（阈值 10）
    assert len([d for d in dates if d > 20260922]) == 6
    assert len([d for d in dates if d > 20260918]) == 8
    # 旧口径用 int(YYYYMMDD) 相减：跨月必然误判（20261009-20260930=79>10），
    # 同月也可能漏判。用交易日计数则两种情况都稳定。
    assert 20261009 - 20260930 == 79
    assert len([d for d in dates if d > short_suspend[-1]]) == 6


def test_qfq_status_uses_loaded_events_not_path(tmp_path):
    """权息缓存路径存在但内容缺失 → 必须按**原始价**报告，不许宣称前复权。

    回归缺陷：load_events 对缺失文件返回 {}，而 screen.run 用
    `if events_cache`（路径非空）判断，报告印"（前复权）"而实际算原始价，
    ret20 被除权跳空污染却进入 tracking 校准基线。
    """
    empty_cache = tmp_path / "empty_events.csv"
    empty_cache.write_text("", encoding="utf-8")
    assert gbbq_reader.load_events(str(empty_cache)) == {}

    missing = str(tmp_path / "nonexistent.csv")
    assert gbbq_reader.load_events(missing) == {}
    # 两种情况下 events 都为空 → qfq_applied 必为 False（run 内部判定）


def test_due_exits_notices_extended_suspended_position(tmp_path):
    """端到端：停牌顺延的持仓，t20_date 落空会导致卖出提示永久漏报。

    回归缺陷：_ret_at 顺延态返回 date=None → t20_date 空 →
    _due_exits 的 `len(d) != 8: continue` 跳过 → 用户永远收不到卖出提醒。
    """
    lday = tmp_path / "vipdoc" / "sh" / "lday"
    lday.mkdir(parents=True)
    cal_dates = [20260101 + i for i in range(40)]
    _write_day(str(lday / "sh000001.day"), _flat_rows(cal_dates, close=3000.0))

    # 个股在 as_of 之后仍停牌：只有建仓日附近几根 bar
    stock = [20260101, 20260102, 20260103, 20260104]
    _write_day(str(lday / "sh600000.day"), _flat_rows(stock, close=10.0))

    track = tmp_path / "tracking.csv"
    with open(track, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["as_of", "code", "name", "score", "liq20",
                    "ret20", "vol20", "maxret20", "risk_flags"])
        w.writerow([20260101, "600000", "浦发银行", 0.9, 1e8,
                    -0.1, 0.02, 0.02, ""])

    filled = tmp_path / "tracking_filled.csv"
    backfill.run(str(tmp_path / "vipdoc"), str(track), str(filled))
    assert filled.exists()

    with open(filled, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows, "回填应产出至少一行"
    row = rows[0]
    # 关键断言：凡 status=filled 的行，到期日**不得为空**
    if row.get("t5_status") == "filled" or row.get("t20_status") == "filled":
        assert (row.get("t5_date") or row.get("t20_date") or "").strip(), (
            "已到期持仓的日期不得为空——否则 _due_exits 会静默跳过，"
            "用户永远收不到卖出提示")


# ---------------------------------------------------------------------------
# 2026-10-04 飞书推送改造回归
# 用户策略：**有异常才推**（正常产出静默）
# ---------------------------------------------------------------------------


def test_feishu_quiet_skips_when_no_exits(monkeypatch):
    """正常产出且无到期待卖 → 静默，不发消息（用户要求"有异常才推"）。"""
    sent = []
    monkeypatch.setattr(run_daily, "_feishu_post",
                        lambda w, c: sent.append(c) or True)
    payload = {"as_of": "20260930", "top": [
        {"code": "600000", "name": "浦发银行", "score": 0.9,
         "ret20": -0.1}],
        "universe": {"stocks_found": 5616, "scored": 3010}}
    assert run_daily.feishu_push("https://x", payload) is True
    assert sent == [], "静默模式下不应发出任何请求"


def test_feishu_pushes_when_exits_present(monkeypatch):
    """有到期待卖 → 必须推送，且卡片须含卖出段与逾期标注。"""
    sent = []
    monkeypatch.setattr(run_daily, "_feishu_post",
                        lambda w, c: sent.append(c) or True)
    payload = {
        "as_of": "20260930",
        "top": [{"code": "600000", "name": "浦发银行",
                 "score": 0.9, "ret20": -0.1}],
        "universe": {"stocks_found": 5616, "scored": 3010},
        "exits": [{"code": "000001", "name": "平安银行",
                   "t20_date": "20260925", "t20_ret": "-0.05",
                   "_overdue_days": 5}],
    }
    assert run_daily.feishu_push("https://x", payload) is True
    assert len(sent) == 1
    body = str(sent[0])
    assert "平安银行" in body
    assert "逾期 5 天" in body
    assert "到期待卖出" in body


def test_feishu_top_limits_rows(monkeypatch):
    """候选只列前 N 只（默认 5），避免手机上刷屏。"""
    sent = []
    monkeypatch.setattr(run_daily, "_feishu_post",
                        lambda w, c: sent.append(c) or True)
    top = [{"code": f"60000{i}", "name": f"股票{i}",
            "score": 0.9 - i / 100, "ret20": -0.1} for i in range(20)]
    payload = {"as_of": "20260930", "top": top,
               "universe": {"stocks_found": 5616, "scored": 3010},
               "feishu_quiet": False, "feishu_top": 5}
    assert run_daily.feishu_push("https://x", payload) is True
    body = str(sent[0])
    assert "股票0" in body
    assert "股票5" not in body, "第 6 只不应出现在卡片里"
    assert "共 20 只" in body


def test_read_webhook_priority(monkeypatch, tmp_path):
    """Webhook 读取优先级：命令行 > 环境变量 > 文件；文件缺失返回空。"""
    f = tmp_path / "wh.txt"
    f.write_text("https://from-file\n", encoding="utf-8")
    monkeypatch.setenv("TDX_FEISHU_WEBHOOK", "https://from-env")
    assert run_daily._read_webhook("https://from-cli", str(f)) == "https://from-cli"
    assert run_daily._read_webhook("", str(f)) == "https://from-env"
    monkeypatch.delenv("TDX_FEISHU_WEBHOOK")
    assert run_daily._read_webhook("", str(f)) == "https://from-file"
    assert run_daily._read_webhook("", str(tmp_path / "none.txt")) == ""


def test_feishu_alert_never_raises():
    """告警推送失败不得抛异常——它本身是最后一道防线。"""
    assert run_daily.feishu_alert("http://127.0.0.1:9/none", "测试",
                                   ["x"]) is False


# ---------------------------------------------------------------------------
# 2026-10-04 飞书推送改造回归
# 用户策略：**有异常才推**（正常产出静默）
# ---------------------------------------------------------------------------


def test_feishu_quiet_skips_when_no_exits(monkeypatch):
    """正常产出且无到期待卖 → 静默，不发消息（用户要求"有异常才推"）。"""
    sent = []
    monkeypatch.setattr(run_daily, "_feishu_post",
                        lambda w, c: sent.append(c) or True)
    payload = {"as_of": "20260930", "top": [
        {"code": "600000", "name": "浦发银行", "score": 0.9,
         "ret20": -0.1}],
        "universe": {"stocks_found": 5616, "scored": 3010}}
    assert run_daily.feishu_push("https://x", payload) is True
    assert sent == [], "静默模式下不应发出任何请求"


def test_feishu_pushes_when_exits_present(monkeypatch):
    """有到期待卖 → 必须推送，且卡片须含卖出段与逾期标注。"""
    sent = []
    monkeypatch.setattr(run_daily, "_feishu_post",
                        lambda w, c: sent.append(c) or True)
    payload = {
        "as_of": "20260930",
        "top": [{"code": "600000", "name": "浦发银行",
                 "score": 0.9, "ret20": -0.1}],
        "universe": {"stocks_found": 5616, "scored": 3010},
        "exits": [{"code": "000001", "name": "平安银行",
                   "t20_date": "20260925", "t20_ret": "-0.05",
                   "_overdue_days": 5}],
    }
    assert run_daily.feishu_push("https://x", payload) is True
    assert len(sent) == 1
    body = str(sent[0])
    assert "平安银行" in body
    assert "逾期 5 天" in body
    assert "到期待卖出" in body


def test_feishu_top_limits_rows(monkeypatch):
    """候选只列前 N 只（默认 5），避免手机上刷屏。"""
    sent = []
    monkeypatch.setattr(run_daily, "_feishu_post",
                        lambda w, c: sent.append(c) or True)
    top = [{"code": f"60000{i}", "name": f"股票{i}",
            "score": 0.9 - i / 100, "ret20": -0.1} for i in range(20)]
    payload = {"as_of": "20260930", "top": top,
               "universe": {"stocks_found": 5616, "scored": 3010},
               "feishu_quiet": False, "feishu_top": 5}
    assert run_daily.feishu_push("https://x", payload) is True
    body = str(sent[0])
    assert "股票0" in body
    assert "股票5" not in body, "第 6 只不应出现在卡片里"
    assert "共 20 只" in body


def test_read_webhook_priority(monkeypatch, tmp_path):
    """Webhook 读取优先级：命令行 > 环境变量 > 文件；文件缺失返回空。"""
    f = tmp_path / "wh.txt"
    f.write_text("https://from-file\n", encoding="utf-8")
    monkeypatch.setenv("TDX_FEISHU_WEBHOOK", "https://from-env")
    assert run_daily._read_webhook("https://from-cli", str(f)) == "https://from-cli"
    assert run_daily._read_webhook("", str(f)) == "https://from-env"
    monkeypatch.delenv("TDX_FEISHU_WEBHOOK")
    assert run_daily._read_webhook("", str(f)) == "https://from-file"
    assert run_daily._read_webhook("", str(tmp_path / "none.txt")) == ""


def test_feishu_alert_never_raises():
    """告警推送失败不得抛异常——它本身是最后一道防线。"""
    assert run_daily.feishu_alert("http://127.0.0.1:9/none", "测试",
                                   ["x"]) is False
