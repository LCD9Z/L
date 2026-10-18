# -*- coding: utf-8 -*-
"""东财预约披露第二源守卫（DATA_CHANNEL_PREREG 组件 C，A8，判据 D 组）。

## 锁住什么

1. **解析正确**：字段映射、代码补零、市场取自 SECUCODE、日期截到日；
2. **缺失即缺失**：`ACTUAL_PUBLISH_DATE` 为空的行不产出实际披露日
   （预约日 ≠ 实际披露日，混为一谈就是 PIT 前视）；
3. **接口异常不伪装成「无数据」**：无响应 / 非 JSON / schema 变更一律抛错；
4. **PIT 主口径未动**（D-6）：`pit/pit_fundamentals.py` 不得引用本模块。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from fetch import disclosure_eastmoney as de
from pit import pit_fundamentals

ROOT = Path(__file__).resolve().parent.parent


def _payload(rows, pages=1):
    return {"version": "x", "result": {"pages": pages, "data": rows}}


def _row(**over):
    r = {
        "SECURITY_CODE": "000001",
        "SECURITY_NAME_ABBR": "平安银行",
        "REPORT_DATE": "2024-03-31 00:00:00",
        "FIRST_APPOINT_DATE": "2024-04-20 00:00:00",
        "FIRST_CHANGE_DATE": None,
        "SECOND_CHANGE_DATE": None,
        "THIRD_CHANGE_DATE": None,
        "ACTUAL_PUBLISH_DATE": "2024-04-20 00:00:00",
        "APPOINT_PUBLISH_DATE": "2024-04-20 00:00:00",
        "IS_PUBLISH": "1",
        "SECUCODE": "000001.SZ",
        "REPORT_TYPE_NAME": "2024年 一季报",
    }
    r.update(over)
    return r


# ---------------------------------------------------------------------------
# D-1 结构与解析
# ---------------------------------------------------------------------------

def test_d1_parse_maps_fields():
    rows = de.parse_appointment_rows(_payload([_row()]), "2024-03-31")
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "000001"
    assert r["report_period"] == "2024-03-31"
    assert r["market"] == "sz"
    assert r["secucode"] == "000001.SZ"
    assert r["first_appoint"] == "2024-04-20"
    assert r["actual_publish"] == "2024-04-20"
    assert r["appoint_publish"] == "2024-04-20"
    assert r["revisions"] == 0
    assert r["is_publish"] == "1"


def test_d1_code_zfilled_and_market_from_secucode():
    rows = de.parse_appointment_rows(
        _payload([_row(SECURITY_CODE="1", SECUCODE="600000.SH")]), "2024-03-31")
    assert rows[0]["code"] == "000001"  # zfill
    assert rows[0]["market"] == "sh"
    bj = de.parse_appointment_rows(
        _payload([_row(SECURITY_CODE="920000", SECUCODE="920000.BJ")]), "2024-03-31")
    assert bj[0]["market"] == "bj"


def test_d1_revisions_counted_from_changes():
    rows = de.parse_appointment_rows(
        _payload([_row(FIRST_CHANGE_DATE="2024-04-25 00:00:00",
                       SECOND_CHANGE_DATE="2024-04-26 00:00:00")]),
        "2024-03-31")
    assert rows[0]["revisions"] == 2
    assert rows[0]["first_change"] == "2024-04-25"


def test_d1_rows_without_code_skipped():
    rows = de.parse_appointment_rows(
        _payload([_row(SECURITY_CODE=""), _row(SECURITY_CODE="600001")]),
        "2024-03-31")
    assert [r["code"] for r in rows] == ["600001"]


def test_d1_report_period_to_iso():
    assert de.report_period_to_iso("20240331") == "2024-03-31"
    for bad in ("2024-3-31", "2024033", "abcd0331", ""):
        with pytest.raises(ValueError, match="非法报告期"):
            de.report_period_to_iso(bad)


# ---------------------------------------------------------------------------
# D-1（续）缺失即缺失：未披露的行不产出实际披露日
# ---------------------------------------------------------------------------

def test_d1_undisclosed_row_has_no_actual_date():
    """ACTUAL_PUBLISH_DATE 为 null ⇒ actual_publish 空串，first_appoint 仍在。"""
    rows = de.parse_appointment_rows(
        _payload([_row(ACTUAL_PUBLISH_DATE=None, IS_PUBLISH="0")]), "2026-09-30")
    r = rows[0]
    assert r["actual_publish"] == ""
    assert r["first_appoint"] == "2024-04-20"  # 预约日仍如实保留
    assert r["is_publish"] == "0"


@pytest.mark.parametrize("bad", ["NaT", "nan", "None", "null", ""])
def test_d1_garbage_dates_become_empty(bad):
    """上游曾把 pandas 缺失值写成 "NaT"（2026-09-25 实测 11 条）——必须归空。"""
    rows = de.parse_appointment_rows(
        _payload([_row(ACTUAL_PUBLISH_DATE=bad)]), "2024-03-31")
    assert rows[0]["actual_publish"] == ""


# ---------------------------------------------------------------------------
# D-1（续）接口异常不伪装成「无数据」
# ---------------------------------------------------------------------------

def test_d1_schema_error_raises():
    payloads: List[object] = [None, {}, {"result": None}, {"result": {}}, "not-a-dict"]
    for payload in payloads:
        with pytest.raises(ValueError):
            de.parse_appointment_rows(payload, "2024-03-31")


def test_d1_fetch_no_response_raises(monkeypatch):
    monkeypatch.setattr(de, "_http_get", lambda url: None)
    with pytest.raises(RuntimeError, match="无响应"):
        de.fetch_appointment_period("20240331")


def test_d1_fetch_non_json_raises(monkeypatch):
    monkeypatch.setattr(de, "_http_get", lambda url: "<html>oops</html>")
    with pytest.raises(RuntimeError, match="非 JSON"):
        de.fetch_appointment_period("20240331")


def test_d1_fetch_schema_error_raises(monkeypatch):
    monkeypatch.setattr(de, "_http_get", lambda url: json.dumps({"result": None}))
    with pytest.raises(RuntimeError, match="schema 异常"):
        de.fetch_appointment_period("20240331")


def test_d1_fetch_paginates(monkeypatch):
    calls: List[str] = []

    def fake(url):
        calls.append(url)
        page = int(url.split("pageNumber=")[1].split("&")[0])
        code = f"{page:06d}"
        return json.dumps(_payload([_row(SECURITY_CODE=code)], pages=2))

    monkeypatch.setattr(de, "_http_get", fake)
    got = de.fetch_appointment_period("20240331", page_size=1)
    assert got["pages"] == 2 and got["rows"] == 2
    assert [r["code"] for r in got["records"]] == ["000001", "000002"]
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# D-6 PIT 主口径未动
# ---------------------------------------------------------------------------

def test_d6_pit_module_does_not_import_second_source():
    """D-6：pit_fundamentals 不得引用东财第二源 —— 冲突不静默覆盖。"""
    src = (ROOT / "pit" / "pit_fundamentals.py").read_text(encoding="utf-8")
    assert "disclosure_eastmoney" not in src
    assert "RPT_PUBLIC_BS_APPOIN" not in src


def test_d6_resolve_availability_untouched():
    """D-6：PIT 首选依据仍是巨潮表；本模块不在其依赖里。"""
    src = (ROOT / "pit" / "pit_fundamentals.py").read_text(encoding="utf-8")
    # 首选依据顺序：真实披露日（巨潮）> 可信公告日 > 法定截止日
    assert "actual_disclosure" in src and "statutory_deadline" in src
    assert "eastmoney" not in src.lower().replace("东方财富", "")  # 注释里提及数据源不算接线
    assert hasattr(pit_fundamentals, "resolve_availability")
    assert hasattr(pit_fundamentals, "load_disclosures")
