# -*- coding: utf-8 -*-
"""真实披露日（巨潮资讯）与超额统计量助手的守卫。

## 为什么需要

此前财务数据的**可用日**只能用"法定披露截止日"兜底 —— 因为东财业绩报表的
`最新公告日期` 在 2016-01 ~ 2025-06 的全部报告期上系统性偏移 +1 年（实测 88.4%
的记录不可信）。兜底虽不会前视，但会把数据可用时间整体推迟数周至数月。

巨潮 `stock_report_disclosure` 的 `实际披露` 字段给出**真实披露日**且是全市场批量，
是本层的**首选**依据。本文件锁住：解析、优先级、以及"缺失不补造"。
"""
import pytest

from alpha.alpha_survival_lab import excess_t_statistics
from fetch.fundamentals_source import (
    AkshareUnavailable,
    disclosure_period_label,
    fetch_disclosure_period,
)
from pit.pit_fundamentals import (
    PitFundamentals,
    load_disclosures,
    resolve_availability,
    statutory_available_date,
)


# ---------------------------------------------------------------------------
# 报告期 → 巨潮期数标签
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period,expected", [
    ("2024-03-31", "2024一季"),
    ("2024-06-30", "2024半年报"),
    ("2024-09-30", "2024三季"),
    ("2024-12-31", "2024年报"),
    ("2016-03-31", "2016一季"),
])
def test_disclosure_period_label(period, expected):
    assert disclosure_period_label(period) == expected


def test_disclosure_period_label_rejects_bad_period():
    with pytest.raises(ValueError, match="非法报告期"):
        disclosure_period_label("2024-05-15")


# ---------------------------------------------------------------------------
# 抓取解析（全测试替身，不联网）
# ---------------------------------------------------------------------------

class FakeFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return [dict(r) for r in self._rows]


class FakeAk:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def stock_report_disclosure(self, market, period):
        self.calls.append((market, period))
        return FakeFrame(self.rows)


def _row(code, actual, scheduled=None, revisions=()):
    r = {"股票代码": code, "股票简称": "测试", "首次预约": scheduled,
         "初次变更": None, "二次变更": None, "三次变更": None, "实际披露": actual}
    for i, v in enumerate(revisions):
        r[("初次变更", "二次变更", "三次变更")[i]] = v
    return r


def test_fetch_disclosure_period_parses_actual_date(monkeypatch):
    fake = FakeAk([_row("000001", "2025-03-15", "2025-03-15"),
                   _row("000002", "2025-04-01", "2025-03-29", ("2025-04-01",))])
    monkeypatch.setattr("fetch.fundamentals_source._ak", lambda: fake)
    got = fetch_disclosure_period("2024-12-31")
    assert fake.calls == [("沪深京", "2024年报")]
    assert [r["code"] for r in got] == ["000001", "000002"]
    assert got[0]["actual_disclose"] == "2025-03-15"
    assert got[1]["revisions"] == 1          # 变更过一次
    assert got[1]["first_scheduled"] == "2025-03-29"


def test_fetch_disclosure_period_skips_undisclosed(monkeypatch):
    """`实际披露` 为空 = 尚未披露 → **不产出**（缺失即缺失，不补造）。"""
    monkeypatch.setattr("fetch.fundamentals_source._ak",
                        lambda: FakeAk([_row("000001", None), _row("000002", "2025-04-01")]))
    got = fetch_disclosure_period("2024-12-31")
    assert [r["code"] for r in got] == ["000002"]


def test_fetch_disclosure_period_skips_rows_without_code(monkeypatch):
    monkeypatch.setattr("fetch.fundamentals_source._ak",
                        lambda: FakeAk([_row("", "2025-04-01"), _row("000002", "2025-04-01")]))
    assert len(fetch_disclosure_period("2024-12-31")) == 1


