# -*- coding: utf-8 -*-
"""P013-④ `_baseline` 字段守卫（2026-10-17 补实现）。

P013 §三-4 原文：`_recalc` 产物**生成时**写入 `git rev-parse HEAD` 短 sha + 时间戳；
已落窗口由验收环节补记基线 `f8f020d`。

锁四件事：
1. 新落盘产物被补上 `_baseline`（含 commit / as_of / source）；
2. **幂等**：已有 `_baseline` 不被覆盖（重跑不得抹掉原始基线）；
3. `git_short_sha()` 返回 7 位 sha 或显式 `unknown`（不抛异常）；
4. `write_baseline_index()` 为已落盘产物建旁挂索引，**不改产物字节、不改 mtime**。
"""
import importlib.util
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "run_recompute_baseline", ROOT / "scripts" / "run_recompute.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rr = _load()
TASK = {"name": "demo_prod", "script": "scripts/demo.py", "args": [],
        "windows": ["2023-01-03", "2023-07-03"]}


def _mk_product(tmp_path, window="2023-01-03", payload=None):
    p = tmp_path / f"demo_prod_{window}.json"
    p.write_text(json.dumps(payload or {"total_return_pct": -1.5},
                            ensure_ascii=False), encoding="utf-8")
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


def test_stamp_baseline_is_idempotent(tmp_path, monkeypatch):
    """反向验证：已有 `_baseline` 时**不得**覆盖（防重跑抹掉原始基线）。"""
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    p = _mk_product(tmp_path, payload={"_baseline": {"commit": "first01"},
                                       "total_return_pct": -1.5})
    assert rr.stamp_baseline(TASK, "2023-01-03", commit="second2") is None
    assert json.loads(p.read_text(encoding="utf-8"))["_baseline"]["commit"] == "first01"


def test_stamp_baseline_missing_product(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    assert rr.stamp_baseline(TASK, "2023-01-03", commit="abc1234") is None


def test_git_short_sha_is_sane():
    sha = rr.git_short_sha()
    assert sha == "unknown" or (len(sha) == 7 and all(c in "0123456789abcdef" for c in sha))


def test_baseline_index_does_not_touch_products(tmp_path, monkeypatch):
    """索引只读产物：字节与 mtime 必须原样（既有 43 份是证据，禁令 3）。"""
    monkeypatch.setattr(rr, "OUT_DIR", tmp_path)
    p1 = _mk_product(tmp_path, "2023-01-03")
    p2 = _mk_product(tmp_path, "2023-07-03")
    old = time.time() - 86400
    for p in (p1, p2):
        os.utime(p, (old, old))
    before = {p.name: (p.read_bytes(), p.stat().st_mtime) for p in (p1, p2)}

    idx = rr.write_baseline_index("f8f020d", [TASK])

    after = {p.name: (p.read_bytes(), p.stat().st_mtime) for p in (p1, p2)}
    assert before == after, "索引写入不得改动产物字节或 mtime"
    data = json.loads(idx.read_text(encoding="utf-8"))
    assert data["_default_commit"] == "f8f020d"
    assert set(data["entries"]) == {"demo_prod_2023-01-03.json",
                                   "demo_prod_2023-07-03.json"}
    rec = data["entries"]["demo_prod_2023-07-03.json"]
    assert rec["commit"] == "f8f020d"
    assert rec["origin"] == "backfilled"
    assert rec["window"] == "2023-07-03"
