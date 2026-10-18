# -*- coding: utf-8 -*-
"""双源交叉校验脚本的助手函数守卫（DATA_CHANNEL_PREREG 组件 C）。

D-2~D-5 的**数字**由跑脚本产出（记入 `DATA_CHANNEL_VERDICT.md`）；
本文件锁住脚本里的纯函数：JSONL 装载（坏行计数）、天数差、分位数。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "crosscheck_disclosure_sources.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("_crosscheck", SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_load_jsonl_map_counts_bad_lines(mod, tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps({"code": "1", "report_period": "2024-03-31",
                    "actual_publish": "2024-04-20"}, ensure_ascii=False) + "\n"
        + "{broken json\n"
        + json.dumps({"code": "600000", "report_period": "bad-period",
                      "actual_publish": ""}, ensure_ascii=False) + "\n"
        + "\n",
        encoding="utf-8")
    out, bad = mod._load_jsonl_map(p, ("actual_publish",))
    assert out == {("000001", "2024-03-31"): {"actual_publish": "2024-04-20"}}
    assert bad == 2  # 坏 JSON 一行 + 非法报告期一行（空行不计）


def test_days_diff(mod):
    assert mod._days("2024-04-20", "2024-03-31") == 20
    assert mod._days("2024-03-31", "2024-04-20") == -20
    assert mod._days("2024-04-20", "2024-03-31") is not None
    assert mod._days("bad", "2024-03-31") is None


def test_percentile(mod):
    vals = list(range(1, 101))  # 1..100
    assert mod._percentile(vals, 0.0) == 1
    assert mod._percentile(vals, 0.5) == 50
    assert mod._percentile(vals, 1.0) == 100
    assert mod._percentile([], 0.5) == 0.0
