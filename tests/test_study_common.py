# -*- coding: utf-8 -*-
"""``scripts/_study_common.py`` 的**行为等价性**守卫（CODE_REDUNDANCY_AUDIT P2）。

收敛不是「看起来一样」：本测试用同一份夹具，把统一函数与**逐字复制的原实现**
（A 族 4 站点 / B 族 2 站点的 ``_load``，以及 4 对 ×2 helper）逐一比对，
防止参数化过程中任何行为漂移（尤其是抽样步长、错误跳过、行数过滤三类差异）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from _study_common import (  # noqa: E402
    load_certified_stocks,
    load_codes,
    make_filter,
    pct_rank,
    pool_codes,
)

# ---------------------------------------------------------------------------
# 夹具：一个最小「已认证数据集」
#   000001 / 600519：250 行、元数据正确（正常样本）
#   000003：50 行（短历史，低于 B 族 min_rows=200）
#   000004：元数据 sha256 错误（加载必抛 → A 族跳过 / B 族抛出）
#   abc.csv：非数字名（A 族 digits_only 过滤掉，B 族不过滤但无对应 metadata）
# ---------------------------------------------------------------------------
def _write_stock(d: Path, code: str, n_rows: int, *, break_meta: bool = False) -> None:
    import datetime as _dt
    import hashlib

    rows = ["date,open,close,high,low,volume,amount"]
    base = _dt.date(2024, 1, 1)
    for i in range(n_rows):
        rows.append(f"{base + _dt.timedelta(days=i)},10.0,10.5,11.0,9.5,1000,10500.0")
    p = d / f"{code}.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    meta: Dict[str, Any] = {"strict": True, "rows": n_rows}
    if break_meta:
        meta["sha256"] = "0" * 64
    else:
        meta["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (d / f"{code}.metadata.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture()
def dataset(tmp_path: Path) -> str:
    ds = tmp_path / "ds"
    stocks = ds / "stocks"
    stocks.mkdir(parents=True)
    _write_stock(stocks, "000001", 250)
    _write_stock(stocks, "000003", 50)
    _write_stock(stocks, "000004", 250, break_meta=True)
    _write_stock(stocks, "600519", 250)
    (stocks / "abc.csv").write_text("date,open\n2024-01-01,1\n", encoding="utf-8")  # 无 metadata
    (ds / "pit_universe.json").write_text(json.dumps(
        {"snapshots": {"2024-01-01": ["000001", "600519", "999999"], "2024-06-03": ["000003"]}}
    ), encoding="utf-8")
    return str(ds)


@pytest.fixture()
def clean_dataset(tmp_path: Path) -> str:
    """无坏元数据股票的数据集（B 族 skip_errors=False 也能全程跑通）。"""
    ds = tmp_path / "ds_clean"
    stocks = ds / "stocks"
    stocks.mkdir(parents=True)
    _write_stock(stocks, "000001", 250)
    _write_stock(stocks, "000003", 50)
    _write_stock(stocks, "600519", 250)
    return str(ds)


# ---------------------------------------------------------------------------
# 原实现的逐字副本（等价性基准）—— 来自审计 §3.1 #1 / §3.2 的位置
# ---------------------------------------------------------------------------
def _ref_load_a(dataset: str, max_stocks: int) -> Dict[str, List[Dict[str, Any]]]:
    """A 族（run_expert_filter_study:68 等 4 处）：digits_only + 跳过异常。"""
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                   if f.endswith(".csv") and f[:-4].isdigit())
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    out: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        try:
            out[c] = load_certified_csv(p, m)
        except Exception:
            continue
    return out


def _ref_load_b(dataset: str, max_stocks: int, min_rows: int = 200) -> Dict[str, Any]:
    """B 族（run_contrarian_portfolio:59 等 2 处）：不收数字过滤、不跳异常、min_rows=200。"""
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    data: Dict[str, Any] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        bars = load_certified_csv(p, m)
        if len(bars) >= min_rows:
            data[c] = bars
    return data


def test_load_matches_a_family_full(dataset: str):
    assert load_certified_stocks(dataset, 0) == _ref_load_a(dataset, 0)


def test_load_matches_a_family_sampled(dataset: str):
    """max_stocks 抽样的等步长 picks 必须逐码一致（000004 坏元数据被 A 族跳过）。"""
    assert load_certified_stocks(dataset, 2) == _ref_load_a(dataset, 2)


def test_load_matches_b_family_full(clean_dataset: str):
    assert load_certified_stocks(clean_dataset, 0, min_rows=200, digits_only=False,
                                 skip_errors=False) == _ref_load_b(clean_dataset, 0)


def test_load_b_family_raises_on_broken_meta(dataset: str):
    """B 族语义：坏元数据**抛出**（不静默跳过）——000004 命中，且与原实现同抛。"""
    with pytest.raises(ValueError, match="sha256"):
        load_certified_stocks(dataset, 0, min_rows=1, digits_only=False, skip_errors=False)
    with pytest.raises(ValueError, match="sha256"):
        _ref_load_b(dataset, 0, 1)


def test_load_b_family_min_rows_filters_short_history(clean_dataset: str):
    got = load_certified_stocks(clean_dataset, 0, min_rows=200, digits_only=False, skip_errors=False)
    assert "000003" not in got, "50 行短历史须被 min_rows=200 过滤"
    assert {"000001", "600519"} <= set(got)


def test_pool_codes_matches_original(dataset: str):
    """吸收 run_concentration_study:64 / run_universe_replication:47。"""
    d = os.path.join(dataset, "stocks")
    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as f:
        snaps = json.load(f)["snapshots"]
    pool: set = set()
    for v in snaps.values():
        pool.update(v)
    want = sorted(c for c in pool
                  if os.path.exists(os.path.join(d, f"{c}.csv"))
                  and os.path.exists(os.path.join(d, f"{c}.metadata.json")))
    assert pool_codes(dataset) == want == ["000001", "000003", "600519"]


def test_load_codes_matches_original(dataset: str):
    """吸收 run_concentration_study:76 / run_universe_replication:60。"""
    from real_alpha_pipeline import load_certified_csv

    d = os.path.join(dataset, "stocks")
    ref: Dict[str, Any] = {}
    for c in ("000001", "999999"):
        p, m = os.path.join(d, f"{c}.csv"), os.path.join(d, f"{c}.metadata.json")
        if os.path.exists(p) and os.path.exists(m):
            ref[c] = load_certified_csv(p, m)
    assert load_codes(dataset, ("000001", "999999")) == ref


def test_make_filter_matches_original():
    """吸收 run_tail_exclusion_study:148 / run_universe_replication:102。"""
    excl = {"momentum": {"2024-01-02": {"000001", "600519"}}}
    flt = make_filter(excl, ["momentum"])
    assert flt is not None
    assert flt("000001", [], "2024-01-02") is False
    assert flt("000003", [], "2024-01-02") is True
    assert flt("000001", [], "2024-01-03") is True, "无该日排除记录 ⇒ 通过"
    assert make_filter(excl, []) is None, "factors 为空 ⇒ None（调用方跳过过滤步）"


def test_pct_rank_matches_original():
    """吸收 run_contrarian_portfolio:79 / run_contrarian_study:75。"""
    def ref(values: Sequence[float]) -> List[float]:
        n = len(values)
        if n <= 1:
            return [0.5] * n
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        for pos, i in enumerate(order):
            out[i] = pos / (n - 1)
        return out

    assert pct_rank([]) == []
    assert pct_rank([3.0]) == [0.5]
    assert pct_rank([10.0, 20.0, 30.0]) == [0.0, 0.5, 1.0]
    for vals in ([5.0, 1.0, 5.0, 2.0], [0.1, -7.0, 3.3]):
        assert pct_rank(vals) == ref(vals)
