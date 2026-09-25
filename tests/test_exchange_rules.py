# -*- coding: utf-8 -*-
"""A股涨跌幅限制派生规则的守卫（2026-09-19 新增）。

## 为什么需要这组测试

主板 ST/*ST 股票的涨跌幅长期为 ±5%，**2026-07-06 起放宽至 ±10%**。
数据集横跨 2016~2026，两个时代的规则必须分开算。

漏掉这一档会产生**单向乐观偏差**：主板 ST 股票真实涨停（+5% 一字板、
买不进）时，按 10% 判定不构成涨停 → 回测会"买到"实际买不到的票。
偏差方向是**高估**策略收益，属于最危险的一类错误。

出处：沪深北交易所 2026-07-06 同步施行的交易规则修订
（主板风险警示股涨跌幅 5% → 10%；创业板/科创板 ST 维持 20%；北交所 30%）。
"""
import pytest

from exchange_rules import (
    ST_LIMIT_CHANGE_DATE,
    ST_LIMIT_RATIO_AFTER,
    ST_LIMIT_RATIO_BEFORE,
    derive_limit_ratio,
    is_st_flag,
    limit_prices,
    limit_ratio,
)

BEFORE = "2026-07-03"   # 变更生效前最后一个交易日
AFTER = "2026-07-06"    # 变更生效日


# ---------------------------------------------------------------------------
# is_st_flag —— "0" 是字符串，bool("0") 为 True，必须显式解析
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("0", False), ("1", True), (0, False), (1, True),
    (0.0, False), (1.0, True), (False, False), (True, True),
    ("true", True), ("false", False), ("是", True), ("", False),
    (None, False), (" 1 ", True),
])
def test_is_st_flag_parses_all_representations(value, expected):
    assert is_st_flag(value) is expected


def test_is_st_flag_does_not_use_raw_truthiness():
    """回归守卫：``bool("0")`` 为 True，若实现退回真值判断会在这里失败。"""
    assert bool("0") is True
    assert is_st_flag("0") is False


# ---------------------------------------------------------------------------
# 板块 × ST × 日期
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", ["600000", "601398", "603259", "605499",
                                  "000001", "001979", "002594", "003816"])
def test_main_board_non_st_is_ten_percent(code):
    ratio, basis = derive_limit_ratio(code, is_st=False, trade_date=BEFORE)
    assert ratio == pytest.approx(0.10)
    assert basis == "board"


@pytest.mark.parametrize("code", ["600000", "000001"])
def test_main_board_st_before_change_is_five_percent(code):
    """变更生效前：主板 ST 为 ±5% —— 这是此前实现漏掉的一档。"""
    ratio, basis = derive_limit_ratio(code, is_st=True, trade_date=BEFORE)
    assert ratio == pytest.approx(ST_LIMIT_RATIO_BEFORE)
    assert ratio == pytest.approx(0.05)
    assert basis == "board_st_legacy"


@pytest.mark.parametrize("code", ["600000", "000001"])
def test_main_board_st_after_change_is_ten_percent(code):
    ratio, basis = derive_limit_ratio(code, is_st=True, trade_date=AFTER)
    assert ratio == pytest.approx(ST_LIMIT_RATIO_AFTER)
    assert ratio == pytest.approx(0.10)
    assert basis == "board_st"


def test_st_ratio_is_piecewise_at_the_effective_date():
    before, _ = derive_limit_ratio("600000", is_st=True, trade_date=BEFORE)
    after, _ = derive_limit_ratio("600000", is_st=True, trade_date=AFTER)
    assert before != after
    assert ST_LIMIT_CHANGE_DATE == "2026-07-06"
    assert BEFORE < ST_LIMIT_CHANGE_DATE <= AFTER


def test_st_flag_is_ignored_when_no_trade_date_given():
    """缺交易日时按**现行**规则（10%）—— 不能默默退回 5%。"""
    ratio, basis = derive_limit_ratio("600000", is_st=True, trade_date=None)
    assert ratio == pytest.approx(ST_LIMIT_RATIO_AFTER)
    assert basis == "board_st"


@pytest.mark.parametrize("code", ["300750", "301236", "688981", "688111"])
def test_growth_and_star_board_are_twenty_percent(code):
    for is_st in (False, True):
        ratio, basis = derive_limit_ratio(code, is_st=is_st, trade_date=BEFORE)
        assert ratio == pytest.approx(0.20)
        assert basis == "board"


@pytest.mark.parametrize("code", ["830799", "430047", "920000"])
def test_bse_is_thirty_percent(code):
    for is_st in (False, True):
        ratio, _ = derive_limit_ratio(code, is_st=is_st, trade_date=BEFORE)
        assert ratio == pytest.approx(0.30)


def test_st_never_widens_growth_board_limit():
    """创业板/科创板 ST 与普通股同为 20%，不得被 ST 分支改成 5%/10%。"""
    for date in (BEFORE, AFTER):
        ratio, _ = derive_limit_ratio("300750", is_st=True, trade_date=date)
        assert ratio == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# limit_ratio（bar 级优先，其次派生）
