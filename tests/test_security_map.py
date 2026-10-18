# -*- coding: utf-8 -*-
"""证券代码映射表守卫（DATA_CHANNEL_PREREG 组件 B，②，判据 M 组）。

## 锁住什么

A 股 6 位代码不是全局唯一命名空间：`000905` 既是深交所股票（厦门港务），
又是上交所指数（中证500）。本项目此前的 `fetch/common.py::normalize_code`
对裸码**静默取一个**（`000905` → `0.000905`）。本文件锁住严格层：
歧义必报错、显式市场可解析、未知不猜、secid 双格式、对账不静默改。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from pit.security_map import (
    AMBIGUOUS_BARE_RANGE,
    AmbiguousCodeError,
    MarketMismatchError,
    SecurityMap,
    UnknownCodeError,
    UnknownMarketError,
    is_ambiguous_bare,
    market_of_code,
    secid_baostock,
    secid_eastmoney,
)

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "scripts" / "build_security_map.py"


def _load_build_script():
    """按文件路径加载构建脚本（避免 `scripts.` 包名让 mypy 重复识别）。"""
    spec = importlib.util.spec_from_file_location("_build_security_map", BUILD_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def stocks_dir(tmp_path):
    """构造一份最小股票元数据目录（fixture，不依赖真实数据集）。"""
    d = tmp_path / "stocks"
    d.mkdir()
    meta = {
        # 歧义区两个真例（SZ 股票，但裸码与 SH 指数撞命名空间）
        "000905": {"code": "000905", "name": "厦门港务", "list_date": "1999-04-29",
                   "delist_date": "", "is_delisted": False},
        "000001": {"code": "000001", "name": "平安银行", "list_date": "1991-04-03",
                   "delist_date": "", "is_delisted": False},
        # 非歧义区各一个
        "600000": {"code": "600000", "name": "浦发银行", "list_date": "1999-11-10",
                   "delist_date": "", "is_delisted": False},
        "300001": {"code": "300001", "name": "特锐德", "list_date": "2009-10-30",
                   "delist_date": "", "is_delisted": False},
        "920000": {"code": "920000", "name": "安徽凤凰", "list_date": "2021-11-15",
                   "delist_date": "", "is_delisted": False},
        "689009": {"code": "689009", "name": "九号公司", "list_date": "2020-10-29",
                   "delist_date": "", "is_delisted": False},
        "302132": {"code": "302132", "name": "中航成飞", "list_date": "2010-08-27",
                   "delist_date": "", "is_delisted": False},
        # 已退市（delist 对账用）
        "000002": {"code": "000002", "name": "万科A", "list_date": "1991-01-29",
                   "delist_date": "2026-06-30", "is_delisted": True},
        # 未退市但行情断更（stale_but_active 对账用）
        "000006": {"code": "000006", "name": "深振业A", "list_date": "1992-04-27",
                   "delist_date": "", "is_delisted": False},
        # 未知代码段
        "777777": {"code": "777777", "name": "???", "list_date": "2020-01-02",
                   "delist_date": "", "is_delisted": False},
    }
    for code, m in meta.items():
        (d / f"{code}.metadata.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
    # 行情 CSV：000002 退市前停、000006 断更、其余到全库最后交易日
    bars = {
        "000002": ["2026-06-29", "2026-06-30"],
        "000006": ["2026-01-05", "2026-01-06"],
        "_active": ["2026-09-10", "2026-09-11"],
    }
    for code in meta:
        rows = bars.get(code, bars["_active"])
        (d / f"{code}.csv").write_text(
            "date,open,high,low,close\n" + "".join(f"{r},1,1,1,1\n" for r in rows),
            encoding="utf-8")
    return d


@pytest.fixture()
def smap(stocks_dir):
    return SecurityMap.build_from_metadata(stocks_dir)


# ---------------------------------------------------------------------------
# M-1 阳性对照：歧义区裸码必须报错，不能静默取一个
# ---------------------------------------------------------------------------

def test_m1_ambiguous_bare_raises(smap):
    """000905 / 000001 落在歧义区 ⇒ AmbiguousCodeError，信息含两个命名空间。"""
    for code in ("000905", "000001"):
        with pytest.raises(AmbiguousCodeError) as ei:
            smap.resolve(code)
        msg = str(ei.value)
        assert "sh" in msg and "sz" in msg, f"错误信息须列出两个候选命名空间：{msg}"
        assert "不静默取一个" in msg


def test_m1_get_does_not_silently_pick(smap):
    """不抛异常的 get() 对歧义码返回 None —— 也不许静默取一个。"""
    assert smap.get("000905") is None
    assert smap.get("000905", "sz") is not None


def test_m1_ambiguacy_is_namespace_based_not_data_based(smap):
    """歧义由命名空间重叠决定，与库里有没有第二个条目无关。"""
    assert is_ambiguous_bare("000905") is True
    assert is_ambiguous_bare("000001") is True
    assert AMBIGUOUS_BARE_RANGE == ("000000", "000999")
    # 001xxx 起 SZ 独有，不再歧义
    assert is_ambiguous_bare("001979") is False
    assert is_ambiguous_bare("300001") is False


# ---------------------------------------------------------------------------
# M-2 / M-3 显式市场可解析；非歧义区裸码可直接解析
# ---------------------------------------------------------------------------

def test_m2_explicit_market_resolves(smap):
    e = smap.resolve("000905", "sz")
    assert e.code == "000905" and e.market == "sz"
    assert e.name == "厦门港务" and e.listed == "1999-04-29"


def test_m3_unambiguous_bare_resolves(smap):
    assert smap.resolve("600000").market == "sh"
    assert smap.resolve("300001").market == "sz"
    assert smap.resolve("920000").market == "bj"
    # 两个实证单票段：302132（中航成飞）/ 689009（九号公司 CDR）
    assert smap.resolve("302132").market == "sz"
    assert smap.resolve("689009").market == "sh"


def test_market_of_code_rules():
    assert market_of_code("600000") == "sh"
    assert market_of_code("688009") == "sh"
    assert market_of_code("000001") == "sz"
    assert market_of_code("301039") == "sz"
    assert market_of_code("430047") == "bj"
    with pytest.raises(UnknownMarketError, match="不在任何已知市场命名空间"):
        market_of_code("777777")


# ---------------------------------------------------------------------------
# M-4 未知 / 传错市场：三种错误可区分
# ---------------------------------------------------------------------------

def test_m4_unknown_code_raises(smap):
    with pytest.raises(UnknownCodeError, match="没有代码"):
        smap.resolve("600001", "sh")  # 命名空间对，但库里没有


def test_m4_market_mismatch_raises(smap):
    with pytest.raises(MarketMismatchError, match="不属于"):
        smap.resolve("600000", "sz")  # SH 代码传成 SZ —— 静默接受即错


def test_m4_unknown_market_raises(smap):
    with pytest.raises(UnknownMarketError, match="未知市场"):
        smap.resolve("000905", "hk")


def test_m4_unknown_market_code_recorded_not_dropped(stocks_dir, smap):
    """未知代码段：条目仍在表内（market 为空）并进异常计数 —— 不静默丢弃。

    注意：这类条目**不可经 resolve 查询**（resolve 要求市场可解析），
    只能经 `entries()`/异常清单观察 —— 「在表里但查不到」本身是
    对调用方的信号：该代码的市场需要先弄清。
    """
    assert len(smap) == 10
    assert "777777" in smap.anomalies["unknown_market"]
    codes = {e.code for e in smap.entries()}
    assert "777777" in codes
    assert smap.get("777777") is None  # 市场不可解析 ⇒ 查不到（不猜）


# ---------------------------------------------------------------------------
# M-5 secid 双格式
# ---------------------------------------------------------------------------

def test_m5_secid_eastmoney():
    assert secid_eastmoney("600000", "sh") == "1.600000"
    assert secid_eastmoney("000001", "sz") == "0.000001"
    assert secid_eastmoney("430047", "bj") == "0.430047"  # BJ 段沿用 normalize_code 口径


def test_m5_secid_baostock():
    assert secid_baostock("600000", "sh") == "sh.600000"
    assert secid_baostock("000001", "sz") == "sz.000001"
    assert secid_baostock("430047", "bj") == "bj.430047"


def test_m5_secid_rejects_market_mismatch():
    with pytest.raises(MarketMismatchError):
        secid_eastmoney("000001", "sh")  # SZ 代码要 SH secid —— 典型的互抄错误
    with pytest.raises(MarketMismatchError):
        secid_baostock("600000", "sz")


# ---------------------------------------------------------------------------
# M-6 市场交叉校验（与东财 SECUCODE 后缀）
# ---------------------------------------------------------------------------

def test_m6_secucode_crosscheck(tmp_path, smap):
    bs = _load_build_script()
    sj = tmp_path / "disc.jsonl"
    rows = [
        {"code": "000905", "secucode": "000905.SZ"},   # 一致
        {"code": "600000", "secucode": "600000.SH"},   # 一致
        {"code": "000006", "secucode": "000006.SH"},   # 分歧：库里是 sz
        {"code": "002190", "secucode": "002190.SZ"},   # 映射表没有的代码
    ]
    sj.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                  encoding="utf-8")
    xc = bs.crosscheck_markets(smap, sj)
    assert xc["compared"] == 4
    assert xc["agree"] == 2
    assert xc["agree_ratio"] == 0.5
    assert xc["disagree"] == [{"code": "000006", "map_market": "sz",
                               "secucode_market": "sh", "name": "深振业A"}]
    assert xc["unmapped"] == [{"code": "002190", "secucode_market": "sz"}]


# ---------------------------------------------------------------------------
# M-7 delist 对账
# ---------------------------------------------------------------------------

def test_m7_delist_consistency_verdicts(smap, stocks_dir):
    audit = smap.audit_delist_consistency(stocks_dir)
    v = audit["verdicts"]
    # 000002 已退市，末条 2026-06-30 == delist_date ⇒ match
    assert v["sz:000002"]["verdict"] == "match"
    # 000006 未退市但末条 2026-01-06 < 全库最后交易日 2026-09-11 ⇒ 断更
    assert v["sz:000006"]["verdict"] == "stale_but_active"
    # 活跃票 ⇒ active_ok
    assert v["sz:000905"]["verdict"] == "active_ok"
    assert audit["dataset_end"] == "2026-09-11"
    assert audit["counts"].get("stale_but_active") == 1


def test_m7_delist_mismatch_detected(stocks_dir):
    """末条晚于 delist_date ⇒ mismatch（矛盾只登记）。"""
    (stocks_dir / "000002.csv").write_text(
        "date,open,high,low,close\n2026-07-01,1,1,1,1\n", encoding="utf-8")
    smap = SecurityMap.build_from_metadata(stocks_dir)
    audit = smap.audit_delist_consistency(stocks_dir)
    assert audit["verdicts"]["sz:000002"]["verdict"] == "mismatch"


# ---------------------------------------------------------------------------
# M-8 确定性
# ---------------------------------------------------------------------------

def test_m8_deterministic(stocks_dir):
    a = SecurityMap.build_from_metadata(stocks_dir).to_dict(built_at="T")
    b = SecurityMap.build_from_metadata(stocks_dir).to_dict(built_at="T")
    assert a == b


def test_m8_successor_is_empty_and_counted(smap):
    """successor 无本地来源：一律空串，计数为 0（不硬凑）。"""
    assert smap.successor_known_count == 0
    assert all(e.successor == "" for e in smap.entries())
    assert smap.to_dict(built_at="T")["successor_known_count"] == 0
