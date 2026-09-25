# -*- coding: utf-8 -*-
"""PIT 财务数据的时点正确性守卫。

这组用例的核心只有一件事：**该日还没公告的数据，绝不能出现在该日的因子值里**。
前视偏差不会抛异常，只会让回测结果悄悄变好 —— 所以必须由测试来挡。
"""
import json

import pytest

from pit.pit_fundamentals import (
    ANNOUNCE_SANITY_DAYS,
    PitFundamentals,
    SUPPORTED_FACTORS,
    audit_announce_dates,
    load_records,
    resolve_availability,
    save_records,
    statutory_available_date,
)


def rec(code="600519", period="2024-03-31", announce="2024-04-25", **kw):
    base = {"code": code, "report_period": period, "announce_date": announce,
            "name": "测试", "industry": "白酒",
            "eps": 1.0, "revenue": 1e9, "revenue_yoy_pct": 10.0,
            "net_profit": 1e8, "net_profit_yoy_pct": 12.0,
            "bps": 10.0, "roe_pct": 8.0, "ocf_per_share": 0.5,
            "gross_margin_pct": 90.0}
    base.update(kw)
    return base


def _as_of(pf: PitFundamentals, code: str, date: str) -> dict:
    """取一条必然存在的记录（不存在则用例失败），避免每处都写 None 断言。"""
    out = pf.as_of(code, date)
    assert out is not None, f"{code} @ {date} 应有可用记录"
    return out


# ---------------------------------------------------------------------------
# 公告日索引
# ---------------------------------------------------------------------------

def test_no_record_before_first_announcement():
    """公告日之前必须查不到任何数据 —— 这是整层存在的理由。"""
    pf = PitFundamentals([rec(announce="2024-04-25")])
    assert pf.as_of("600519", "2024-04-24") is None
    assert pf.as_of("600519", "2024-04-25") is not None
    assert pf.as_of("600519", "2024-04-26") is not None


def test_as_of_returns_latest_available_period():
    """两期都已公告时取**报告期最晚**的一期。"""
    pf = PitFundamentals([
        rec(period="2024-03-31", announce="2024-04-25", eps=1.0),
        rec(period="2024-06-30", announce="2024-08-20", eps=2.0),
    ])
    assert _as_of(pf, "600519", "2024-08-19")["report_period"] == "2024-03-31"
    assert _as_of(pf, "600519", "2024-08-20")["report_period"] == "2024-06-30"


def test_as_of_prefers_newer_period_even_if_announced_earlier():
    """年报延迟披露时，次年一季报才是更新的信息 —— 必须选一季报。"""
    pf = PitFundamentals([
        rec(period="2023-12-31", announce="2024-05-10", eps=4.0),
        rec(period="2024-03-31", announce="2024-04-25", eps=1.5),
    ])
    assert _as_of(pf, "600519", "2024-04-26")["report_period"] == "2024-03-31"
    assert _as_of(pf, "600519", "2024-05-11")["report_period"] == "2024-03-31"


def test_later_announcement_of_same_period_wins():
    """同一报告期有更正公告时，取公告日更晚的一条（更保守）。"""
    pf = PitFundamentals([
        rec(period="2024-03-31", announce="2024-04-25", eps=1.0),
        rec(period="2024-03-31", announce="2024-06-01", eps=1.1),
    ])
    assert _as_of(pf, "600519", "2024-05-01")["eps"] == pytest.approx(1.0)
    assert _as_of(pf, "600519", "2024-06-02")["eps"] == pytest.approx(1.1)


def test_records_without_announce_or_period_are_dropped():
    pf = PitFundamentals([
        {"code": "600519", "report_period": "2024-03-31"},          # 缺公告日
        {"code": "600519", "announce_date": "2024-04-25"},          # 缺报告期
        rec(),
    ])
    assert len(pf) == 1
    assert pf.codes() == ["600519"]


def test_unknown_code_returns_none():
    pf = PitFundamentals([rec()])
    assert pf.as_of("000001", "2025-01-01") is None
    assert pf.factors_as_of("000001", "2025-01-01") == {}


def test_known_as_of_is_monotone_in_date():
    pf = PitFundamentals([
        rec(period="2024-03-31", announce="2024-04-25"),
        rec(period="2024-06-30", announce="2024-08-20"),
        rec(period="2024-09-30", announce="2024-10-25"),
    ])
    counts = [len(pf.known_as_of("600519", d))
              for d in ("2024-01-01", "2024-05-01", "2024-09-01", "2025-01-01")]
    assert counts == sorted(counts)
    assert counts[0] == 0 and counts[-1] == 3


# ---------------------------------------------------------------------------
# TTM 每股收益
# ---------------------------------------------------------------------------

def _year_of_records(year, eps_q1, eps_q4, eps_q2=None):
    rows = [rec(period=f"{year}-03-31", announce=f"{year}-04-25", eps=eps_q1),
            rec(period=f"{year}-12-31", announce=f"{year + 1}-04-20", eps=eps_q4)]
    if eps_q2 is not None:
        rows.append(rec(period=f"{year}-06-30", announce=f"{year}-08-20", eps=eps_q2))
    return rows