def test_fetch_disclosure_period_raises_honestly(monkeypatch):
    class Boom:
        def stock_report_disclosure(self, market, period):
            raise RuntimeError("上游 500")
    monkeypatch.setattr("fetch.fundamentals_source._ak", lambda: Boom())
    with pytest.raises(AkshareUnavailable, match="stock_report_disclosure"):
        fetch_disclosure_period("2024-12-31")


# ---------------------------------------------------------------------------
# 可用日优先级：真实披露日 > 可信公告日 > 法定截止日
# ---------------------------------------------------------------------------

def test_real_disclosure_wins_over_corrupt_announce_date():
    """真实披露日必须压过损坏的公告日 —— 这是本层升级的全部意义。"""
    rec = {"code": "600519", "report_period": "2016-03-31",
           "announce_date": "2017-04-25"}          # 损坏（偏移 +1 年）
    out, basis = resolve_availability(rec, {("600519", "2016-03-31"): "2016-04-20"})
    assert basis == "actual_disclosure"
    assert out == "2016-04-20"                     # 既非损坏公告日，也非法定截止日


def test_falls_back_when_no_real_disclosure():
    rec = {"code": "600519", "report_period": "2016-03-31",
           "announce_date": "2017-04-25"}
    out, basis = resolve_availability(rec, {})
    assert basis == "statutory_deadline"
    assert out == statutory_available_date("2016-03-31") == "2016-04-30"


def test_plausible_announce_date_still_used_without_disclosure():
    rec = {"code": "600519", "report_period": "2024-03-31",
           "announce_date": "2024-04-25"}
    out, basis = resolve_availability(rec, None)
    assert (out, basis) == ("2024-04-25", "announce_date")


def test_pit_uses_real_disclosure_for_availability():
    """端到端：给定披露日后，数据在**真实披露日**当天即可用。"""
    recs = [{"code": "600519", "report_period": "2024-03-31",
             "announce_date": "2025-04-30", "eps": 1.0, "bps": 10.0,
             "roe_pct": 8.0, "net_profit_yoy_pct": 12.0, "revenue_yoy_pct": 10.0,
             "gross_margin_pct": 90.0, "ocf_per_share": 0.5}]
    disc = {("600519", "2024-03-31"): "2024-04-18"}
    pf = PitFundamentals(recs, disc)
    assert pf.as_of("600519", "2024-04-17") is None       # 披露前一天不可用
    got = pf.as_of("600519", "2024-04-18")
    assert got is not None
    assert got["availability_basis"] == "actual_disclosure"
    assert got["available_from"] == "2024-04-18"
    assert got["announce_date"] == "2025-04-30"           # 原值保留供审计


def test_pit_without_disclosures_keeps_old_behaviour():
    recs = [{"code": "600519", "report_period": "2024-03-31",
             "announce_date": "2024-04-25", "eps": 1.0}]
    pf = PitFundamentals(recs)
    got = pf.as_of("600519", "2024-04-25")
    assert got is not None
    assert got["availability_basis"] == "announce_date"


def test_load_disclosures_roundtrip(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"code": "600519", "report_period": "2024-03-31",'
                 ' "actual_disclose": "2024-04-18"}\n'
                 '{"code": "1", "report_period": "2024-06-30",'
                 ' "actual_disclose": "2024-08-20"}\n'
                 '\n{ 坏行\n', encoding="utf-8")
    d = load_disclosures(p)
    assert d[("600519", "2024-03-31")] == "2024-04-18"
    assert d[("000001", "2024-06-30")] == "2024-08-20"   # 代码补零


def test_load_disclosures_missing_file_is_empty(tmp_path):
    assert load_disclosures(tmp_path / "nope.jsonl") == {}


# ---------------------------------------------------------------------------
# 超额统计量助手
# ---------------------------------------------------------------------------

def test_excess_t_statistics_matches_hand_computation():
    """样本 [0.02,-0.01,0.03,0.01,0.00]：

    mean = 0.01；**样本**标准差（n−1，t 检验的标准口径）= sqrt(1e-3/4) = 0.0158114；
    t = 0.01 / (0.0158114/sqrt(5)) = **1.414214**。
    """
    st = excess_t_statistics([0.02, -0.01, 0.03, 0.01, 0.00])
    assert st["n"] == 5
    assert st["t"] == pytest.approx(1.4142135623730951, abs=1e-9)
    assert st["p"] is not None and 0 < st["p"] < 1


