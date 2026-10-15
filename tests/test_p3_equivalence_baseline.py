# -*- coding: utf-8 -*-
"""P3 参数化改造的**行为锁定测试**（characterization test）。

**为什么需要**：审计 P3 要收敛 3 组同构函数（`_rank ×6` / `fetch_all_*` /
`board_of ×2`）。改造前后**行为必须逐值一致** —— 本文件先把**当前行为**钉死，
改造后同一套断言仍须通过（否则改造引入了行为漂移）。

**写法说明**：这类测试**刻意不依赖实现细节**（不断言内部结构），只断言
「输入 → 输出」；因此改造（提取公共函数）不会让它变红，而**行为变化会让它变红**。

参见 `P3_PARAMETERIZATION_PLAN.md` §二。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(rel: str, name: str):
    """按路径加载模块（scripts/ 下的模块不走包导入）。"""
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 组 2：_rank ×6（平均秩，处理并列）
# ---------------------------------------------------------------------------
RANK_CASES: List[List[float]] = [
    [3.0, 1.0, 1.0, 2.0],           # 并列（唯一易错点）
    [1.0, 2.0, 3.0, 4.0],           # 无并列
    [5.0, 5.0, 5.0],                # 全并列
    [-1.5, 0.0, -1.5, 2.5, 2.5],    # 负值 + 多组并列
    [42.0],                         # 单元素
    [],                             # 空
]


def _rank_sites() -> List[tuple]:
    """(标签, 可调用) 列表 —— 覆盖 6 处实现。"""
    sites: List[tuple] = []
    sites.append(("factor_ic_lab._rank", _load("factors/factor_ic_lab.py",
                                               "_rl")._rank))
    for rel, mod_name, attr in [
        ("scripts/evaluate_form_screen.py", "_efs", "_ranks"),
        ("scripts/factor_corr_by_window.py", "_fcbw", "_rank"),
        ("scripts/run_factor_orthogonality.py", "_rfo", "_rank"),
        ("scripts/run_tdx_universe_ic.py", "_rtui", "_rank"),
        ("scripts/run_xsrc_ic.py", "_rxi", "_rank"),
    ]:
        mod = _load(rel, mod_name)
        if hasattr(mod, attr):
            sites.append((f"{rel}:{attr}", getattr(mod, attr)))
    return sites


def test_rank_sites_all_present():
    """6 处实现都应可加载（防改造时漏改/误删）。"""
    sites = _rank_sites()
    assert len(sites) >= 6, f"仅加载到 {len(sites)} 处：{[s[0] for s in sites]}"


@pytest.mark.parametrize("values", RANK_CASES, ids=lambda v: f"n{len(v)}")
def test_rank_sites_agree(values: List[float]):
    """⚠️ 核心：6 处实现对同一输入必须给出**逐元素相同**的秩。

    改造（统一为一份实现）后本测试仍须通过 —— 它锁定的是**行为**而非实现。
    """
    results = {label: fn(list(values)) for label, fn in _rank_sites()}
    base_label, base = next(iter(results.items()))
    for label, got in results.items():
        assert got == base, (
            f"{label} 与 {base_label} 不一致：\n  {got}\n  {base}\n"
            f"（输入 {values}）"
        )


def test_rank_handles_ties_by_average():
    """并列值取**平均秩**（1-based）—— 改造若改用 `sorted` 索引会在此失败。"""
    fn = _load("factors/factor_ic_lab.py", "_rl2")._rank
    # [3,1,1,2]：1 与 1 并列占秩 1、2 → 平均 1.5；2 占秩 3；3 占秩 4
    assert fn([3.0, 1.0, 1.0, 2.0]) == [4.0, 1.5, 1.5, 3.0]


# ---------------------------------------------------------------------------
# 组 5：board_of ×2（板块归属）
# ---------------------------------------------------------------------------
BOARD_CASES = [
    ("600519", "sh_main"), ("601398", "sh_main"), ("603259", "sh_main"),
    ("605499", "sh_main"),
    ("688981", "star"), ("689009", "star"),
    ("000001", "sz_main"), ("001979", "sz_main"), ("002594", "sz_main"),
    ("003816", "sz_main"),
    ("300750", "chinext"), ("301236", "chinext"),
    ("920000", "bse"), ("830799", "bse"), ("430047", "bse"),
]


def test_board_of_sites_agree():
    """⚠️ 两处 `board_of` 对全部前缀必须给出相同板块（改造后仍须一致）。"""
    a = _load("tdx/tdx_csv_adapter.py", "_tca").board_of
    b = _load("tdx_native/day_reader.py", "_dr").board_of
    for code, expect in BOARD_CASES:
        ga, gb = a(code), b(code)
        assert ga == gb == expect, f"{code}: tdx={ga} tdx_native={gb} 期望={expect}"


def test_board_of_zero_pads_short_codes():
    """短代码须零填充到 6 位（`1` → `000001` → sz_main）。"""
    a = _load("tdx/tdx_csv_adapter.py", "_tca2").board_of
    assert a("1") == "sz_main"
    assert a("600519") == "sh_main"


def test_board_of_third_site_is_a_distinct_value_domain():
    """⚠️ 第三处 `board_of`（ashare/ashare_market.py）是**另一个值域**（中文板块名）。

    审计只列了 2 处，实际有 3 处。第一处返回中文名且**含 B 股分类**，
    与 tdx/tdx_native 的英文短码**不是同一函数语义** —— 因此组 5 只能
    收敛 ②③，**不可三合一**。本测试钉死该结论，防止后来者误合并。
    """
    ashare = _load("ashare/ashare_market.py", "_am").board_of
    tdx = _load("tdx/tdx_csv_adapter.py", "_tca3").board_of
    # 值域互不相交：中文名 vs 英文短码
    for code in ("600519", "300750", "688981", "920000"):
        assert ashare(code) != tdx(code), f"{code}: 两个值域不应相同"
    # ashare 侧独有的 B 股分类
    assert ashare("900901") == "沪B股"
    assert ashare("200011") == "深B股"


def test_board_of_known_divergences_locked():
    """锁定 ②③ 的**已知静默错误分类**（characterization：记录现状，不代表正确）。

    ⚠️ 这些是**待决缺陷**，不是期望行为。改造时若顺手修了，本测试会变红 ——
    变红即提示「行为已变更，须人工确认影响面」。
    参见 `P3_PARAMETERIZATION_PLAN.md` §组5 修正。
    """
    tdx = _load("tdx/tdx_csv_adapter.py", "_tca4").board_of
    # ① B 股被当成北交所（900/200 不在任何前缀列表 → 落 default "bse"）
    assert tdx("900901") == "bse", "B 股误判为北交所的现状已改变，须评估影响面"
    assert tdx("200011") == "bse"
    # ② 带市场前缀的代码无法识别（只做 zfill，不剥离 sh/sz/bj）
    assert tdx("sh600519") == "bse", "带前缀代码的现状已改变，须评估影响面"
    # ③ 689（科创板 CDR）在 ashare 侧漏判，落「其他A股」
    ashare = _load("ashare/ashare_market.py", "_am2").board_of
    assert ashare("689009") == "其他A股", "689 段归属已改变，须评估影响面"


# ---------------------------------------------------------------------------
# 组 3：fetch_all_periods / fetch_all_disclosures（逐期抓取骨架）
# ---------------------------------------------------------------------------
def _fund_mod():
    return _load("fetch/fundamentals_source.py", "_fs")


def test_fetch_all_periods_shape_on_success(monkeypatch):
    """全成功：records 拼接、ok_periods 完整、failed 为空。"""
    mod = _fund_mod()
    monkeypatch.setattr(mod, "fetch_period", lambda p: [{"period": p, "v": 1}])
    out = mod.fetch_all_periods(["A", "B"], delay=0)
    assert [r["period"] for r in out["records"]] == ["A", "B"]
    assert out["ok_periods"] == ["A", "B"]
    assert out["failed"] == {}


def test_fetch_all_periods_records_empty_as_failure(monkeypatch):
    """**空结果也算失败**（不得当「成功但无数据」）—— 改造后仍须如此。"""
    mod = _fund_mod()
    monkeypatch.setattr(mod, "fetch_period",
                        lambda p: [] if p == "B" else [{"period": p}])
    out = mod.fetch_all_periods(["A", "B"], delay=0)
    assert out["failed"] == {"B": "empty_records"}
    assert out["ok_periods"] == ["A"]


def test_fetch_all_periods_records_unavailable_as_failure(monkeypatch):
    """源不可用：记入 failed（带原因），不中断其余期。"""
    mod = _fund_mod()

    def fake(p):
        if p == "B":
            raise mod.AkshareUnavailable("源不可用")
        return [{"period": p}]

    monkeypatch.setattr(mod, "fetch_period", fake)
    out = mod.fetch_all_periods(["A", "B", "C"], delay=0)
    assert set(out["failed"]) == {"B"}
    assert out["ok_periods"] == ["A", "C"]


def test_fetch_all_disclosures_same_shape(monkeypatch):
    """披露日抓取与估值期抓取**骨架行为一致**（改造为共用骨架的依据）。"""
    mod = _fund_mod()
    monkeypatch.setattr(mod, "fetch_disclosure_period", lambda p: [{"rp": p}])
    out = mod.fetch_all_disclosures(["P1"], delay=0)
    assert out["ok_periods"] == ["P1"]
    assert isinstance(out["records"], list)
    assert isinstance(out["failed"], Dict)


def test_fetch_all_progress_callback_signature(monkeypatch):
    """`on_progress` 回调签名 `(i, total, item, n_got, err)` 不得变。"""
    mod = _fund_mod()
    monkeypatch.setattr(mod, "fetch_period", lambda p: [{"period": p}])
    calls: List[Any] = []
    mod.fetch_all_periods(["A", "B"], delay=0,
                          on_progress=lambda *a: calls.append(a))
    assert len(calls) == 2
    for i, (idx, total, item, n_got, err) in enumerate(calls, 1):
        assert idx == i and total == 2 and item in ("A", "B")
        assert n_got == 1 and err == ""
