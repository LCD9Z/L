# -*- coding: utf-8 -*-
"""守卫：研究产物的**增量落盘**契约。

## 为什么需要

本机后台进程会**静默死亡**（SOUL.md 明列的工程风险），而研究脚本单次运行 10 分钟~2 小时。
2026-09-23 实测：集中度实验跑到**第 11/12 次回测**时进程无报错退出，
因脚本只在结尾写一次 JSON，**10 次回测（约 2 小时）的结果全部丢失**。

本文件锁住三件事：

1. ``write_partial`` 只写 ``<out>.partial`` 且带 ``complete: False``；
2. ``write_final`` 才写正式 ``<out>`` 且带 ``complete: True`` ——
   **存在正式产物即代表跑完**；
3. 写入是**原子**的（``.tmp`` + ``os.replace``），不会读到半成品。

另外用一条**防回退守卫**断言四个长跑脚本确实接了增量落盘 ——
防止日后重构时被静默移除。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_artifacts import (
    PARTIAL_SUFFIX,
    read_partial,
    write_final,
    write_partial,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 契约
# ---------------------------------------------------------------------------

def test_write_partial_creates_only_partial(tmp_path):
    out = str(tmp_path / "r.json")
    write_partial(out, {"rows": [1, 2]})
    assert Path(out + PARTIAL_SUFFIX).exists()
    # 关键：正式产物**不得**存在，否则读者会误以为跑完了
    assert not Path(out).exists()
    body = json.loads(Path(out + PARTIAL_SUFFIX).read_text(encoding="utf-8"))
    assert body["complete"] is False
    assert body["rows"] == [1, 2]


def test_write_final_creates_final_only(tmp_path):
    out = str(tmp_path / "r.json")
    write_final(out, {"rows": [1, 2]})
    assert Path(out).exists()
    body = json.loads(Path(out).read_text(encoding="utf-8"))
    assert body["complete"] is True


def test_final_overrides_earlier_partial(tmp_path):
    """先写 partial 再写 final：正式产物存在且 complete=True，partial 保留。"""
    out = str(tmp_path / "r.json")
    write_partial(out, {"rows": [1]})
    write_final(out, {"rows": [1, 2], "summary": {"ok": True}})
    assert json.loads(Path(out).read_text(encoding="utf-8"))["complete"] is True
    assert Path(out + PARTIAL_SUFFIX).exists()          # 可抢救的中间态仍在


def test_partial_carries_progress_note(tmp_path):
    out = str(tmp_path / "r.json")
    write_partial(out, {"rows": []}, note="已完成 5/12 次回测")
    body = json.loads(Path(out + PARTIAL_SUFFIX).read_text(encoding="utf-8"))
    assert body["note"] == "已完成 5/12 次回测"


def test_partial_default_note_mentions_risk(tmp_path):
    out = str(tmp_path / "r.json")
    write_partial(out, {"rows": []})
    body = json.loads(Path(out + PARTIAL_SUFFIX).read_text(encoding="utf-8"))
    assert "静默死亡" in body["note"]


def test_no_tmp_file_left_behind(tmp_path):
    """原子写不得留下 ``.tmp`` 残留。"""
    out = str(tmp_path / "r.json")
    write_partial(out, {"a": 1})
    write_final(out, {"a": 1})
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_empty_out_is_noop(tmp_path):
    """``--out`` 为空时两个函数都应是空操作（脚本支持不落盘）。"""
    write_partial("", {"a": 1})
    write_final("", {"a": 1})
    assert list(tmp_path.iterdir()) == []


def test_read_partial_roundtrip(tmp_path):
    out = str(tmp_path / "r.json")
    write_partial(out, {"rows": [1, 2, 3]}, note="n=3")
    got = read_partial(out)
    assert got is not None and got["rows"] == [1, 2, 3] and got["complete"] is False


def test_read_partial_missing_returns_none(tmp_path):
    assert read_partial(str(tmp_path / "nope.json")) is None


def test_read_partial_corrupt_returns_none(tmp_path):
    out = str(tmp_path / "r.json")
    Path(out + PARTIAL_SUFFIX).write_text("{ 坏 json", encoding="utf-8")
    assert read_partial(out) is None


def test_write_partial_survives_unwritable_path(tmp_path, capsys):
    """落盘失败不得抛出（不能因 I/O 失败中断研究），但要打印告警。"""
    bad = str(tmp_path / "no_such_dir" / "r.json")
    write_partial(bad, {"a": 1})
    assert "增量落盘失败" in capsys.readouterr().out


def test_payload_is_not_mutated(tmp_path):
    """写入方传入的 dict 不应被就地修改（加了 complete/note 的是副本）。"""
    out = str(tmp_path / "r.json")
    payload = {"rows": [1]}
    write_partial(out, payload)
    assert payload == {"rows": [1]}


# ---------------------------------------------------------------------------
# 防回退守卫：四个长跑脚本必须接入增量落盘
# ---------------------------------------------------------------------------

LONG_RUNNING_SCRIPTS = [
    "run_tail_exclusion_study.py",
    "run_regime_overlay_study.py",
    "run_cost_model_check.py",
    "run_contrarian_portfolio.py",
    "run_concentration_study.py",
]


@pytest.mark.parametrize("script", LONG_RUNNING_SCRIPTS)
def test_long_running_script_checkpoints(script):
    """每个长跑脚本都必须同时调用 write_partial 与 write_final。

    只调 write_final 就是"只在结尾落盘"——那正是 2026-09-23 丢 2 小时结果的成因。
    """
    src = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert "write_partial" in src, f"{script} 未接入增量落盘（write_partial）"
    assert "write_final" in src, f"{script} 未使用 write_final"


@pytest.mark.parametrize("script", LONG_RUNNING_SCRIPTS)
def test_long_running_script_has_no_raw_json_dump_to_out(script):
    """禁止再出现「自己 open(args.out, 'w') 后 json.dump」的结尾落盘写法。"""
    src = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert 'open(args.out, "w"' not in src, (
        f"{script} 仍有裸的结尾落盘 —— 应改用 write_final"
    )