def test_ttm_eps_at_annual_period_is_the_annual_figure():
    pf = PitFundamentals(_year_of_records(2023, 1.0, 4.0))
    assert pf.ttm_eps_as_of("600519", "2024-04-21") == pytest.approx(4.0)


def test_ttm_eps_formula_q1():
    """TTM = EPS(Y,Q1) + EPS(Y-1,年报) - EPS(Y-1,Q1) = 1.5 + 4.0 - 1.0 = 4.5"""
    pf = PitFundamentals(_year_of_records(2023, 1.0, 4.0) +
                         _year_of_records(2024, 1.5, 0.0)[:1])
    assert pf.ttm_eps_as_of("600519", "2024-04-25") == pytest.approx(4.5)


def test_ttm_eps_is_none_when_prior_year_missing():
    """缺上一年年报 → 不推算，返回 None（不插补、不近似）。"""
    pf = PitFundamentals([rec(period="2024-03-31", announce="2024-04-25", eps=1.5)])
    assert pf.ttm_eps_as_of("600519", "2024-05-01") is None


def test_ttm_eps_does_not_use_prior_annual_announced_later():
    """前视守卫：上一年年报比本年一季报**公告得更晚**时，不得用于该时点。

    年报（2023-12-31）在 2024-04-20 公告，一季报在 2024-04-25 公告 ——
    这属于正常顺序；反过来构造（年报 2024-05-10 才公告）时必须判不可用。
    """
    rows = [
        rec(period="2023-03-31", announce="2023-04-25", eps=1.0),
        rec(period="2023-12-31", announce="2024-05-10", eps=4.0),   # 公告晚于下条
        rec(period="2024-03-31", announce="2024-04-25", eps=1.5),
    ]
    pf = PitFundamentals(rows)
    assert _as_of(pf, "600519", "2024-04-25")["report_period"] == "2024-03-31"
    assert pf.ttm_eps_as_of("600519", "2024-04-25") is None      # 年报尚未公告
    assert pf.ttm_eps_as_of("600519", "2024-05-10") == pytest.approx(4.5)


# ---------------------------------------------------------------------------
# 因子派生
# ---------------------------------------------------------------------------

def test_pb_is_price_over_book_value_per_share():
    pf = PitFundamentals([rec(bps=10.0)])
    out = pf.factors_as_of("600519", "2025-01-01", price=200.0)
    assert out["pb"] == pytest.approx(20.0)


def test_pb_omitted_when_bps_not_positive():
    pf = PitFundamentals([rec(bps=0.0)])
    assert "pb" not in pf.factors_as_of("600519", "2025-01-01", price=200.0)
    pf_neg = PitFundamentals([rec(bps=-1.0)])
    assert "pb" not in pf_neg.factors_as_of("600519", "2025-01-01", price=200.0)


def test_pe_ttm_omitted_when_earnings_negative():
    """负 PE 无经济含义，硬算会产生假排序 —— 必须缺失而不是取绝对值。"""
    pf = PitFundamentals([rec(period="2023-12-31", announce="2024-04-20", eps=-2.0)])
    out = pf.factors_as_of("600519", "2025-01-01", price=200.0)
    assert "pe_ttm" not in out
    assert "pb" in out


def test_valuation_factors_need_price():
    pf = PitFundamentals([rec()])
    out = pf.factors_as_of("600519", "2025-01-01")
    assert "pb" not in out and "pe_ttm" not in out
    assert out["roe"] == pytest.approx(8.0)          # 不需要价格的因子照常输出


def test_missing_metrics_are_absent_not_zero():
    """缺失即缺失：不返回 0，否则会被读成"指标为零"而不是"没有数据"。"""
    pf = PitFundamentals([rec(roe_pct=None, gross_margin_pct=None)])
    out = pf.factors_as_of("600519", "2025-01-01")
    assert "roe" not in out
    assert "gross_margin" not in out
    assert "net_profit_growth" in out


def test_supported_factors_are_all_emitted():
    pf = PitFundamentals([rec(period="2023-12-31", announce="2024-04-20", eps=4.0)])
    out = pf.factors_as_of("600519", "2025-01-01", price=200.0)
    for name in SUPPORTED_FACTORS:
        assert name in out, f"{name} 应可用"


def test_factors_carry_report_period_for_cross_section_filtering():
    """roe 是 YTD 口径，跨报告期不可比 —— 必须能拿到 report_period 来过滤。"""
    pf = PitFundamentals([rec(period="2024-06-30", announce="2024-08-20")])
    out = pf.factors_as_of("600519", "2024-09-01")
    assert out["report_period"] == "2024-06-30"
    assert out["announce_date"] == "2024-08-20"


# ---------------------------------------------------------------------------
# 覆盖率与序列化
# ---------------------------------------------------------------------------

