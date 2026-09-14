from corporate.corporate_action_provider import (
    audit_action_coverage,
    consolidate_actions,
    normalize_tushare_dividend,
)
from corporate.corporate_actions import CorporateAction, build_back_adjustment_factors


def test_normalize_tushare_cash_bonus():
    a = normalize_tushare_dividend({
        "ts_code": "600000.SH", "ex_date": "20260601",
        "stk_bo_rate": 2.0, "stk_co_rate": 3.0, "cash_div": 0.5,
    })
    assert a is not None
    assert a.normalized_code() == "600000"
    assert a.event_type == "cash_bonus"
    assert abs(a.bonus_ratio - 0.5) < 1e-9
    assert abs(a.cash_dividend - 0.5) < 1e-9


def test_missing_ex_date_is_not_invented():
    assert normalize_tushare_dividend({"ts_code": "600000.SH", "cash_div": 1.0}) is None


def test_coverage_detects_missing_codes():
    a = normalize_tushare_dividend({"ts_code": "600000.SH", "ex_date": "20260601", "cash_div": 1.0})
    assert a is not None
    audit = audit_action_coverage(["600000", "000001"], [a])
    assert audit.requested_codes == 2
    assert audit.returned_codes == 1
    assert audit.event_rows == 1
    assert audit.has_complete_coverage is False
    assert audit.missing_codes == ("000001",)


# ---------------------------------------------------------------------------
# consolidate_actions：同一除权日的不同报告期分红方案
# ---------------------------------------------------------------------------

def _mk(code="600720", ex="2024-06-13", cash=0.0, bonus=0.0,
        rights=0.0, rights_price=0.0, source="test"):
    return CorporateAction(code=code, ex_date=ex, event_type="cash_dividend",
                           cash_dividend=cash, bonus_ratio=bonus,
                           rights_ratio=rights, rights_price=rights_price, source=source)


def test_consolidate_sums_same_ex_date_cash():
    """实测案例：600720 于 20240613 同时实施 2023 年报与 2022 年报分红。"""
    out = consolidate_actions([
        _mk(cash=0.257, source="em.2023"),
        _mk(cash=0.1104, source="em.2022"),
    ])
    assert len(out) == 1
    assert abs(out[0].cash_dividend - 0.3674) < 1e-9
    assert out[0].event_type == "cash_dividend"


def test_consolidate_merges_cash_and_bonus():
    out = consolidate_actions([
        _mk(cash=0.5), _mk(bonus=0.3),
    ])
    assert len(out) == 1
    assert abs(out[0].cash_dividend - 0.5) < 1e-9
    assert abs(out[0].bonus_ratio - 0.3) < 1e-9
    assert out[0].event_type == "cash_bonus"


def test_consolidate_keeps_distinct_dates_separate():
    out = consolidate_actions([_mk(ex="2024-06-13", cash=0.1), _mk(ex="2024-07-01", cash=0.2)])
    assert len(out) == 2


def test_consolidate_keeps_distinct_codes_separate():
    out = consolidate_actions([_mk(code="600720", cash=0.1), _mk(code="601966", cash=0.2)])
    assert len(out) == 2


def test_consolidate_single_action_returned_unchanged():
    """未发生合并时不得重建对象（否则会丢失证据字段）。"""
    a = _mk(cash=0.5, source="em.original")
    out = consolidate_actions([a])
    assert len(out) == 1
    assert out[0] is a


def test_consolidate_marks_source_chain():
    out = consolidate_actions([_mk(cash=0.1, source="em.a"), _mk(cash=0.2, source="em.b")])
    assert out[0].source == "em.a+em.b"
    assert out[0].confidence == "consolidated"


def test_consolidate_rights_price_is_ratio_weighted():
    out = consolidate_actions([
        _mk(rights=0.2, rights_price=5.0),
        _mk(rights=0.3, rights_price=8.0),
    ])
    assert len(out) == 1
    assert out[0].event_type == "rights_issue"
    assert abs(out[0].rights_ratio - 0.5) < 1e-9
    assert abs(out[0].rights_price - (5.0 * 0.2 + 8.0 * 0.3) / 0.5) < 1e-9


def test_consolidate_output_passes_validate_actions():
    """合并结果必须能通过 validate_actions —— 这正是未合并时会抛错的路径。"""
    from corporate.corporate_actions import validate_actions
    merged = consolidate_actions([_mk(cash=0.257), _mk(cash=0.1104)])
    assert len(validate_actions(merged)) == 1


def test_unconsolidated_duplicates_still_rejected():
    """守卫必须保留：真正的重复事件仍应被拒绝，不能因合并功能而放宽。"""
    import pytest
    from corporate.corporate_actions import validate_actions
    with pytest.raises(ValueError, match="duplicate_corporate_action"):
        validate_actions([_mk(cash=0.257), _mk(cash=0.257)])


def test_consolidated_factor_matches_manual_calculation():
    """端到端：合并后的复权因子应等于「按合计派息」手算的结果。"""
    bars = [
        {"date": "2024-06-12", "close": 10.0},
        {"date": "2024-06-13", "close": 9.6},
        {"date": "2024-06-14", "close": 9.7},
    ]
    merged = consolidate_actions([_mk(cash=0.3), _mk(cash=0.1)])  # 合计 0.4
    out = build_back_adjustment_factors(bars, merged)
    # 除权参考价 = 10 - 0.4 = 9.6 → 因子 = 0.96
    assert abs(out[0]["back_adjustment_factor"] - 0.96) < 1e-9
    assert abs(out[1]["back_adjustment_factor"] - 1.0) < 1e-9
