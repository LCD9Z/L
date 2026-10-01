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
    # 且存在「严格晚于建仓日 20260102」的最后一根（20260103）可回溯
    bars_susp = dict(bars, **{"20260103": {"close": 11.0}})
    assert backfill._ret_at(cal, bars_susp, 0, 4, "20260102", 10.5) == (
        None, 11.0, 11.0 / 10.5 - 1, None)

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


def test_due_exits_only_matches_today(tmp_path):
    """只有 t20_date == today 的持仓算「今日到期」；未到期的不进清单。"""
    p = str(tmp_path / "filled.csv")
    _write_filled(p, [
        ("20260601", "600000", "浦发银行", "20260630", "-0.050000"),
        ("20260601", "000001", "平安银行", "20260701", "0.010000"),
        ("20260601", "300750", "宁德时代", "", ""),          # 未到期
    ])
    got = run_daily._due_exits(p, "20260630")
    assert [r["code"] for r in got] == ["600000"]


def test_due_exits_empty_today_returns_empty(tmp_path):
    """没有当天到期的持仓 → 空清单（不该误报）。"""
    p = str(tmp_path / "filled.csv")
    _write_filled(p, [("20260601", "600000", "浦发银行", "20260630", "-0.05")])
    assert run_daily._due_exits(p, "20260701") == []


def test_due_exits_missing_file_returns_empty(tmp_path):
    """回填产物不存在时不抛错（首次运行 / 数据未更新被跳过的场景）。"""
    assert run_daily._due_exits(str(tmp_path / "nope.csv"), "20260630") == []


def test_export_exits_writes_table_with_return(tmp_path):
    """有到期持仓时写出表格，且收益按百分比格式呈现。"""
    rows = [{"code": "600000", "name": "浦发银行", "t1_date": "20260602",
             "t1_open": "10.0000", "t20_ret": "-0.050000", "risk_flags": ""}]
    p = run_daily.export_exits(rows, str(tmp_path), "20260630")
    text = open(p, encoding="utf-8").read()
    assert "600000" in text
    assert "-5.00%" in text
    assert "不构成投资建议" in text


def test_export_exits_empty_writes_notice(tmp_path):
    """无到期持仓时明确写「今日无到期持仓」，而不是留空文件。"""
    p = run_daily.export_exits([], str(tmp_path), "20260701")
    text = open(p, encoding="utf-8").read()
    assert "今日无到期持仓" in text