def test_coverage_reports_ratio_and_is_date_sensitive():
    pf = PitFundamentals([rec(code="600519", announce="2024-04-25"),
                          rec(code="000001", announce="2024-04-25")])
    codes = ["600519", "000001", "300750"]
    early = pf.coverage(codes, "2024-01-01")
    late = pf.coverage(codes, "2025-01-01")
    assert early["covered"] == 0 and early["ratio"] == 0.0
    assert late["covered"] == 2 and late["ratio"] == pytest.approx(2 / 3)


def test_coverage_on_empty_input():
    pf = PitFundamentals([])
    out = pf.coverage([], "2025-01-01")
    assert out["requested"] == 0 and out["ratio"] == 0.0


def test_jsonl_roundtrip(tmp_path):
    rows = [rec(code="600519"), rec(code="000001", period="2024-06-30")]
    path = tmp_path / "fundamentals.jsonl"
    assert save_records(rows, path) == 2
    back = load_records(path)
    assert len(back) == 2
    assert {r["code"] for r in back} == {"600519", "000001"}


def test_load_records_skips_blank_and_broken_lines(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text(
        json.dumps(rec()) + "\n"
        "\n"
        "{ 这不是合法 JSON\n"
        + json.dumps(rec(code="000001")) + "\n",
        encoding="utf-8")
    assert len(load_records(path)) == 2


def test_save_records_is_sorted_and_newline_terminated(tmp_path):
    path = tmp_path / "x.jsonl"
    save_records([rec(code="600519"), rec(code="000001")], path)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text.splitlines()[0].startswith('{"announce_date"') or '"000001"' in text.splitlines()[0]


# ---------------------------------------------------------------------------
# 公告日不可信时的保守可用日（2026-09-19 实测发现）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period,expected", [
    ("2024-03-31", "2024-04-30"),
    ("2024-06-30", "2024-08-31"),
    ("2024-09-30", "2024-10-31"),
    ("2024-12-31", "2025-04-30"),   # 年报为次年 4/30
])
def test_statutory_available_date_per_quarter(period, expected):
    assert statutory_available_date(period) == expected


def test_resolve_availability_trusts_plausible_announce_date():
    out, basis = resolve_availability({"report_period": "2024-03-31",
                                       "announce_date": "2024-04-25"})
    assert (out, basis) == ("2024-04-25", "announce_date")


def test_resolve_availability_rejects_plus_one_year_offset():
    """实测：数据源公告日在 2016~2025Q2 全部期数上系统性偏移 +1 年。

    茅台 2016Q1 财报（EPS 3.89，数值确为 2016Q1）标注公告日 2017-04-25。
    该值必须被判不可信并退回法定截止日，否则数据可用时间整体推迟一年。
    """
    out, basis = resolve_availability({"report_period": "2016-03-31",
                                       "announce_date": "2017-04-25"})
    assert basis == "statutory_deadline"
    assert out == "2016-04-30"


def test_resolve_availability_tolerates_slightly_late_filers():
    """真实延迟披露在容忍窗口内仍采信公告日（不误伤）。"""
    late = "2024-05-20"      # 法定 2024-04-30 之后 20 天
    out, basis = resolve_availability({"report_period": "2024-03-31",
                                       "announce_date": late})
    assert basis == "announce_date" and out == late
    assert ANNOUNCE_SANITY_DAYS == 45


def test_corrupted_announce_date_does_not_delay_availability():
    """回归守卫：修正前，损坏的公告日会让 2024Q1 数据到 2025-04 才"可用"。"""
    pf = PitFundamentals([rec(period="2024-03-31", announce="2025-04-30", eps=1.0)])
    assert pf.as_of("600519", "2024-04-29") is None      # 法定截止日前不可用
    got = _as_of(pf, "600519", "2024-04-30")             # 截止日起可用
    assert got["availability_basis"] == "statutory_deadline"
    assert got["available_from"] == "2024-04-30"
    assert got["announce_date"] == "2025-04-30"          # 原值保留，便于审计


def test_factors_expose_availability_provenance():
    pf = PitFundamentals([rec(period="2024-03-31", announce="2024-04-25")])
    out = pf.factors_as_of("600519", "2024-05-01", price=100.0)
    assert out["available_from"] == "2024-04-25"
    assert out["availability_basis"] == "announce_date"


def test_audit_announce_dates_flags_broken_period():
    good = [rec(period="2024-06-30", announce="2024-08-20") for _ in range(9)]
    bad = [rec(period="2016-03-31", announce="2017-04-25") for _ in range(1)]
    out = audit_announce_dates(good + bad)
    assert out["periods"]["2024-06-30"]["suspicious_ratio"] == 0.0
    assert out["periods"]["2016-03-31"]["suspicious_ratio"] == 1.0
    assert out["suspicious_total"] == 1
    assert out["records_total"] == 10


def test_audit_announce_dates_on_empty_input():
    out = audit_announce_dates([])
    assert out["records_total"] == 0 and out["suspicious_ratio"] == 0.0


# ---------------------------------------------------------------------------

