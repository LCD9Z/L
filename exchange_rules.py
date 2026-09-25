# -*- coding: utf-8 -*-
"""集中管理A股交易规则；优先使用数据源提供的逐日状态。

## 涨跌幅限制的派生（2026-09-19 新增）

此前 ``limit_ratio`` 只认「数据源给的逐日字段」，没有就退回**板块默认值**
（主板 10% / 创业科创 20% / 北交所 30%）。这漏掉了 **ST 股票**这一档：
主板风险警示股长期为 ±5%，2026-07-06 起才放宽至 ±10%。

后果是**单向乐观偏差**：主板 ST 股票真实涨停（+5% 一字板，买不进）时，
按 10% 判定不构成涨停 → 回测会"买到"实际买不到的票。
详见 `ALPHA_CAPABILITY_GAP_ANALYSIS.md` §4 P0-4。

:func:`derive_limit_ratio` 补上这一档，并且是**时变**的 ——
数据集横跨 2016~2026，两个时代的规则必须分开算。
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from ashare.ashare_market import board_of, default_limit_ratio

# --- 涨跌幅规则常量（有权威出处；改动必须同步更新出处与测试）-------------
#
# 沪深主板 ST/*ST：**2026-07-06 起由 ±5% 放宽至 ±10%**，与主板其他股票一致。
#   出处：沪深北交易所 2026-07-06 同步施行的交易规则修订
#   （同步调整盘后固定价格交易范围、沪市基金尾盘集合竞价、创业板做市商等）。
# 创业板 / 科创板 风险警示股：±20%（此前已统一，本次未变）。
# 北交所：±30%（本次未变）。
ST_LIMIT_CHANGE_DATE = "2026-07-06"
ST_LIMIT_RATIO_BEFORE = 0.05
ST_LIMIT_RATIO_AFTER = 0.10

# 创业板涨跌幅由 ±10% 放宽至 ±20% 的生效日。
#   出处：深交所创业板改革并试点注册制，2020-08-24 起新上市及存量股票统一 ±20%。
#   ⚠️ 此前本函数对创业板**无条件返回 0.20**，等于把当前规则**追溯**到 2016 年 ——
#   2026-09-25 实测：创业板 2,121,218 行中 **738,070 行（34.8%）** 涨跌幅被高估，
#   涉及 834 只。后果是「一字板不可买」检查在该期间**失效**（10% 涨停被当作
#   未触及 20% 阈值），使回测在该段偏乐观。这是 **PIT 违规**，不是近似。
CHINEXT_20PCT_DATE = "2020-08-24"
CHINEXT_RATIO_BEFORE = 0.10        # 改革前：普通股 ±10%
CHINEXT_ST_RATIO_BEFORE = 0.05     # 改革前：风险警示股 ±5%（与其他板块一致）
CHINEXT_RATIO_AFTER = 0.20


def is_st_flag(value) -> bool:
    """把 ``is_st`` 的各种表示解析为布尔。

    必须显式解析：数据源里它是 ``"0"`` / ``"1"`` 字符串，
    而 ``bool("0")`` 为 ``True`` —— 直接用真值判断会把**全部股票**误判为 ST，
    进而把主板涨跌幅从 10% 误设成 5%。
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "t", "yes", "y", "是")


def derive_limit_ratio(code: str, *, is_st: bool = False,
                       trade_date: Optional[str] = None) -> Tuple[float, str]:
    """由 **板块 + 逐日 ST 状态 + 交易日** 派生涨跌幅限制。

    返回 ``(ratio, basis)``；``basis`` 记录派生依据，便于逐行审计：

    ====================  ============================================
    basis                 含义
    ====================  ============================================
    ``board``             非 ST；或科创板/北交所（其 ST 与普通股同幅度）；
                          或创业板且交易日为 2020-08-24 及之后 → 20%
    ``board_chinext_legacy`` 创业板非 ST 且交易日早于 2020-08-24 → 10%
    ``board_chinext_st_legacy`` 创业板 ST 且交易日早于 2020-08-24 → 5%
    ``board_st_legacy``   主板 ST 且交易日早于 2026-07-06 → 5%
    ``board_st``          主板 ST 且交易日为 2026-07-06 及之后 → 10%
    ====================  ============================================

    **不覆盖的例外**（必须随结论声明，不得当作已处理）：

    * 新股上市后**前 5 个交易日不设涨跌幅限制**；
    * **退市整理期**股票的特别规定；
    * 重大资产重组复牌首日等临时安排。

    这些情形下本函数返回的是板块默认值 —— 是**近似**而非正确值。
    若数据源能提供逐日 ``limit_ratio`` 字段，:func:`limit_ratio` 会优先采用它。
    """
    board = board_of(code)
    if board == "科创板":
        return 0.20, "board"          # 2019-07-22 开板即 ±20%，无需分段
    if board == "创业板":
        # 2020-08-24 起 ±20%（ST 与普通股同幅度）；此前普通股 ±10%、ST ±5%。
        # **必须按交易日分段**，否则是 PIT 违规（见上方常量注释）。
        if trade_date is not None and str(trade_date) < CHINEXT_20PCT_DATE:
            if is_st:
                return CHINEXT_ST_RATIO_BEFORE, "board_chinext_st_legacy"
            return CHINEXT_RATIO_BEFORE, "board_chinext_legacy"
        return CHINEXT_RATIO_AFTER, "board"
    if board == "北交所":
        return 0.30, "board"
    if not is_st:
        return default_limit_ratio(code), "board"
    if trade_date is not None and str(trade_date) < ST_LIMIT_CHANGE_DATE:
        return ST_LIMIT_RATIO_BEFORE, "board_st_legacy"
    return ST_LIMIT_RATIO_AFTER, "board_st"


def limit_ratio(code, bar=None):
    if bar:
        for k in ('limit_ratio', 'limit_pct'):
            if bar.get(k) is not None:
                v = float(bar[k]); return v/100 if v > 1 else v
        # 数据源未给逐日字段时，用板块 + 逐日 ST 状态 + 交易日派生（见
        # derive_limit_ratio）。仍属近似：不覆盖新股前 5 日与退市整理期。
        return derive_limit_ratio(
            str(code), is_st=is_st_flag(bar.get('is_st')),
            trade_date=bar.get('date') or bar.get('trade_date'),
        )[0]
    c = str(code).zfill(6)
    return default_limit_ratio(c)


def limit_prices(prev_close, code, bar=None, tick='0.01'):
    if not prev_close or float(prev_close) <= 0: return None, None
    p = Decimal(str(prev_close)); r = Decimal(str(limit_ratio(code, bar))); q = Decimal(str(tick))
    up = (p*(Decimal('1')+r)).quantize(q, rounding=ROUND_HALF_UP)
    down = (p*(Decimal('1')-r)).quantize(q, rounding=ROUND_HALF_UP)
    return float(up), float(down)
