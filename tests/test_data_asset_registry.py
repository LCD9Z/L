# -*- coding: utf-8 -*-
"""数据资产守卫：正式结论产物必须声明数据集（整改清单 P0-2）。

## 锁住什么

验收标准：**每项正式结论可追溯到唯一数据集及版本。**

项目曾因「数据集混淆」出过实质性错误 ——
副本侧以「v3 含 239 只退市股」否证 H-CD「不含退市股」，
但 H-CD 用的是 `D:/new_tdx/vipdoc`（通达信），**不是 v3**。
**两个命题都成立**，错在把不同数据集当成同一个「本项目数据集」。

本测试防三类回归：

1. **新产物不带 `source`** → 结论无法追溯到数据集
2. **`source` 指向未登记的数据集** → 出现"D8"这种野数据集
3. **登记册本身丢失** → 规则失去载体

## 已知缺口（如实记录，不假装通过）

实测：`reports/` 下 71 份 JSON 中，**53 份未声明 `source`**（历史产物）。
本守卫**只约束 VERDICT 类新产物**，历史产物的回填是单独任务
（见 `DATA_ASSET_REGISTRY.md` §四 缺口 1）——**不用降低标准来让历史产物过关**。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
REGISTRY = ROOT / "DATA_ASSET_REGISTRY.md"

#: 已登记的数据集编号 → 路径（须与 DATA_ASSET_REGISTRY.md §二 一致）
KNOWN_DATASETS = {
    "D1": "D:/new_tdx/vipdoc",
    "D2": "D:/tdx_dataset_v2",
    "D3": "D:/tdx_dataset_v3",
    "D4": "D:/tdx_dataset",
    "D5": "D:/xs_tencent/klines",
    "D6": "D:/xs_baostock",
    "D7": "D:/pit_snapshots",
}

#: 必须声明 source 的产物（VERDICT / 判定类 = 正式结论）
REQUIRED_DECLARE = [
    "reports/cross_decade/VERDICT.json",
]


def test_registry_exists():
    assert REGISTRY.is_file(), "DATA_ASSET_REGISTRY.md 缺失"


def test_registry_lists_all_known_datasets():
    text = REGISTRY.read_text(encoding="utf-8")
    for ds in KNOWN_DATASETS:
        assert ds in text, f"登记册缺少数据集 {ds}"


def test_verdict_artifacts_declare_source():
    """⚠️ 核心守卫：判定类产物必须声明 source。"""
    missing = []
    for rel in REQUIRED_DECLARE:
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            missing.append(f"{rel}: 非合法 JSON")
            continue
        src = d.get("source")
        if not src:
            missing.append(f"{rel}: 未声明 source")
        elif not any(v in str(src) for v in KNOWN_DATASETS.values()):
            missing.append(f"{rel}: source={src} 不在登记册内")
    assert missing == [], f"以下判定产物缺 source 或指向未登记数据集: {missing}"


def test_all_cross_decade_artifacts_declare_source():
    """H-CD 系列（跨年代结论）全部须声明 source。"""
    missing = []
    for p in sorted((REPORTS / "cross_decade").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not d.get("source"):
            missing.append(p.name)
    assert missing == [], f"cross_decade 下未声明 source 的产物: {missing}"


def test_xsrc_artifacts_declare_source_and_amount_flag():
    """H-XSRC 产物须声明 source，且须标注 amount 是否为估算值。

    `amihud20` / `loga20` 的定义变量是 amount；腾讯源不返回成交额，
    只能用 `volume×(H+L+C)/3` 估算 —— 若不标注，会被误当原始值使用。
    """
    for name in ("XSRC.json",):
        p = REPORTS / "xsource" / name
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d.get("source"), "XSRC.json 未声明 source"
        assert "amount_is_estimated" in d, \
            "XSRC.json 未标注 amount 是否为估算值（amihud/loga20 依赖它）"


def test_registry_records_the_v3_vs_vipdoc_incident():
    """登记册须记录那次「数据集混淆」事故 —— 否则后人不知道为什么有这份册子。"""
    text = REGISTRY.read_text(encoding="utf-8")
    assert "vipdoc" in text and "v3" in text, "登记册未记录 v3 vs 通达信事故"
    assert "否证" in text, "登记册未说明那次错误的具体形态"
