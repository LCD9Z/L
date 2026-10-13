# -*- coding: utf-8 -*-
"""PIT 快照库守卫测试（`pit/pit_snapshot_store.py`）。

锁住四类**不会报错、但会让结论悄悄变好**的失效：

1. **双时间轴被绕过** —— ``revisable`` 数据集若漏掉 ``as_of`` 轴，
   会把「当时尚未公布」的修订值放进历史查询（前视偏差）。
2. **只追加被绕过** —— 覆盖已落盘日期 = 历史被悄悄改写，无法复现。
3. **未登记数据集被静默使用** —— 与项目反复出现的「契约断裂」同类。
4. **行尾不合规** —— 本项目已被 CRLF 咬过三次（见 memory 2026-09-30/10-11）。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

import pytest

from pit.pit_snapshot_store import (
    DATASET_REGISTRY,
    MODE_IMMUTABLE_FACT,
    MODE_REVISABLE,
    OverwriteRefusedError,
    PitSnapshotStore,
    UnknownDatasetError,
    dataset_meta,
    in_universe,
    make_run_id,
    sha256_of_file,
)


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------
@pytest.fixture()
def store(tmp_path: Path) -> PitSnapshotStore:
    return PitSnapshotStore(tmp_path / "snap")


@pytest.fixture()
def revisable_ds(monkeypatch: pytest.MonkeyPatch) -> str:
    """临时登记一个 ``revisable`` 数据集（用于验证双轴确实生效）。"""
    name = "_test_revisable"
    monkeypatch.setitem(
        DATASET_REGISTRY,
        name,
        {
            "pit_mode": MODE_REVISABLE,
            "primary_key": "code",
        },
    )
    return name


def _rows(*triples: Any) -> List[Dict[str, str]]:
    """(code, effective_date, as_of, payload) → 规范行。"""
    out = []
    for code, eff, as_of, payload in triples:
        out.append(
            {
                "code": code,
                "effective_date": eff,
                "as_of": as_of,
                "ingest_run_id": "20261011-2130",
                "payload": payload,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 登记纪律
# ---------------------------------------------------------------------------
def test_unregistered_dataset_is_rejected():
    """未登记数据集必须抛错 —— 防「静默使用未登记数据」。"""
    with pytest.raises(UnknownDatasetError):
        dataset_meta("_not_registered")


def test_l1_stock_basic_is_registered_as_immutable_fact_with_justification():
    """`l1_stock_basic` 走单轴，**必须**在登记表给出理由（不得裸声明）。"""
    meta = dataset_meta("l1_stock_basic")
    assert meta["pit_mode"] == MODE_IMMUTABLE_FACT
    assert str(meta.get("justification", "")).strip(), "immutable_fact 必须附理由"


def test_every_immutable_fact_dataset_documents_justification():
    """全局守卫：任何 `immutable_fact` 数据集都必须有非空 justification。"""
    for name, meta in DATASET_REGISTRY.items():
        if meta.get("pit_mode") == MODE_IMMUTABLE_FACT:
            assert str(meta.get("justification", "")).strip(), f"{name} 缺 justification"


# ---------------------------------------------------------------------------
# 只追加
# ---------------------------------------------------------------------------
def test_append_raw_refuses_overwrite(store: PitSnapshotStore):
    store.append_raw("src", "ep", "2026-10-11", [{"a": 1}])
    with pytest.raises(OverwriteRefusedError):
        store.append_raw("src", "ep", "2026-10-11", [{"a": 2}])


def test_append_raw_force_allows_overwrite(store: PitSnapshotStore):
    store.append_raw("src", "ep", "2026-10-11", [{"a": 1}])
    p = store.append_raw("src", "ep", "2026-10-11", [{"a": 2}], force=True)
    assert '"a": 2' in p.read_text(encoding="utf-8")


def test_write_normalized_refuses_overwrite(store: PitSnapshotStore):
    store.write_normalized("l1_stock_basic", "2026-10-11", _rows(("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "x")))
    with pytest.raises(OverwriteRefusedError):
        store.write_normalized("l1_stock_basic", "2026-10-11", _rows(("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "x")))


# ---------------------------------------------------------------------------
# 双时间轴（核心）
# ---------------------------------------------------------------------------
def test_revisable_mode_enforces_as_of_axis(store: PitSnapshotStore, revisable_ds: str):
    """⚠️ 核心守卫：`revisable` 数据集不得漏掉 as_of 轴。

    记录：effective_date=2020-01-01（事件日）但 as_of=2026-10-11（2026 年才知道）。
    → 查询 2021-01-01 时**必须看不到它**（否则就是前视）。
    """
    store.write_normalized(
        revisable_ds, "2026-10-11",
        _rows(("600000", "2020-01-01", "2026-10-11T21:00:00+08:00", "revised")),
    )
    assert store.records_as_of(revisable_ds, "2021-01-01") == []
    assert len(store.records_as_of(revisable_ds, "2026-10-12")) == 1


def test_immutable_fact_mode_uses_effective_axis_only(store: PitSnapshotStore):
    """`immutable_fact` 数据集：历史结局事实可回溯查询（as_of 仅溯源）。"""
    store.write_normalized(
        "l1_stock_basic", "2026-10-11",
        _rows(("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "listed")),
    )
    # as_of 是 2026 年，但 effective_date 是 1999 → 2000 年查询应可见
    assert len(store.records_as_of("l1_stock_basic", "2000-01-01")) == 1


def test_effective_date_future_is_always_excluded(store: PitSnapshotStore):
    """两个模式下，`effective_date > D` 的记录都必须被排除。

    ⚠️ 本测试同时锁住一个**真实踩过的坑**：首版登记表用 `effective_field`
    间接指向列名（l1 指向 `ipo_date`），导致同名的 `effective_date` 列被静默绕过。
    现已统一为保留列名 `effective_date`，本断言即为其守卫。
    """
    store.write_normalized(
        "l1_stock_basic", "2026-10-11",
        _rows(("301999", "2030-01-01", "2026-10-11T21:00:00+08:00", "future")),
    )
    assert store.records_as_of("l1_stock_basic", "2026-10-11") == []


def test_record_as_of_picks_latest_effective(store: PitSnapshotStore, revisable_ds: str):
    store.write_normalized(
        revisable_ds, "2026-10-11",
        _rows(
            ("600000", "2019-01-01", "2026-10-11T21:00:00+08:00", "old"),
            ("600000", "2021-01-01", "2026-10-11T21:00:00+08:00", "new"),
        ),
    )
    got = store.record_as_of(revisable_ds, "600000", "2026-10-12")
    assert got is not None and got["payload"] == "new"


def test_record_as_of_returns_none_when_unknown(store: PitSnapshotStore):
    """查不到 → 返回 None（**不猜、不填默认值**）。"""
    assert store.record_as_of("l1_stock_basic", "999999", "2026-10-11") is None


# ---------------------------------------------------------------------------
# L1 universe 语义
# ---------------------------------------------------------------------------
def test_in_universe_boundaries():
    """边界：上市日当天在内、退市日当天在外。"""
    rec = {"ipo_date": "2010-01-04", "out_date": "2020-06-30"}
    assert in_universe(rec, "2010-01-03") is False
    assert in_universe(rec, "2010-01-04") is True
    assert in_universe(rec, "2020-06-29") is True
    assert in_universe(rec, "2020-06-30") is False   # 退市日当天已不可交易


def test_in_universe_still_listed():
    """``out_date`` 空 = 仍在市 → 任何不早于上市日的日期都在内。"""
    rec = {"ipo_date": "2001-08-27", "out_date": ""}
    assert in_universe(rec, "2001-08-26") is False
    assert in_universe(rec, "2026-10-11") is True


# ---------------------------------------------------------------------------
# 自检原语
# ---------------------------------------------------------------------------
def test_primary_key_duplicate_detection():
    dup = PitSnapshotStore.check_primary_key_unique(
        [{"code": "600000"}, {"code": "600000"}, {"code": "000001"}], "code"
    )
    assert dup == ["600000"]


def test_missing_rate_counts_empty_and_none():
    rate = PitSnapshotStore.check_missing_rate(
        [{"x": "1"}, {"x": ""}, {"x": None}, {"x": "4"}], "x"
    )
    assert rate == pytest.approx(0.5)


def test_missing_rate_on_empty_rows_is_zero():
    assert PitSnapshotStore.check_missing_rate([], "x") == 0.0


# ---------------------------------------------------------------------------
# 断更
# ---------------------------------------------------------------------------
def test_detect_gaps(store: PitSnapshotStore):
    store.write_normalized("l1_stock_basic", "2026-10-09", _rows(("600000", "1999-11-10", "2026-10-09T21:00:00+08:00", "x")))
    store.write_normalized("l1_stock_basic", "2026-10-11", _rows(("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "x")))
    gaps = store.detect_gaps("l1_stock_basic", ["2026-10-09", "2026-10-10", "2026-10-11"])
    assert gaps == ["2026-10-10"]


# ---------------------------------------------------------------------------
# 日志与行尾
# ---------------------------------------------------------------------------
def test_ingest_log_appends(store: PitSnapshotStore):
    store.log_ingest({"a": 1})
    store.log_ingest({"a": 2})
    assert [e["a"] for e in store.ingest_log()] == [1, 2]


def test_normalized_csv_is_lf(store: PitSnapshotStore):
    """⚠️ 规范层必须 LF —— Windows 上 csv 默认写 CRLF，本项目已被此咬过三次。"""
    p = store.write_normalized(
        "l1_stock_basic", "2026-10-11",
        _rows(("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "x")),
    )
    raw = p.read_bytes()
    assert b"\r\n" not in raw, "规范层出现 CRLF"
    assert b"\n" in raw


def test_readback_roundtrip(store: PitSnapshotStore):
    rows = _rows(("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "x"))
    store.write_normalized("l1_stock_basic", "2026-10-11", rows)
    back = store.read_normalized("l1_stock_basic")
    assert len(back) == 1
    assert back[0]["code"] == "600000"
    assert back[0]["ingest_run_id"] == "20261011-2130"


def test_readback_merges_multiple_dates(store: PitSnapshotStore):
    store.write_normalized("l1_stock_basic", "2026-10-10", _rows(("600000", "1999-11-10", "2026-10-10T21:00:00+08:00", "d1")))
    store.write_normalized("l1_stock_basic", "2026-10-11", _rows(("600001", "1998-01-22", "2026-10-11T21:00:00+08:00", "d2")))
    assert len(store.read_normalized("l1_stock_basic")) == 2


def test_sha256_of_file(tmp_path: Path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"abc")
    assert sha256_of_file(p) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_make_run_id_format():
    from datetime import datetime, timezone, timedelta

    ts = datetime(2026, 10, 11, 21, 30, tzinfo=timezone(timedelta(hours=8)))
    assert make_run_id(ts) == "20261011-2130"


# ---------------------------------------------------------------------------
# 流式读取（iter_normalized）—— L3 全量 ~1.3 GB CSV 的唯一可行消费方式
#
# ⚠️ 背景（P3 §5 残留风险）：read_normalized 全量入内存，L3 单日即 ~1.3 GB /
# 1,100 万行 → 首个 L3 消费者出现前必须先有流式通道。read_normalized 现为
# iter_normalized 的薄封装（语义不变），新代码必须用流式版。
# ---------------------------------------------------------------------------
def test_iter_normalized_matches_read_normalized(store: PitSnapshotStore):
    """流式与全量读必须**逐行一致**（薄封装不得漂移语义）。"""
    store.write_normalized("l1_stock_basic", "2026-10-11", _rows(
        ("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "a"),
        ("600001", "2000-01-04", "2026-10-11T21:00:00+08:00", "b"),
    ))
    got_stream = list(store.iter_normalized("l1_stock_basic"))
    got_full = store.read_normalized("l1_stock_basic")
    assert got_stream == got_full, "流式与全量读漂移"


def test_iter_normalized_is_lazy_generator(store: PitSnapshotStore):
    """必须是**惰性**生成器（读第一行不载入全文件）——大文件消费的前提。"""
    import types
    store.write_normalized("l1_stock_basic", "2026-10-11", _rows(
        ("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "a"),
        ("600001", "2000-01-04", "2026-10-11T21:00:00+08:00", "b"),
    ))
    it = store.iter_normalized("l1_stock_basic")
    assert isinstance(it, types.GeneratorType), "必须返回生成器而非 list"
    first = next(it)
    assert first["code"] == "600000"


def test_iter_normalized_scoped_to_ingest_date(store: PitSnapshotStore):
    """给 ingest_date 只读该日文件（不混入其他日期）。"""
    store.write_normalized("l1_stock_basic", "2026-10-11", _rows(
        ("600000", "1999-11-10", "2026-10-11T21:00:00+08:00", "a"),
    ))
    store.append_normalized("l1_stock_basic", "2026-10-11", _rows(
        ("600001", "2000-01-04", "2026-10-12T09:00:00+08:00", "b"),
    ))
    store.write_normalized("l1_stock_basic", "2026-10-12", _rows(
        ("600002", "2000-01-05", "2026-10-12T09:00:00+08:00", "c"),
    ))
    got = list(store.iter_normalized("l1_stock_basic", "2026-10-12"))
    assert [r["code"] for r in got] == ["600002"], "只含指定 ingest_date 的行"
    assert [r["code"] for r in store.iter_normalized("l1_stock_basic")] == [
        "600000", "600001", "600002"], "跨日期按文件名（=日期）升序"


def test_iter_normalized_missing_dataset_yields_nothing(store: PitSnapshotStore):
    assert list(store.iter_normalized("l1_stock_basic")) == [], "未落盘 ⇒ 空"
    assert list(store.iter_normalized("l1_stock_basic", "2026-10-11")) == [], "缺文件 ⇒ 空"


# ---------------------------------------------------------------------------
# 真实产物守卫（若已落盘则校验；未落盘则跳过，不误报失败）
# ---------------------------------------------------------------------------
def test_real_snapshot_if_present_is_wellformed():
    root = Path("D:/pit_snapshots")
    norm = root / "normalized" / "l1_stock_basic"
    if not norm.is_dir():
        pytest.skip("本机尚无 PIT 快照落盘")
    files = sorted(norm.glob("*.csv"))
    assert files, "规范层目录存在但无文件"
    with files[-1].open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) > 4000, f"行数异常偏少: {len(rows)}"
    for need in ("code", "ipo_date", "out_date", "effective_date", "as_of", "ingest_run_id"):
        assert need in rows[0], f"规范层缺列 {need}"
    assert len({r["code"] for r in rows}) == len(rows), "主键不唯一"