def test_excess_t_statistics_uses_sample_sd_not_population():
    """回归守卫：口径必须是样本标准差（n−1）。用总体标准差会得到 1.5811。"""
    st = excess_t_statistics([0.02, -0.01, 0.03, 0.01, 0.00])
    assert st["t"] != pytest.approx(1.5811388, abs=1e-4)


def test_excess_t_statistics_degenerate_inputs():
    assert excess_t_statistics([])["t"] is None
    assert excess_t_statistics([0.01])["t"] is None
    assert excess_t_statistics([0.01, 0.01, 0.01])["t"] is None   # 标准差 0


def test_excess_t_statistics_sign_follows_mean():
    assert excess_t_statistics([0.01, 0.02, 0.03])["t"] > 0
    assert excess_t_statistics([-0.01, -0.02, -0.03])["t"] < 0


# ---------------------------------------------------------------------------
# 回归守卫：pandas 缺失值不得伪装成合法日期
#
# 2026-09-25 实测缺陷：巨潮披露日 176,841 条中有 **11 条** `actual_disclose="NaT"`。
# 根因是 `_norm_date` 只判 `None`，而 `str(pd.NaT) == "NaT"`（长度 3，非空串），
# 于是 "NaT" 作为"合法日期"流进下游，直接污染了「披露时点偏离」的分布计算
# （`date.fromisoformat("NaT")` 才报错暴露出来）。
#
# 「缺失即缺失」—— 这里锁住两层防线。
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["NaT", "nat", "NaN", "nan", "None", "", "   ", None])
def test_norm_date_rejects_pandas_missing(raw):
    from fetch.fundamentals_source import _norm_date
    assert _norm_date(raw) == ""


@pytest.mark.parametrize("raw,expected", [
    ("2024-04-25", "2024-04-25"),
    ("2024/04/25", "2024-04-25"),
    ("20240425", "2024-04-25"),
    ("  2024-04-25  ", "2024-04-25"),
    ("2024-04-25 00:00:00", "2024-04-25"),
])
def test_norm_date_still_parses_real_dates(raw, expected):
    from fetch.fundamentals_source import _norm_date
    assert _norm_date(raw) == expected


def test_fetch_disclosure_period_skips_nat(monkeypatch):
    """上游返回缺失值时不得产出该记录（此前会产出 actual_disclose="NaT"）。

    用 ``float("nan")`` 覆盖与 ``pd.NaT`` 相同的代码路径（``str()`` 后非空串），
    从而不必为测试引入 pandas 依赖。
    """
    monkeypatch.setattr("fetch.fundamentals_source._ak",
                        lambda: FakeAk([_row("000001", float("nan")),
                                       _row("000002", "2025-04-01")]))
    got = fetch_disclosure_period("2024-12-31")
    assert [r["code"] for r in got] == ["000002"]


def test_load_disclosures_rejects_non_iso_dates(tmp_path):
    """消费端防御：即使文件里混入 "NaT"，读入时也必须剔除。"""
    p = tmp_path / "d.jsonl"
    p.write_text('{"code": "600519", "report_period": "2024-03-31",'
                 ' "actual_disclose": "NaT"}\n'
                 '{"code": "000001", "report_period": "2024-03-31",'
                 ' "actual_disclose": "2024-04-18"}\n', encoding="utf-8")
    d = load_disclosures(p)
    assert ("600519", "2024-03-31") not in d        # NaT 被拒
    assert d[("000001", "2024-03-31")] == "2024-04-18"


def test_load_disclosures_accepts_iso_dates_only(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"code": "1", "report_period": "2024-03-31",'
                 ' "actual_disclose": "20240418"}\n', encoding="utf-8")
    assert load_disclosures(p) == {}                # 非 ISO 格式一律不收
