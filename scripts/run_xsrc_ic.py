# -*- coding: utf-8 -*-
"""H-XSRC：跨源验证 —— 在独立源（腾讯）上重算因子 IC，对比主干符号。

## 回答什么

**四个因子的 IC 方向，在独立数据源上是否一致？**
（详见 `XSOURCE_VALIDATION_PREREG.md`）

- 方向一致 → 结论**不依赖数据源**（可信度大幅提升）
- 方向翻转 → ⚠️ **20 项实验、65 个文档全部要重新审视**

## 口径（与主干严格一致）

- **因子定义**：**直接复用** `run_tdx_universe_ic._factors_at`
  （该函数与生产 `five_factor.compute_factors` 逐字一致）
- **IC 口径**：`step=5`、`horizon=5`、截面 Spearman、`min_cross_section=200`
- **窗口**：与 H-CD 相同的 W1~W5 + R
- **复权**：腾讯 `qfq`（前复权）—— 与主干一致
- **流动性门槛**：**不过滤**（H-CD 已证明门槛会干预 amihud/loga20）

## ⚠️ amount 是估算值

腾讯不返回成交额。本脚本用 `volume(股) × (H+L+C)/3` 估算
（与 `fetch_delisted_full.py` 一致）。**该字段是 amihud20 / loga20 的定义变量**，
故这两个因子的结论应视为**较弱证据**（在报告中标注）。

用法::

    python scripts/run_xsrc_ic.py --src D:/xs_tencent/klines \\
        --out reports/xsource/XSRC.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FACTORS = ["ret20", "vol20", "amihud20", "loga20", "maxret20"]
DIRECTIONS = {"ret20": -1, "vol20": -1, "amihud20": 1, "loga20": -1,
              "maxret20": -1}
WINDOWS = [("W1", "20030101", "20071231"), ("W2", "20080101", "20121231"),
           ("W3", "20130101", "20171231"), ("W4", "20180101", "20221231"),
           ("W5", "20230101", "20260930"), ("R", "20210802", "20260930")]

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "ic_mod", os.path.join(_here, "scripts", "run_tdx_universe_ic.py"))
ic_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic_mod)


# --------------------------------------------------------------------------
# 统计工具（与 run_factor_orthogonality.py 同源，保持全项目零 numpy）
# --------------------------------------------------------------------------


def _rank(v: List[float]) -> List[float]:
    order = sorted(range(len(v)), key=lambda k: v[k])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _pearson(x: List[float], y: List[float]) -> Optional[float]:
    n = len(x)
    if n < 10:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / math.sqrt(sxx * syy)


def _spearman(x: List[float], y: List[float]) -> Optional[float]:
    if len(x) < 10:
        return None
    return _pearson(_rank(x), _rank(y))


def _stat(v: List[float]) -> Dict:
    if len(v) < 2:
        return {"ic_mean": None, "t": None, "n": len(v)}
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
    t = m / (sd / math.sqrt(len(v))) if sd > 0 else 0.0
    return {"ic_mean": round(m, 6), "t": round(t, 2), "n": len(v)}


def load_series(path: str) -> Optional[Dict]:
    """读腾讯 CSV → 升序 date/closes/amounts。"""
    try:
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return None
    dates, closes, amounts = [], [], []
    for r in rows:
        try:
            d = str(r["date"]).replace("-", "").strip()
            c = float(r["close"])
            a = float(r.get("amount") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        if not d or c <= 0:
            continue
        if a <= 0:                                    # 估算 amount（与拉取端一致）
            try:
                h, lo = float(r["high"]), float(r["low"])
                v = float(r.get("volume") or 0)
                a = v * (h + lo + c) / 3.0
            except (ValueError, TypeError):
                continue
        dates.append(d)
        closes.append(c)
        amounts.append(a)
    if len(dates) < 40:
        return None
    order = sorted(range(len(dates)), key=lambda k: dates[k])
    return {"dates": [dates[k] for k in order],
            "closes": [closes[k] for k in order],
            "amounts": [amounts[k] for k in order]}


def main() -> int:
    ap = argparse.ArgumentParser(description="H-XSRC 跨源 IC 计算")
    ap.add_argument("--src", required=True, help="腾讯 CSV 目录")
    ap.add_argument("--codes", default="",
                    help="名单文件（JSON 或纯文本）。给定时**只算名单内的股票**，"
                         "并在输出里报告名单覆盖率 —— 防「目录混批」")
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--min-cross-section", type=int, default=200)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.src, "*.csv")))
    if not files:
        print(f"{args.src} 下无 CSV")
        return 2

    # ⚠️ 2026-10-13 补：样本身份核对（对象标识核对）。
    # 曾经目录里混了「300 名单」与「更早 1000 名单」两批，IC 按目录全算，
    # 得出 297 只 —— 与预注册的「seed=42 抽 300」不符，事后才发现。
    # 现在给 --codes 时只算名单内股票，并显式报告覆盖率。
    allowed = None
    codes_rel = ""
    if args.codes and os.path.exists(args.codes):
        try:
            with open(args.codes, encoding="utf-8") as fh:
                raw = fh.read()
            try:
                allowed = {d["code"] for d in json.loads(raw)
                           if isinstance(d, dict) and "code" in d}
            except json.JSONDecodeError:
                allowed = {ln.strip() for ln in raw.splitlines() if ln.strip()}
            codes_rel = os.path.abspath(args.codes)
        except OSError:
            allowed = None
    if allowed is not None:
        before = len(files)
        files = [f for f in files
                 if os.path.basename(f)[:-4] in allowed]
        print(f"[0/3] 名单核对：{before} 个 CSV → 名单内 {len(files)} 个"
              f"（名单要求 {len(allowed)}，覆盖率 "
              f"{len(files)/max(1,len(allowed))*100:.1f}%）")
        if len(files) < len(allowed):
            miss = len(allowed) - len(files)
            print(f"      ⚠️ 名单内有 {miss} 只尚未拉到（结论会标注覆盖率）")

    print(f"[1/3] 载入 {len(files)} 只 ...", flush=True)

    series: Dict[str, Dict] = {}
    for f in files:
        s = load_series(f)
        if s:
            series[os.path.basename(f)[:-4]] = s
    print(f"      有效 {len(series)} 只", flush=True)

    # 逐日收集横截面
    buckets: Dict[str, Dict[str, Dict]] = {t: {} for t, _s, _e in WINDOWS}
    for s in series.values():
        dates, closes, amounts = s["dates"], s["closes"], s["amounts"]
        for tag, ws, we in WINDOWS:
            for i in range(0, len(dates), args.step):
                d = dates[i]
                if not (ws <= d <= we):
                    continue
                if i < 21 or i + args.horizon >= len(dates):
                    continue
                f = ic_mod._factors_at(closes, amounts, i, liq_min=None)
                if f is None:
                    continue
                c0, c1 = closes[i], closes[i + args.horizon]
                if c0 <= 0:
                    continue
                slot = buckets[tag].setdefault(
                    d, {"f": {k: [] for k in FACTORS}, "y": []})
                for k in FACTORS:
                    slot["f"][k].append(f[k])
                slot["y"].append(c1 / c0 - 1)

    print("[2/3] 逐期算 IC ...", flush=True)
    out: Dict = {"windows": {}, "n_stocks": len(series),
                 # 样本身份核对（对象标识核对）
                 "codes_file": codes_rel,
                 "codes_required": len(allowed) if allowed else None,
                 "codes_covered": len(files) if allowed else None,
                 # ⚠️ 数据集标识（整改清单 P0-2）—— 缺了会被
                 # test_data_asset_registry 抓住（2026-10-13 确实被抓住过一次）。
                 "source": str(Path(args.src).resolve()),
                 "source_dataset_id": "D5",
                 "amount_is_estimated": True,
                 "note": "amount 为 volume×(H+L+C)/3 估算值；"
                         "amihud20/loga20 结论应视为较弱证据"}
    for tag, _s, _e in WINDOWS:
        # ⚠️ 不能用 dict.fromkeys(FACTORS, []) —— 那会让 5 个因子**共享同一个
        # list 对象**，append 全进同一个列表，导致 5 个因子 IC 完全相同。
        # （2026-10-12 实测踩到：我曾为消 ruff C420 改成 dict.fromkeys，
        #  结果 5 因子 IC 全是 -0.0326/-4.34。）
        got = {k: [] for k in FACTORS}
        n_cs = 0
        for _d, slot in buckets[tag].items():
            y = slot["y"]
            if len(y) < args.min_cross_section:
                continue
            n_cs += 1
            for k in FACTORS:
                ic = _spearman(slot["f"][k], y)
                if ic is not None:
                    got[k].append(ic)
        if not n_cs:
            continue
        out["windows"][tag] = {"cross_sections": n_cs,
                               "ic": {k: _stat(got[k]) for k in FACTORS}}

    print("[3/3] 对比主干符号 ...")
    mv_path = os.path.join(_here, "reports", "cross_decade", "VERDICT.json")
    out["main_verdict_ref"] = os.path.relpath(mv_path, _here) \
        if os.path.exists(mv_path) else "(不存在)"

    print(f"\n  {'因子':<10}{'冻结':>5}", end="")
    for tag, _s, _e in WINDOWS:
        print(f"{tag:>18}", end="")
    print()
    reg = ["W1", "W2", "W3", "W4", "W5"]
    consistent: Dict[str, int] = dict.fromkeys(FACTORS, 0)
    flipped: Dict[str, List[str]] = {k: [] for k in FACTORS}
    # ⚠️ 2026-10-12 修正：区分「方向不一致」与「无法判定（无数据）」。
    # 原实现把 W1/W2 的「无数据」也计入「未同号」，导致 4/4 有效窗口全同号的
    # 因子被判 3/5 →「整体存疑」——**机械误判**：无数据 ≠ 方向相反。
    # 整改清单 P0-1 要求「不允许择优汇报」，同样要求如实区分「相反」与「缺失」。
    for k in FACTORS:
        print(f"  {k:<10}{DIRECTIONS[k]:>+5}", end="")
        for tag, _s, _e in WINDOWS:
            w = out["windows"].get(tag)
            if not w:
                print(f"{'—':>18}", end="")
                continue
            v = w["ic"][k]
            if v["ic_mean"] is None:
                print(f"{'n/a':>18}", end="")
                continue
            ok = (v["ic_mean"] > 0) == (DIRECTIONS[k] > 0)
            if ok:
                if tag in reg:
                    consistent[k] += 1
            else:
                flipped[k].append(tag)
            print(f"{v['ic_mean']:+.4f}/{v['t']:+.2f}{'✓' if ok else '✗':>3}",
                  end="")
        print()
    out["consistent_windows"] = consistent

    # 覆盖率（防「无数据被悄悄当成一致」或「当成不一致」）
    usable = [t for t, _s, _e in WINDOWS if out["windows"].get(t)]
    missing = [t for t, _s, _e in WINDOWS if not out["windows"].get(t)]
    out["coverage"] = {"usable_windows": usable, "missing_windows": missing,
                       "n_stocks": len(series)}
    print(f"\n  窗口覆盖：可用 {len(usable)}/{len(WINDOWS)}"
          + (f"　缺失 {missing}" if missing else ""))

    # 判定：在**可用正式窗口**里数同号数（而非在全部 6 个里数）
    n_reg_usable = sum(1 for t in reg if out["windows"].get(t))
    n_ok = sum(1 for k in FACTORS
               if n_reg_usable > 0 and consistent[k] >= min(4, n_reg_usable)
               and not flipped[k])
    if missing:
        concl = (f"⚠️ 覆盖率不足（缺 {missing}）→ 判定降级为「部分一致」；"
                 f"既不得当作「跨源一致」，也不得当作「方向相反」")
    elif n_ok >= 4:
        concl = "跨源一致"
    elif n_ok == 3:
        concl = "部分一致"
    else:
        concl = "⚠️ 整体存疑（须上报，启动全项目复审）"
    out["verdict"] = {
        "factors_consistent_ge4": n_ok,
        "n_regular_windows_usable": n_reg_usable,
        "flipped": {k: v for k, v in flipped.items() if v},
        "conclusion": concl}
    print(f"\n  → 同号因子 {n_ok}/5（可用正式窗口 {n_reg_usable} 个）；"
          f"翻转 {[k for k, v in flipped.items() if v]}")
    print(f"  → 判定：{concl}")

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print(f"已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
