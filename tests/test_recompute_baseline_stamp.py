# -*- coding: utf-8 -*-
"""`_baseline` 字段与旁挂基线索引守卫（P013-④ / 2026-10-17 R1–R3 整改）。

P013-④ 原文：`_recalc` 产物**生成时**写入 `git rev-parse HEAD` 短 sha + 时间戳。
**旁挂索引属本轮自创的证据保全方案**（不触产物字节/mtime），不是 P013 要求；
回溯基线按侧取 `8db1c65`（主，登记册 §六）/ `2b9f97d`（副本，10-17 验收回执文首）。

锁六件事：
1. 新落盘产物被补上 `_baseline`（commit / as_of / source），且**沿用原生缩进与尾换行**；
2. **幂等**：已有 `_baseline` 不被覆盖（重跑不得抹掉原始基线）；
3. `git_short_sha()` 为 `unknown` 时**不落戳**（否则把 unknown 永久写死，反锁补戳）；
4. `git_short_sha()` 返回 7 位 sha 或显式 `unknown`（不抛异常）；
5. 索引按**侧**取值（main=8db1c65 / copy=2b9f97d），entry 含 `side`；
6. 索引只读产物：字节与 mtime 原样。
"""
import importlib.util
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(module: str, rel: str):
    spec = importlib.util.spec_from_file_location(module, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rr = _load("run_recompute_baseline", "scripts/run_recompute.py")
cr = _load("check_recompute_baseline", "scripts/check_recompute.py")

TASK = {"name": "demo_prod", "script": "scripts/demo.py", "args": [],
        "windows": ["2023-01-03", "2023-07-03"]}
TASK_COPY = {"name": "copy_prod", "script": "scripts/demo.py", "args": [],
             "windows": ["2023-01-03"]}


def _mk_product(tmp_path, name="demo_prod", window="2023-01-03",
                payload=None, indent=1, trailing=""):
    p = tmp_path / f"{name}_{window}.json"
    data = payload if payload is not None else {"total_return_pct": -1.5}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + trailing,
                 encoding="utf-8", newline="")
    return p


def test_stamp_baseline_adds_field(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    p = _mk_product(tmp_path)
    sha = rr.stamp_baseline(TASK, "2023-01-03", commit="abc1234")
    assert sha == "abc1234"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["_baseline"]["commit"] == "abc1234"
    assert data["_baseline"]["source"] == "run_recompute"
    assert len(data["_baseline"]["as_of"]) == 19          # YYYY-MM-DDTHH:MM:SS
    assert data["total_return_pct"] == -1.5               # 原有数字不变


def test_stamp_baseline_preserves_native_style(tmp_path, monkeypatch):
    """R3：重写必须沿用原生缩进与尾换行（只加一个字段，不改整份文件格式）。"""
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    # 情形 A：原生 indent=1、无尾换行（`reports/_recalc/` 实测形态）
    p = _mk_product(tmp_path, indent=1, trailing="")
    before = p.read_text(encoding="utf-8")
    rr.stamp_baseline(TASK, "2023-01-03", commit="abc1234")
    after = p.read_text(encoding="utf-8")
    assert not after.endswith("\n"), "原生无尾换行，重写不得添加"
    back = json.loads(after)
    del back["_baseline"]
    assert json.dumps(back, ensure_ascii=False, indent=1) == before, \
        "去掉新增字段后，必须能逐字节还原原文（含缩进与分隔符）"
    assert "_baseline" in after

    # 情形 B：原生 indent=2、带尾换行
    p2 = _mk_product(tmp_path, window="2023-07-03", indent=2, trailing="\n")
    rr.stamp_baseline(TASK, "2023-07-03", commit="abc1234")
    text2 = p2.read_text(encoding="utf-8")
    assert text2.endswith("\n") and text2.count("\n  \"") >= 2, "缩进应仍为 2 空格"


def test_stamp_baseline_is_idempotent(tmp_path, monkeypatch):
    """反向验证：已有 `_baseline` 时**不得**覆盖（防重跑抹掉原始基线）。"""
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    p = _mk_product(tmp_path, payload={"_baseline": {"commit": "first01"},
                                       "total_return_pct": -1.5})
    assert rr.stamp_baseline(TASK, "2023-01-03", commit="second2") is None
    assert json.loads(p.read_text(encoding="utf-8"))["_baseline"]["commit"] == "first01"


def test_stamp_baseline_skips_when_git_unavailable(tmp_path, monkeypatch):
    """R3-1：sha 不可用时**不落 `unknown` 戳**（否则永久写死、反锁日后补戳）。"""
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    monkeypatch.setattr(rr, "git_short_sha", lambda: "unknown")
    p = _mk_product(tmp_path)
    before = p.read_bytes()
    assert rr.stamp_baseline(TASK, "2023-01-03") is None
    assert p.read_bytes() == before, "sha 不可用时产物必须**完全不动**"
    assert "_baseline" not in json.loads(p.read_text(encoding="utf-8"))


def test_stamp_baseline_missing_product(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    assert rr.stamp_baseline(TASK, "2023-01-03", commit="abc1234") is None


def test_git_short_sha_is_sane():
    sha = rr.git_short_sha()
    assert sha == "unknown" or (len(sha) == 7 and all(c in "0123456789abcdef" for c in sha))


def test_baseline_constants_match_check_recompute():
    """R1：两文件基线常量必须一致（禁止各写各的）。"""
    expected = {k: cr.ATTRIBUTED_BASELINE[k] for k in ("main", "copy")}
    assert expected == rr.BASELINE_BY_SIDE


def test_baseline_index_per_side_and_readonly(tmp_path, monkeypatch):
    """索引按侧取值 + 只读产物（字节与 mtime 原样）。"""
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    p1 = _mk_product(tmp_path, "demo_prod", "2023-01-03")
    p2 = _mk_product(tmp_path, "copy_prod", "2023-01-03")
    old = time.time() - 86400
    for p in (p1, p2):
        os.utime(p, (old, old))
    before = {p.name: (p.read_bytes(), p.stat().st_mtime) for p in (p1, p2)}

    idx = rr.write_baseline_index({"main": [TASK], "copy": [TASK_COPY]})

    after = {p.name: (p.read_bytes(), p.stat().st_mtime) for p in (p1, p2)}
    assert before == after, "索引写入不得改动产物字节或 mtime"
    data = json.loads(idx.read_text(encoding="utf-8"))
    assert data["baseline_by_side"] == {"main": "8db1c65", "copy": "2b9f97d"}
    assert "f8f020d" not in json.dumps(data), "索引不得再出现 f8f020d"
    main_rec = data["entries"]["demo_prod_2023-01-03.json"]
    copy_rec = data["entries"]["copy_prod_2023-01-03.json"]
    assert (main_rec["side"], main_rec["commit"]) == ("main", "8db1c65")
    assert (copy_rec["side"], copy_rec["commit"]) == ("copy", "2b9f97d")
    assert main_rec["origin"] == "backfilled"
