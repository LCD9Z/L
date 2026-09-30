# -*- coding: utf-8 -*-
"""tdx_native 冒烟自测（零依赖，可脱离真实 TDX 数据运行）。

覆盖：
  1. .day 二进制 写→读 往返（struct 格式正确性）
  2. 五因子计算在构造序列上的精确值
  3. 端到端 screen（用合成 vipdoc 树，验证 Top 排序与 V1 剔除）

运行::

    python -m tdx_native.smoke_test
"""
from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SMOKE_DIR = os.path.join(HERE, "_smoke")     # 合成数据落这里（不删除，避免沙箱删除守卫）

REC = struct.Struct("<IIIIIfII")


def _write_day(path, rows):
    """rows: [(date, open, high, low, close, amount, volume)]，价格 ×100 存 int。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        for d, o, h, l, c, a, v in rows:
            f.write(REC.pack(int(d), int(round(o * 100)), int(round(h * 100)),
                             int(round(l * 100)), int(round(c * 100)), float(a),
                             int(v), 0))


def _series(start_close=10.0, days=30, drift=0.01, amount=200_000_000.0):
    """生成一条单调上涨的小序列（用于精确断言）。"""
    rows = []
    c = start_close
    for i in range(days):
        d = 20260101 + i
        o = c * (1 + drift / 2)
        c2 = c * (1 + drift)
        h = max(o, c2) * 1.005
        l = min(o, c2) * 0.995
        rows.append((d, o, h, l, c2, amount, 1_000_000))
        c = c2
    return rows


def test_day_roundtrip():
    from . import day_reader
    path = os.path.join(SMOKE_DIR, "sh600000.day")
    rows = _series()
    _write_day(path, rows)
    bars = day_reader.read_day_tail(path, 80)
    assert len(bars) == len(rows), f"往返行数 {len(bars)} != {len(rows)}"
    assert abs(bars[-1]["close"] - rows[-1][4]) < 0.011, "收盘价往返不匹配"
    assert bars[0]["date"] == str(rows[0][0])
    print("  [OK] .day 写→读往返（struct <IIIIIfII>）")


def test_factors():
    from . import five_factor
    rows = _series(days=30, drift=0.01)
    bars = [{"date": str(d), "open": o, "high": h, "low": l, "close": c,
             "amount": a, "volume": v} for d, o, h, l, c, a, v in rows]
    f = five_factor.compute_factors(bars)
    assert f is not None
    # ret20 = close[-1]/close[-21]-1，序列每步 +1%
    import math
    expect_ret20 = (1.01 ** 20) - 1
    assert abs(f["ret20"] - expect_ret20) < 1e-6, f"ret20 {f['ret20']} != {expect_ret20}"
    assert f["vol20"] < 1e-6, "恒定涨幅序列 vol20 应≈0"
    assert f["maxret20"] - 0.01 < 1e-9
    assert abs(f["loga20"] - math.log1p(200_000_000.0)) < 1e-6
    assert f["liq20"] == 200_000_000.0
    print("  [OK] 五因子计算（ret20/vol20/maxret20/loga20/liq20 精确断言）")


def test_screen_end2end():
    from . import day_reader, screen
    # 三只：A 超跌反转(高得分)、B 中规中矩、C 20日大涨(应被 V1 剔除)
    for code, drift, amount in (("600001", -0.03, 300_000_000.0),   # A 跌
                                ("600002", 0.001, 300_000_000.0),  # B 平
                                ("600003", 0.05, 300_000_000.0)):  # C 大涨
        _write_day(os.path.join(SMOKE_DIR, f"sh{code}.day"),
                   _series(days=30, drift=drift, amount=amount))
    vipdoc = os.path.join(SMOKE_DIR, "vipdoc")
    sh_lday = os.path.join(vipdoc, "sh", "lday")
    os.makedirs(sh_lday, exist_ok=True)
    import shutil
    for code in ("600001", "600002", "600003"):
        src = os.path.join(SMOKE_DIR, f"sh{code}.day")
        shutil.copy(src, os.path.join(sh_lday, f"sh{code}.day"))

    res = screen.run(vipdoc, top_n=3, out=os.path.join(SMOKE_DIR, "smoke_out.json"))
    top_codes = [t["code"] for t in res["top"]]
    assert "600001" in top_codes, f"反转股应入选: {top_codes}"

    res2 = screen.run(vipdoc, top_n=3, exclude_ret20_top=0.20)
    v1_codes = [t["code"] for t in res2["top"]]
    assert "600003" not in v1_codes, f"V1 应剔除 20 日大涨的 600003: {v1_codes}"
    print("  [OK] 端到端 screen（合成 vipdoc 树 + V1 尾部剔除）")


if __name__ == "__main__":
    print("tdx_native 冒烟自测")
    test_day_roundtrip()
    test_factors()
    test_screen_end2end()
    print("全部通过 ✅")
