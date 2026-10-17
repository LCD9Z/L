# -*- coding: utf-8 -*-
"""`run_contrarian_portfolio` 交易日感知成本守卫（缺陷 #16）。

背景（改动前先核对，勿凭记忆调整数值）：
- 印花税分段生效日 **2023-08-28**：此前卖出单边 **1‰**、此后 **0.5‰**
  （`backtest_engine._stamp_rate`）。
- **缺陷 #16**（2026-10-17 登记）：`scripts/run_contrarian_portfolio._trade_return`
  调用 `_trade_cost` 时**未传 `trade_date`** ⇒ `_stamp_rate` 走「未提供日期 → 现行税率」
  分支 ⇒ 跨线卖出恒按 0.5‰ ⇒ **单边成本低估 0.5‰**（修复前后均错，与 D1 独立）。
- **修复**：买入传 `str(entry_bar["date"])`、卖出传 `str(exit_bar["date"])`
  （与 `walk_forward` / `portfolio_backtest` 同形态）。
- **反向验证（已做，留痕见提交信息）**：把两处调用改回不传日期后，
  `test_trade_return_passes_trade_dates` 与 `test_trade_return_reflects_change_date`
  必须失败；修复后全过。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest_engine import Costs, _trade_cost  # noqa: E402


def _load(module_name: str, rel_path: str):
    """按**文件路径**加载被测模块（避免 ``scripts.`` 包名让 mypy 重复识别）。"""
    spec = importlib.util.spec_from_file_location(module_name, ROOT / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


cmod = _load("_run_contrarian_portfolio_under_test",
             "scripts/run_contrarian_portfolio.py")

HORIZON = cmod.HORIZON


def _make_bars(entry_date: str, exit_date: str, price: float = 10.0):
    """构造最小 bars：i=0 时 entry=bars[1]、exit=bars[1+HORIZON]。"""
    n = 1 + HORIZON + 1
    bars = [
        {"date": f"2023-07-{d:02d}", "open": price, "close": price,
         "high": price, "low": price}
        for d in range(1, n + 1)
    ]
    bars[1] = {"date": entry_date, "open": price, "close": price,
               "high": price, "low": price}
    bars[1 + HORIZON] = {"date": exit_date, "open": price, "close": price,
                         "high": price, "low": price}
    return bars


def test_trade_return_passes_trade_dates(monkeypatch):
    """缺陷 #16 守卫：买入必须带 entry 日期、卖出必须带 exit 日期。"""
    seen = []

    def _spy(notional, side, costs, trade_date=None):
        seen.append((side, trade_date))
        return 0.0

    monkeypatch.setattr(cmod, "_trade_cost", _spy)
    ret = cmod._trade_return(
        _make_bars("2023-08-21", "2023-08-25"), 0, Costs(), 100_000.0
    )
    assert ret is not None
    assert ("buy", "2023-08-21") in seen, f"买入未传 entry 日期：{seen}"
    assert ("sell", "2023-08-25") in seen, f"卖出未传 exit 日期（缺陷 #16 复发）：{seen}"


def test_sell_cost_before_change_is_higher():
    """跨线卖出（2023-08-25）比线后（2023-08-29）高 0.5‰ × 名义金。"""
    c, gross = Costs(), 100_000.0
    before = _trade_cost(gross, "sell", c, "2023-08-25")
    after = _trade_cost(gross, "sell", c, "2023-08-29")
    # 佣金同一档（0.03% = 30 元 > 5 元保底）⇒ 差额纯为印花税 0.5‰ = 50 元
    assert before - after == pytest.approx(gross * 0.0005)
    assert before > after


def test_trade_return_reflects_change_date():
    """同一价格路径、仅卖出日不同 ⇒ 线前收益更低（成本更高）。"""
    before = cmod._trade_return(
        _make_bars("2023-08-21", "2023-08-25"), 0, Costs(), 100_000.0
    )
    after = cmod._trade_return(
        _make_bars("2023-08-21", "2023-08-29"), 0, Costs(), 100_000.0
    )
    assert before is not None and after is not None
    assert before < after, "卖出日跨线但收益相同 ⇒ 未按交易日分段计费（缺陷 #16）"