# ---------------------------------------------------------------------------

def test_explicit_bar_field_wins_over_derivation():
    """数据源给了逐日字段时必须以它为准（那是权威值）。"""
    bar = {"date": BEFORE, "is_st": "1", "limit_ratio": 0.20}
    assert limit_ratio("600000", bar) == pytest.approx(0.20)


def test_bar_limit_pct_above_one_is_treated_as_percent():
    bar = {"date": BEFORE, "limit_pct": 20}
    assert limit_ratio("600000", bar) == pytest.approx(0.20)


def test_bar_without_explicit_field_derives_from_st():
    """回归守卫：修复前这里会返回板块默认 0.10，把 ST 的 5% 涨跌停漏判。"""
    bar = {"date": BEFORE, "is_st": "1"}
    assert limit_ratio("600000", bar) == pytest.approx(0.05)
    bar_after = {"date": AFTER, "is_st": "1"}
    assert limit_ratio("600000", bar_after) == pytest.approx(0.10)


def test_bar_is_st_zero_string_does_not_trigger_st_rule():
    bar = {"date": BEFORE, "is_st": "0"}
    assert limit_ratio("600000", bar) == pytest.approx(0.10)


def test_no_bar_falls_back_to_board_default():
    assert limit_ratio("600000") == pytest.approx(0.10)
    assert limit_ratio("300750") == pytest.approx(0.20)
    assert limit_ratio("830799") == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# 涨跌停价（含 ST 档）
# ---------------------------------------------------------------------------

def test_limit_prices_use_st_ratio_for_main_board_st():
    """前收 10 元的主板 ST（变更前）：涨停 10.50、跌停 9.50。"""
    bar = {"date": BEFORE, "is_st": "1"}
    up, down = limit_prices(10.0, "600000", bar)
    assert up == pytest.approx(10.50)
    assert down == pytest.approx(9.50)


def test_limit_prices_use_ten_percent_after_change():
    bar = {"date": AFTER, "is_st": "1"}
    up, down = limit_prices(10.0, "600000", bar)
    assert up == pytest.approx(11.00)
    assert down == pytest.approx(9.00)


def test_limit_prices_round_half_up_to_cent():
    """非整数前收必须按分位四舍五入，不能截断。"""
    bar = {"date": BEFORE, "is_st": "0"}
    up, down = limit_prices(3.33, "600000", bar)
    assert up == pytest.approx(3.66)
    assert down == pytest.approx(3.00)


def test_limit_prices_reject_invalid_prev_close():
    assert limit_prices(0, "600000") == (None, None)
    assert limit_prices(None, "600000") == (None, None)
    assert limit_prices(-1.0, "600000") == (None, None)


# ---------------------------------------------------------------------------
# 回归守卫：创业板涨跌幅必须**按交易日分段**，不得把当前规则追溯
#
# 2026-09-25 实测缺陷：`derive_limit_ratio` 对创业板**无条件返回 0.20**，
# 等于把 2020-08-24 起才生效的 ±20% 追溯到了 2016 年。
# 量化：创业板 2,121,218 行中 **738,070 行（34.8%）** 涨跌幅被高估，涉及 834 只。
#
# 后果不是"近似"而是**偏乐观**：该期间 10% 涨停的「一字板」不会被
# 「涨跌停不可买」检查拦住（10% < 20% 阈值），回测因而多吃了本不可成交的成交。
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("date,expected,basis", [
    ("2016-01-04", 0.10, "board_chinext_legacy"),   # 创业板改革前
    ("2020-08-21", 0.10, "board_chinext_legacy"),   # 生效日前最后交易日（周五）
    ("2020-08-24", 0.20, "board"),                  # 生效日当天
    ("2024-06-03", 0.20, "board"),
])
def test_chinext_limit_ratio_is_date_aware(date, expected, basis):
    ratio, got_basis = derive_limit_ratio("300001", is_st=False, trade_date=date)
    assert (ratio, got_basis) == (expected, basis)


def test_chinext_without_trade_date_assumes_current_rule():
    """未给交易日时退回当前规则（20%）—— 调用方应尽量传日期。"""
    ratio, basis = derive_limit_ratio("300001")
    assert (ratio, basis) == (0.20, "board")


def test_star_market_is_20pct_regardless_of_date():
    """科创板 2019-07-22 开板即 ±20%，无需分段。"""
    for d in ("2019-07-22", "2024-06-03"):
        assert derive_limit_ratio("688001", trade_date=d) == (0.20, "board")


def test_chinext_st_is_20pct_after_change_date():
    """创业板 ST 与普通股同幅度（改革后 ±20%）。"""
    assert derive_limit_ratio("300001", is_st=True, trade_date="2024-06-03")[0] == 0.20


def test_chinext_st_before_change_date_is_5pct():
    """改革前创业板风险警示股为 ±5%（与其他板块 ST 一致）。"""
    ratio, basis = derive_limit_ratio("300001", is_st=True, trade_date="2019-05-06")
    assert (ratio, basis) == (0.05, "board_chinext_st_legacy")
