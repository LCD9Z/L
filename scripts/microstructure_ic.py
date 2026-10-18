# -*- coding: utf-8 -*-
"""PREREG_02 的执行脚本：量价微观结构因子的 IC 检验与 Double Sort。

对应预注册：`MICROSTRUCTURE_FACTORS_PREREG.md`（下称"预注册"）。
本脚本**只做因子检验**，不产生任何交易信号、不改任何交易逻辑。

## 四段结构（与预注册章节一一对应）

| 段 | 预注册 | 做什么 |
|---|---|---|
| `gate` | §3.0 | **前置闸**：同口径复现 `reports/decay_h20_ic.json` 的 5 个因子 |
| `ic`   | §3.2 | 单变量截面 IC + 块自举 CI + `n_eff` + 年度稳健 |
| `dsort`| §3.4 | 控制 `momentum_5d` 的 3×5 双排序 + 单调性 |
| `all`  | §3.6 | 串起来并按 `FACTOR PASS` 合成判定 |

## 三处刻意的工程约束（都是踩过坑换来的）

1. **`n_eff` 用非重叠截面数，不用交易日数**。
   每 20 个交易日取 1 个截面、持有期也是 20 日 ⇒ 收益窗口**零重叠**，
   截面数就是独立观测数。PREREG_01 的 G-3 就死在"用重叠日数冒充样本量"。

2. **双排序的两道计数闸**：动量档 < 30 只 ⇒ 该截面 invalid（Critic 追加）；
   单元格 < 20 只 ⇒ 该动量档该截面剔除（预注册 §3.4）。
   两者都**只记 invalid、不补造、不放宽**。

3. **自举的块长以「截面」为单位**，1 个截面 = 20 个交易日。
   预注册写 `block=5 截面`（= 100 交易日，满足"≥ horizon"）；
   另跑 `block=10/20` 作敏感性并**全部报出**，不一挑一。

## 为什么收益口径是 `C[T+h]/O[T+1]-1`

`factors/factor_ic_lab.py::forward_return` 是 `close/close`（T 日收盘买进）。
T 日收盘价本身就是因子输入（CLV 直接用它）⇒ 同价进出会系统性抬高高 IC。
故本脚本自带 `forward_return_open`，**不改动** `factor_ic_lab` 的既有语义。

用法::

    python scripts/microstructure_ic.py build-cache
    python scripts/microstructure_ic.py gate
    python scripts/microstructure_ic.py ic
    python scripts/microstructure_ic.py dsort
    python scripts/microstructure_ic.py all
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import warnings
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factors.factor_ic_lab import spearman as _spearman_lab  # noqa: E402
# 复用 PREREG_01 的块自举与 BH（同一实现、同一分位公式，避免两套数字）。
# ⚠️ 同级脚本必须用**裸名**导入：`scripts/` 没有 `__init__.py`，mypy 会把
# `scripts/regime_attribution.py` 记成模块 `regime_attribution`；
# 若这里写 `from scripts.regime_attribution import ...`，同一文件就有两个模块名，
# mypy 报 "Source file found twice"。
from regime_attribution import (  # noqa: E402
    bh_adjust, block_bootstrap_means, ci_from_means, one_sided_p,
)
from validation.multiple_testing import deflated_family  # noqa: E402

# ---------------------------------------------------------------------------
# 常量（预注册 §二 / §3.2 / §3.4，改动须先改预注册）
# ---------------------------------------------------------------------------

DATASET = r"D:/tdx_dataset_v3"
STOCK_DIR = os.path.join(DATASET, "stocks")
PIT_UNIVERSE = os.path.join(DATASET, "pit_universe.json")
BENCHMARK = os.path.join(DATASET, "benchmark.csv")
OUT_DIR = r"D:/_ext_verify/microstructure"
ARCHIVE_IC = "reports/decay_h20_ic.json"

SECTION_START = "2017-01-03"     # 首个截面不早于此（前 61 行留给 warmup）
SECTION_STEP = 20                # 每 20 个交易日 1 个截面（与 h=20 对齐，零重叠）
WARMUP = 61                      # 最长回看：CLV/RC 需 60 日 + 1
H_MAIN = 20                      # 主持有期
H_AUX = 5                        # 辅助持有期（重叠，只报不作判据）

MIN_UNIVERSE = 150               # 截面有效股票下限
MIN_FACTOR_VALID = 100           # 单因子单截面有效值下限
MIN_BUCKET = 30                  # 动量档票数下限（Critic 追加，严于预注册）
MIN_CELL = 20                    # 双排序单元格下限（预注册 §3.4）

BLOCK = 5                        # 主块长（截面数）= 100 交易日
BLOCK_SENS = (10, 20)            # 敏感性块长
REPS = 1000
SEED = 20261018

GATE_TOL = 0.005                 # 预注册 §3.0 的 0.005 容差
GATE_MIN_PASS = 4                # 5 个因子里至少 4 个通过

#: 因子清单（预注册 §一）：3 个新增 + 10 个既有（构成 BH/DSR 的 13 族）
NEW_FACTORS: Tuple[str, ...] = ("qr_quiet_rally_5d", "gap_smoothness_20d",
                                "clv_close_location_20d")
OLD_FACTORS: Tuple[str, ...] = ("ret_1", "ret_5", "ret_20", "vol_20", "amihud_20",
                                "log_amount_20", "vol_ratio", "max_ret_20",
                                "dist_high_20", "price")
FAMILY_13: Tuple[str, ...] = NEW_FACTORS + OLD_FACTORS

#: 逐股票算出的字段（QR 依赖截面 z 分数，装配完再补，故不在此列）
PER_STOCK: Tuple[str, ...] = tuple(f for f in FAMILY_13
                                   if f != "qr_quiet_rally_5d") + (
    "_ret5_raw", "_vr_raw", "_mom5")

#: 预声明的方向（预注册 §1.2：已统一成"越大越好"，故全为 +1）
DIRECTION: Dict[str, int] = dict.fromkeys(NEW_FACTORS, +1)


# ---------------------------------------------------------------------------
# 滚动算子（纯 numpy，nan 安全）
# ---------------------------------------------------------------------------

def _roll_sum_count(x: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
    """返回 (窗口和, 窗口有效数)，窗口 = 截至当前行的 k 行。"""
    n = len(x)
    valid = np.isfinite(x)
    xs = np.where(valid, x, 0.0)
    cs = np.concatenate(([0.0], np.cumsum(xs)))
    cn = np.concatenate(([0], np.cumsum(valid)))
    out_s = np.full(n, np.nan)
    out_n = np.zeros(n, dtype=np.int64)
    if n >= k:
        out_s[k - 1:] = cs[k:] - cs[:-k]
        out_n[k - 1:] = cn[k:] - cn[:-k]
    return out_s, out_n


def _roll_mean(x: np.ndarray, k: int) -> np.ndarray:
    s, c = _roll_sum_count(x, k)
    out = np.full(len(x), np.nan)
    ok = c > 0
    out[ok] = s[ok] / c[ok]
    return out


def _roll_std(x: np.ndarray, k: int) -> np.ndarray:
    m1 = _roll_mean(x, k)
    m2 = _roll_mean(x * x, k)
    var = np.maximum(m2 - m1 * m1, 0.0)
    return np.sqrt(var)


def _roll_max(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < k:
        return out
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        win = np.lib.stride_tricks.sliding_window_view(x, k)
        out[k - 1:] = np.nanmax(win, axis=1)
    return out


def _roll_min(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < k:
        return out
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        win = np.lib.stride_tricks.sliding_window_view(x, k)
        out[k - 1:] = np.nanmin(win, axis=1)
    return out


def _shift(x: np.ndarray, k: int) -> np.ndarray:
    """`out[i] = x[i-k]`；不足处置 NaN。"""
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:-k]
    return out


# ---------------------------------------------------------------------------
# 面板缓存
# ---------------------------------------------------------------------------

PANEL_COLS = ("open", "high", "low", "close", "volume", "amount", "turnover", "is_st")


def _to_int_date(s: str) -> int:
    return int(s.replace("-", ""))


def build_cache(out_dir: str = OUT_DIR, verbose: bool = True) -> Dict[str, Any]:
    """把 `stocks/*.csv` 压成一个 mmap 友好的二进制面板。

    为什么要有缓存：5,667 个文件、约 1,100 万行，每次跑都重新解析要 ~90 秒，
    而本脚本要反复迭代（闸 → IC → 双排序）。缓存后加载是 mmap，秒级。
    """
    os.makedirs(out_dir, exist_ok=True)
    codes = sorted(f[:-4] for f in os.listdir(STOCK_DIR)
                   if f.endswith(".csv") and f[:-4].isdigit())
    rows: List[np.ndarray] = []
    dates: List[np.ndarray] = []
    offs = [0]
    kept: List[str] = []
    t0 = time.time()
    for i, code in enumerate(codes):
        path = os.path.join(STOCK_DIR, f"{code}.csv")
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                import csv as _csv
                rd = _csv.reader(fh)
                head = next(rd)
                idx = {name: head.index(name) for name in ("date", *PANEL_COLS)}
                d: List[int] = []
                mat: List[List[float]] = [[] for _ in PANEL_COLS]
                for row in rd:
                    try:
                        d.append(_to_int_date(row[idx["date"]]))
                        for j, name in enumerate(PANEL_COLS):
                            v = row[idx[name]]
                            mat[j].append(float(v) if v not in ("", "None") else math.nan)
                    except (IndexError, ValueError):
                        continue
        except OSError:
            continue
        if len(d) < WARMUP + H_MAIN + 2:
            continue
        arr = np.asarray(mat, dtype=np.float32).T          # (n, 8)
        dv = np.asarray(d, dtype=np.int32)
        order = np.argsort(dv, kind="stable")
        rows.append(arr[order])
        dates.append(dv[order])
        kept.append(code)
        offs.append(offs[-1] + len(d))
        if verbose and (i + 1) % 1000 == 0:
            print(f"  读入 {i + 1}/{len(codes)} … {time.time() - t0:.1f}s", flush=True)

    panel = np.concatenate(rows, axis=0)
    dts = np.concatenate(dates, axis=0)
    np.save(os.path.join(out_dir, "panel.npy"), panel)
    np.save(os.path.join(out_dir, "panel_dates.npy"), dts)
    np.save(os.path.join(out_dir, "panel_offsets.npy"), np.asarray(offs, dtype=np.int64))
    meta = {"codes": kept, "cols": list(PANEL_COLS), "n_rows": len(panel),
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(out_dir, "panel_codes.json"), "w", encoding="utf-8",
              newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False)
    if verbose:
        print(f"缓存完成：{len(kept)} 只 / {len(panel)} 行 / {time.time() - t0:.1f}s")
    return meta


class Panel:
    """mmap 面板：`slice(i)` 返回第 i 只股票的 (n, 8) 视图。"""

    def __init__(self, out_dir: str = OUT_DIR) -> None:
        self.dir = out_dir
        self.data = np.load(os.path.join(out_dir, "panel.npy"), mmap_mode="r")
        self.dates = np.load(os.path.join(out_dir, "panel_dates.npy"), mmap_mode="r")
        self.offsets = np.load(os.path.join(out_dir, "panel_offsets.npy"))
        with open(os.path.join(out_dir, "panel_codes.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.codes: List[str] = meta["codes"]
        self.col = {name: j for j, name in enumerate(meta["cols"])}

    def __len__(self) -> int:
        return len(self.codes)

    def slice(self, i: int) -> Tuple[np.ndarray, np.ndarray]:
        a, b = int(self.offsets[i]), int(self.offsets[i + 1])
        return np.asarray(self.data[a:b]), np.asarray(self.dates[a:b])


# ---------------------------------------------------------------------------
# 因子（预注册 §1.2 + 既有 10 个）
# ---------------------------------------------------------------------------

def compute_factors(bars: np.ndarray, col: Dict[str, int]) -> Dict[str, np.ndarray]:
    """对**一只股票的全部历史**算因子序列，返回 {因子名: 与 bars 等长的数组}。

    全部先转"越大越好"方向（预注册 §1.1），故 IC 的预声明符号一律为 +。
    """
    o = bars[:, col["open"]].astype(np.float64)
    h = bars[:, col["high"]].astype(np.float64)
    lo = bars[:, col["low"]].astype(np.float64)
    c = bars[:, col["close"]].astype(np.float64)
    v = bars[:, col["volume"]].astype(np.float64)
    a = bars[:, col["amount"]].astype(np.float64)

    n = len(c)
    r = np.full(n, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = c[1:] / c[:-1] - 1.0

    out: Dict[str, np.ndarray] = {}

    # ---- 既有 10 个 ----
    out["ret_1"] = r
    out["ret_5"] = np.where(_shift(c, 5) > 0, c / _shift(c, 5) - 1.0, np.nan)
    out["ret_20"] = np.where(_shift(c, 20) > 0, c / _shift(c, 20) - 1.0, np.nan)
    out["vol_20"] = _roll_std(r, 20)
    with np.errstate(divide="ignore", invalid="ignore"):
        illiq = np.where(a > 0, np.abs(r) / a, np.nan)
    out["amihud_20"] = _roll_mean(illiq, 20)
    ma_a = _roll_mean(a, 20)
    out["log_amount_20"] = np.where(ma_a > 0, np.log(ma_a), np.nan)
    ma_v = _roll_mean(v, 20)
    out["vol_ratio"] = np.where(ma_v > 0, v / ma_v, np.nan)
    out["max_ret_20"] = _roll_max(r, 20)
    hi20 = _roll_max(h, 20)
    out["dist_high_20"] = np.where(hi20 > 0, c / hi20 - 1.0, np.nan)
    out["price"] = c

    # ---- 新增 3 个（预注册 §1.2）----
    # F1 QR：价涨量缩。z 分数是**截面**算子，此处只给 (ret5, VR) 两个原料，
    # 在截面装配时再做 z_cs（见 `assemble_sections`）。
    out["_ret5_raw"] = out["ret_5"]
    out["_vr_raw"] = out["vol_ratio"]

    # F2 GAP：MA20(|跳空|) / MA20(|日收益|)，取负号 ⇒ 越平滑越大
    with np.errstate(divide="ignore", invalid="ignore"):
        gap_abs = np.where(_shift(c, 1) > 0, np.abs(o / _shift(c, 1) - 1.0), np.nan)
    mg = _roll_mean(gap_abs, 20)
    md = _roll_mean(np.abs(r), 20)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["gap_smoothness_20d"] = np.where(md > 0, -(mg / md), np.nan)

    # F3 CLV：20 日收盘位置均值（跳过 H=L 的日），有效天数 < 15 ⇒ 剔除
    rng = h - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        clv = np.where(rng > 0, (2.0 * c - h - lo) / rng, np.nan)
    clv_mean = _roll_mean(clv, 20)
    _, clv_cnt = _roll_sum_count(clv, 20)
    out["clv_close_location_20d"] = np.where(clv_cnt >= 15, clv_mean, np.nan)

    # 辅助因子（双排序的控制变量）
    out["_mom5"] = out["ret_5"]
    return out


# ---------------------------------------------------------------------------
# 前向收益（预注册 §2.1）
# ---------------------------------------------------------------------------

def forward_return_open(bars: np.ndarray, i: int, horizon: int,
                        col: Dict[str, int]) -> float:
    """`C[i+h] / O[i+1] - 1`：T 日算因子、T+1 开盘买入、持有 h 日收盘卖出。"""
    j = i + horizon
    if j >= len(bars) or i + 1 >= len(bars):
        return math.nan
    o1 = float(bars[i + 1, col["open"]])
    cj = float(bars[j, col["close"]])
    if not (o1 > 0) or not (cj > 0):
        return math.nan
    return cj / o1 - 1.0


def forward_return_close(bars: np.ndarray, i: int, horizon: int,
                         col: Dict[str, int]) -> float:
    """`C[i+h] / C[i] - 1`：既有 `forward_return` 的口径（仅用于 §3.0 闸对账）。"""
    j = i + horizon
    if j >= len(bars):
        return math.nan
    c0 = float(bars[i, col["close"]])
    cj = float(bars[j, col["close"]])
    if not (c0 > 0) or not (cj > 0):
        return math.nan
    return cj / c0 - 1.0


# ---------------------------------------------------------------------------
# 截面装配
# ---------------------------------------------------------------------------

def load_section_dates() -> List[str]:
    """截面网格：`SECTION_START` 起每 `SECTION_STEP` 个交易日取 1 个。"""
    with open(PIT_UNIVERSE, encoding="utf-8") as f:
        snaps = json.load(f)["snapshots"]
    days = sorted(snaps)
    days = [d for d in days if d >= SECTION_START]
    if len(days) <= WARMUP:
        raise SystemExit("交易日不足，无法构造截面")
    return days[WARMUP::SECTION_STEP]


def _zscore(x: np.ndarray) -> np.ndarray:
    """截面 z 分数（nan 安全，总体标准差）。"""
    m = np.nanmean(x)
    s = np.nanstd(x)
    if not np.isfinite(s) or s == 0:
        return np.full_like(x, np.nan)
    return (x - m) / s


def assemble_sections(panel: Panel, section_dates: Sequence[str],
                      verbose: bool = True) -> Dict[str, Any]:
    """把面板按截面装配成 `(n_sec, n_codes)` 的 float32 矩阵。

    返回的 `fields` 里除因子与收益外，还有 `_present`（PIT 成员且当日有行情）、
    `_is_st`（当日 ST 标记）。所有缺失一律 NaN，**不填、不补**。
    """
    sec_int = np.asarray([_to_int_date(d) for d in section_dates], dtype=np.int64)
    n_sec, n_codes = len(sec_int), len(panel)
    fields: Dict[str, np.ndarray] = {
        name: np.full((n_sec, n_codes), np.nan, dtype=np.float32)
        for name in (*FAMILY_13, "_ret5_raw", "_vr_raw", "_mom5",
                     f"_ret{H_MAIN}_open", f"_ret{H_MAIN}_close", f"_ret{H_AUX}_open")
    }
    present = np.zeros((n_sec, n_codes), dtype=bool)

    with open(PIT_UNIVERSE, encoding="utf-8") as f:
        snaps = json.load(f)["snapshots"]

    t0 = time.time()
    for ci, code in enumerate(panel.codes):
        bars, dts = panel.slice(ci)
        if len(dts) == 0:
            continue
        # 该股每个交易日落在哪个截面（向量化，不做 114×5667 双重循环）
        pos = np.searchsorted(sec_int, dts.astype(np.int64))
        hit = pos < n_sec
        pos_c = np.minimum(pos, n_sec - 1)
        hit &= sec_int[pos_c] == dts.astype(np.int64)
        if not hit.any():
            continue
        fvals = compute_factors(bars, panel.col)
        rows = np.where(hit)[0]
        spos = pos_c[hit]
        for r, s in zip(rows.tolist(), spos.tolist(), strict=True):
            if r < WARMUP:
                continue
            if code not in snaps.get(section_dates[s], ()):  # PIT 成员才计数
                continue
            if int(bars[r, panel.col["is_st"]]) == 1:
                continue
            present[s, ci] = True
            for name in PER_STOCK:
                fields[name][s, ci] = fvals[name][r]
            fields[f"_ret{H_MAIN}_open"][s, ci] = forward_return_open(
                bars, r, H_MAIN, panel.col)
            fields[f"_ret{H_MAIN}_close"][s, ci] = forward_return_close(
                bars, r, H_MAIN, panel.col)
            fields[f"_ret{H_AUX}_open"][s, ci] = forward_return_open(
                bars, r, H_AUX, panel.col)
        if verbose and (ci + 1) % 1000 == 0:
            print(f"  装配 {ci + 1}/{n_codes} … {time.time() - t0:.1f}s", flush=True)

    # QR 需要截面 z 分数 ⇒ 装配完再补
    fields["qr_quiet_rally_5d"] = _qr_from_raw(fields["_ret5_raw"], fields["_vr_raw"])
    fields["_present"] = present.astype(np.float32)
    return {"section_dates": list(section_dates), "fields": fields,
            "n_sec": n_sec, "n_codes": n_codes}


def _qr_from_raw(ret5: np.ndarray, vr: np.ndarray,
                 min_valid: int = MIN_FACTOR_VALID) -> np.ndarray:
    """逐截面 `100*(z_cs(ret5) - z_cs(VR))`。

    `min_valid` 必须可覆盖：生产用 `MIN_FACTOR_VALID=100`，
    但单测只造 3 只股票，硬编码 100 会把测试值全变 NaN（首版即踩到）。
    """
    out = np.full(ret5.shape, np.nan, dtype=np.float32)
    for s in range(ret5.shape[0]):
        a, b = ret5[s], vr[s]
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() < min_valid:
            continue
        z = 100.0 * (_zscore(a) - _zscore(b))
        out[s, ok] = z[ok].astype(np.float32)
    return out


# ---------------------------------------------------------------------------
# IC
# ---------------------------------------------------------------------------

def spearman(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    """复用 `factors.factor_ic_lab.spearman`（既有实现、既有测试覆盖）。"""
    return _spearman_lab(a, b)


def section_ic(fx: np.ndarray, ret: np.ndarray, min_valid: int = MIN_FACTOR_VALID
               ) -> Optional[float]:
    ok = np.isfinite(fx) & np.isfinite(ret)
    if int(ok.sum()) < min_valid:
        return None
    return spearman(fx[ok].tolist(), ret[ok].tolist())


def factor_ic_series(fields: Dict[str, np.ndarray], factor: str, ret_key: str
                     ) -> Dict[str, Any]:
    """逐截面 IC 序列（含被跳过截面的计数，不静默丢）。"""
    fx_all = fields[factor]
    ret_all = fields[ret_key]
    ics: List[Optional[float]] = []
    n_valid_vals: List[int] = []
    for s in range(fx_all.shape[0]):
        ok = np.isfinite(fx_all[s]) & np.isfinite(ret_all[s])
        n_valid_vals.append(int(ok.sum()))
        ics.append(None if ok.sum() < MIN_FACTOR_VALID
                   else spearman(fx_all[s][ok].tolist(), ret_all[s][ok].tolist()))
    got = [x for x in ics if x is not None]
    return {"ic_series": ics, "n_used": len(got), "n_skipped": len(ics) - len(got),
            "median_valid_per_section": (statistics.median(n_valid_vals)
                                         if n_valid_vals else 0)}


def summarize_ic(ics: Sequence[float], block: int = BLOCK, reps: int = REPS,
                 seed: int = SEED) -> Dict[str, Any]:
    """均值 + 块自举 CI + 单侧 p + 年度稳健。"""
    vals = [float(x) for x in ics]
    if len(vals) < 5:
        return {"n_eff": len(vals), "ic_mean": None, "ci": None}
    means = block_bootstrap_means(vals, reps=reps, block_size=block, seed=seed)
    ci = ci_from_means(means, 0.05)
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    t = (statistics.mean(vals) / (sd / math.sqrt(len(vals)))) if sd > 0 else None
    return {
        "n_eff": len(vals),
        "ic_mean": statistics.mean(vals),
        "ic_std": sd,
        "icir": (statistics.mean(vals) / sd) if sd > 0 else None,
        "t_normal": t,
        "ci95_lower": (ci or {}).get("lower"),
        "ci95_upper": (ci or {}).get("upper"),
        "p_one_sided": one_sided_p(means, reps),
        "positive_rate": sum(1 for x in vals if x > 0) / len(vals),
        "block_size": block,
    }


# ---------------------------------------------------------------------------
# Double Sort（预注册 §3.4）
# ---------------------------------------------------------------------------

def _bucket_by_rank(x: np.ndarray, k: int) -> np.ndarray:
    """按秩切成 k 档（并列不拆：同秩同档）。返回 0..k-1，无效为 -1。"""
    out = np.full(x.shape, -1, dtype=np.int64)
    ok = np.isfinite(x)
    n = int(ok.sum())
    if n < k:
        return out
    idx = np.where(ok)[0]
    order = idx[np.argsort(x[idx], kind="stable")]
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = np.arange(n, dtype=np.float64)
    pct = ranks / max(n - 1, 1)
    b = np.floor(pct * k).astype(np.int64)
    np.clip(b, 0, k - 1, out=b)
    out[idx] = b
    return out


def double_sort_section(fx: np.ndarray, mom: np.ndarray, ret: np.ndarray,
                        n_mom: int = 3, n_fac: int = 5,
                        min_bucket: int = MIN_BUCKET,
                        min_cell: int = MIN_CELL) -> Dict[str, Any]:
    """一个截面的动量中性价差。

    `D = mean_m ( g[m, 顶] - g[m, 底] )`；返回 `invalid=True` 时**不参与统计**。
    """
    ok = np.isfinite(fx) & np.isfinite(mom) & np.isfinite(ret)
    n = int(ok.sum())
    if n < MIN_UNIVERSE:
        return {"invalid": True, "reason": "universe_too_small", "n": n}
    mb = _bucket_by_rank(mom[ok], n_mom)
    fb = _bucket_by_rank(fx[ok], n_fac)
    rv = ret[ok]
    if (mb < 0).any() or (fb < 0).any():
        return {"invalid": True, "reason": "bucket_failed", "n": n}

    cells: Dict[Tuple[int, int], float] = {}
    counts: Dict[Tuple[int, int], int] = {}
    for m in range(n_mom):
        sel_m = mb == m
        if int(sel_m.sum()) < min_bucket:
            # Critic 追加的计数闸：动量档太薄，整截面作废（不是"这档跳过"）
            return {"invalid": True, "reason": "bucket_too_thin",
                    "n": n, "bucket": m, "bucket_n": int(sel_m.sum())}
        for q in range(n_fac):
            sel = sel_m & (fb == q)
            cnt = int(sel.sum())
            counts[(m, q)] = cnt
            if cnt < min_cell:
                continue
            cells[(m, q)] = float(rv[sel].mean())
    spans: List[Optional[float]] = []
    rhos: List[Optional[float]] = []
    for m in range(n_mom):
        if (m, 0) not in cells or (m, n_fac - 1) not in cells:
            spans.append(None)
            continue
        spans.append(cells[(m, n_fac - 1)] - cells[(m, 0)])
        qs = [cells.get((m, q)) for q in range(n_fac)]
        if all(v is not None for v in qs):
            rho = spearman(list(range(n_fac)), [float(v) for v in qs if v is not None])
            rhos.append(rho)
        else:
            rhos.append(None)
    if any(s is None for s in spans):
        return {"invalid": True, "reason": "cell_too_thin", "n": n,
                "counts_min": min(counts.values()) if counts else 0}
    return {"invalid": False, "n": n,
            "spread": float(np.mean(spans)),
            "spans": spans,
            "rhos": rhos,
            "cells": {f"{m}_{q}": v for (m, q), v in cells.items()},
            "counts_min": min(counts.values())}


def double_sort(fields: Dict[str, np.ndarray], factor: str, ret_key: str,
                n_mom: int = 3, n_fac: int = 5) -> Dict[str, Any]:
    fx, mom, ret = fields[factor], fields["_mom5"], fields[ret_key]
    per: List[Dict[str, Any]] = []
    for s in range(fx.shape[0]):
        per.append(double_sort_section(fx[s], mom[s], ret[s], n_mom, n_fac))
    valid = [p for p in per if not p.get("invalid")]
    reasons: Dict[str, int] = {}
    for p in per:
        if p.get("invalid"):
            reasons[p.get("reason", "?")] = reasons.get(p.get("reason", "?"), 0) + 1
    if len(valid) < 5:
        return {"n_valid": len(valid), "invalid_reasons": reasons, "summary": None}
    spreads = [p["spread"] for p in valid]
    means = block_bootstrap_means(spreads, reps=REPS, block_size=BLOCK, seed=SEED)
    ci = ci_from_means(means, 0.05)
    # 单调性：各动量档内 quintile 序与格均值的秩相关
    rhos_all: List[float] = []
    for p in valid:
        for rho in p["rhos"]:
            if rho is not None:
                rhos_all.append(float(rho))
    n_rho_pos = sum(1 for x in rhos_all if x > 0)
    return {
        "n_valid": len(valid),
        "invalid_reasons": reasons,
        "spread_mean": statistics.mean(spreads),
        "ci95_lower": (ci or {}).get("lower"),
        "ci95_upper": (ci or {}).get("upper"),
        "p_one_sided": one_sided_p(means, REPS),
        "rho_mean": statistics.mean(rhos_all) if rhos_all else None,
        "rho_positive_rate": (n_rho_pos / len(rhos_all)) if rhos_all else None,
        "cells_min_quantile": min(p["counts_min"] for p in valid),
        "summary": None,
    }


# ---------------------------------------------------------------------------
# 年度稳健（S-1d）
# ---------------------------------------------------------------------------

def year_stability(section_dates: Sequence[str], ics: Sequence[Optional[float]]
                   ) -> Dict[str, Any]:
    by_year: Dict[str, List[float]] = {}
    for d, v in zip(section_dates, ics, strict=False):
        if v is None:
            continue
        by_year.setdefault(d[:4], []).append(float(v))
    means = {y: statistics.mean(v) for y, v in sorted(by_year.items())}
    pos = sum(1 for v in means.values() if v > 0)
    return {"per_year_mean": means, "n_years": len(means),
            "n_positive_years": pos,
            "required": math.ceil(0.6 * len(means)) if means else 0}


# ---------------------------------------------------------------------------
# 落盘
# ---------------------------------------------------------------------------

def write_json(name: str, payload: Dict[str, Any]) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return path


def run_meta() -> Dict[str, Any]:
    import subprocess
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))), capture_output=True,
            text=True).stdout.strip()
    except OSError:
        head = "unknown"
    return {"head": head, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---------------------------------------------------------------------------
# 闸 B：独立实现的等价性校验（验证者 ≠ 被验证者）
# ---------------------------------------------------------------------------

def naive_factors_at(bars: np.ndarray, i: int, col: Dict[str, int]) -> Dict[str, float]:
    """按**预注册公式逐字**、用纯 Python 循环实现的因子值（无 numpy 向量化）。

    存在的唯一理由：给 `compute_factors` 找一个**独立的验证者**。
    向量化滚动算子（cumsum 求均值/方差、sliding_window_view 求极值）写错时
    输出往往是"看起来合理的小数"，靠肉眼永远发现不了 ——
    必须有一个按定义直算的参照物。
    """
    def f(name: str, k: int) -> List[float]:
        # ⚠️ 起点必须 max(0, ...)：numpy 的负索引会从尾部绕回来，切片变空
        # （首版直接写 `i-k+1`，在 i<199 时静默得到空列表，`rets[-1]` 才炸）
        return [float(x) for x in bars[max(0, i - k + 1):i + 1, col[name]]]

    close = f("close", 200)
    o, h, lo = f("open", 200), f("high", 200), f("low", 200)
    v, a = f("volume", 200), f("amount", 200)
    c_now = float(bars[i, col["close"]])

    rets: List[float] = []
    for j in range(1, len(close)):
        if close[j - 1] > 0:
            rets.append(close[j] / close[j - 1] - 1.0)
        else:
            rets.append(math.nan)

    out: Dict[str, float] = {}
    out["ret_1"] = rets[-1]
    out["ret_5"] = c_now / float(bars[i - 5, col["close"]]) - 1.0
    out["ret_20"] = c_now / float(bars[i - 20, col["close"]]) - 1.0
    w20 = rets[-20:]
    m = sum(x for x in w20 if math.isfinite(x)) / len(w20)
    out["vol_20"] = math.sqrt(sum((x - m) ** 2 for x in w20) / len(w20))
    illiq = [abs(rets[-20 + k]) / a[-20 + k] if a[-20 + k] > 0 else math.nan
             for k in range(20)]
    out["amihud_20"] = sum(illiq) / 20.0
    out["log_amount_20"] = math.log(sum(a[-20:]) / 20.0)
    out["vol_ratio"] = v[-1] / (sum(v[-20:]) / 20.0)
    out["max_ret_20"] = max(w20)
    out["dist_high_20"] = c_now / max(h[-20:]) - 1.0
    out["price"] = c_now
    gap_abs = [abs(o[-20 + k] / close[-21 + k] - 1.0) if close[-21 + k] > 0 else math.nan
               for k in range(20)]
    md = sum(abs(x) for x in w20) / 20.0
    out["gap_smoothness_20d"] = -(sum(gap_abs) / 20.0 / md) if md > 0 else math.nan
    clvs = []
    for k in range(20):
        hh, ll = h[-20 + k], lo[-20 + k]
        if hh > ll:
            clvs.append((2.0 * close[-20 + k] - hh - ll) / (hh - ll))
    out["clv_close_location_20d"] = (sum(clvs) / len(clvs)) if len(clvs) >= 15 else math.nan
    return out


def run_selfcheck(panel: Panel, n_codes: int = 40, n_sec: int = 12,
                  tol: float = 1e-9) -> Dict[str, Any]:
    """闸 B：同一份数据、同一批日期，`compute_factors` 必须与 `naive_factors_at` 相等。

    这是**确定性**的：没有未知的股票池、没有未知的日期网格，
    因此它比闸 A（对账一个协议未记录的归档）能真正证明「计算层没错」。
    """
    dates = load_section_dates()
    step = max(1, len(panel) // n_codes)
    idxs = list(range(0, len(panel), step))[:n_codes]
    picked = dates[:: max(1, len(dates) // n_sec)][:n_sec]

    worst: Dict[str, float] = {}
    n_checked = 0
    for ci in idxs:
        bars, dts = panel.slice(ci)
        if len(dts) == 0:
            continue
        fv = compute_factors(bars, panel.col)
        for d in picked:
            di = _to_int_date(d)
            r = int(np.searchsorted(dts, di))
            if r >= len(dts) or int(dts[r]) != di or r < WARMUP:
                continue
            nv = naive_factors_at(bars, r, panel.col)
            n_checked += 1
            for name, want in nv.items():
                got = float(fv[name][r])
                if not math.isfinite(want) and not math.isfinite(got):
                    continue
                diff = abs(got - want)
                worst[name] = max(worst.get(name, 0.0), diff)
    bad = {k: v for k, v in worst.items() if v > tol}
    return {"status": "passed" if not bad and n_checked else "blocked",
            "n_points_checked": n_checked, "tol": tol,
            "max_abs_diff": worst, "over_tol": bad,
            "meta": run_meta()}


# ---------------------------------------------------------------------------
# §3.0 同口径复现闸
# ---------------------------------------------------------------------------

VIPDOC = r"D:/new_tdx/vipdoc"
GATE_STEP = 8          # 归档口径：每 8 个交易日一个截面
GATE_N_SECTIONS = 60   # 归档口径：60 个截面
GATE_POOL = 1500       # 归档口径：1500 只

#: 归档 `ic.raw_factor` 的 5 个因子 → 本脚本的因子名
GATE_MAP: Dict[str, str] = {
    "ret20": "ret_20",
    "vol20": "vol_20",
    "amihud20": "amihud_20",
    "loga20": "log_amount_20",
    "maxret20": "max_ret_20",
}


def _vipdoc_calendar() -> List[int]:
    from tdx_native.day_reader import read_day_all
    rows = read_day_all(os.path.join(VIPDOC, "sh", "lday", "sh000001.day"))
    return [int(r["date"]) for r in rows if int(r["date"]) > 0]


def _qfq_index(panel: Panel) -> Dict[str, int]:
    """code → 面板下标（面板里的 close 就是前复权价）。"""
    return {c: i for i, c in enumerate(panel.codes)}


def _gate_bars(raw_rows: Sequence[Dict[str, Any]]) -> np.ndarray:
    """把 vipdoc 行转成面板同构的 (n, 8) 数组（缺列补 0/NaN）。"""
    n = len(raw_rows)
    out = np.zeros((n, 8), dtype=np.float64)
    out[:, 0] = [r["open"] for r in raw_rows]
    out[:, 1] = [r["high"] for r in raw_rows]
    out[:, 2] = [r["low"] for r in raw_rows]
    out[:, 3] = [r["close"] for r in raw_rows]
    out[:, 4] = [r["volume"] for r in raw_rows]
    out[:, 5] = [r["amount"] for r in raw_rows]
    out[:, 6] = np.nan          # turnover：vipdoc 无此列，本轮因子不依赖
    out[:, 7] = 0.0             # is_st：闸内不做 ST 过滤（归档亦未声明）
    return out


def gate_status(rows: Sequence[Dict[str, Any]], min_pass: int) -> str:
    """闸的判定（**二值**，纯函数，便于单测）。

    * `passed` —— `|Δ| ≤ tol` 的因子数 ≥ `min_pass`；
    * `blocked` —— 其余。

    ⚠️ 首版写过第三档 `passed_with_note`：允许「差一个、但差异在实测噪声底内」放行。
    已被**删除**——那正是「网开一面」。
    噪声底（同一实现下两个股票子样本的 IC 差）**只作为诊断量输出**，
    它证明的是「这个差与抽样噪声不可区分」，**不能**证明「口径已对齐」。
    用一个较弱的证据去软化一个较强的判据，等于把闸改成装饰。
    """
    n_pass = sum(1 for r in rows if r.get("pass"))
    return "passed" if n_pass >= min_pass else "blocked"


def _select_pool(mode: str, paths: Sequence[Tuple[str, str]], panel: Panel,
                 limit: int) -> List[Tuple[str, str]]:
    """选闸的股票池。

    * `code`   —— 按代码升序取前 `limit` 只（最朴素的解释）；
    * `liquid` —— 按**近 250 日均成交额**降序取前 `limit` 只（因子研究里更常见的口径）。

    归档只写了 `stocks=1500`，没写选法 ⇒ 两种都要跑，谁复现得好**必须写清**，
    不能只报复现成功的那一种（那等于用结果挑参数）。
    """
    if mode == "code":
        return list(paths[:limit])
    from tdx_native.day_reader import read_day_tail
    scored: List[Tuple[float, str, str]] = []
    for code, path in paths:
        try:
            tail = read_day_tail(path, 250)
        except OSError:
            continue
        if len(tail) < 60:
            continue
        amt = [r["amount"] for r in tail if r["amount"] > 0]
        if not amt:
            continue
        scored.append((sum(amt) / len(amt), code, path))
    scored.sort(reverse=True)
    return [(c, p) for _, c, p in scored[:limit]]


def run_gate(panel: Panel, tol: float = GATE_TOL, min_pass: int = GATE_MIN_PASS,
             pool_mode: str = "code", label_mode: str = "close") -> Dict[str, Any]:
    """用**未复权原始价**算因子、**前复权价**算标签，复现归档 IC。

    四项口径在这里被钉死（预注册 §3.0）：
      1. 股票池：vipdoc sh+sz 的 A 股 `.day`，按代码升序取前 `GATE_POOL` 只
      2. 日期网格：vipdoc 交易日历每 8 个交易日取 1 个，取**最后** 60 个
      3. 收益口径：`close→close`（归档未声明开盘口径，按最朴素解释）
      4. 复权：因子用原始价、标签用数据集的前复权 close
    """
    from tdx_native.day_reader import is_a_share_stock, read_day_all, scan_paths

    with open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), ARCHIVE_IC), encoding="utf-8") as f:
        arch = json.load(f)["ic"]["raw_factor"]

    cal = _vipdoc_calendar()
    qidx = _qfq_index(panel)

    trip = scan_paths(VIPDOC, ("sh", "sz"))      # (code, market, path)
    cand: List[Tuple[str, str]] = []
    for code, market, path in trip:
        # ⚠️ `scan_paths` 返回的 code 已剥掉市场前缀（如 '600000'），**不是** 'sh600000'
        if not is_a_share_stock(code, market):
            continue
        # ⚠️ 缺陷 #21：`is_a_share_stock` 的 `_SH_INDEX_CODES` 只排除了 5 个宽基指数，
        # sh 下的 000002/000003/… 共 33 个**指数**仍被当成股票。
        # 它们与同号深市股票（如 000002=万科A）**代码撞车**，会把指数行情
        # 配上个股的复权标签 ⇒ 必须先按市场排掉，否则闸的数据本身就是错的。
        if market == "sh" and code.startswith("000"):
            continue
        if code in qidx:
            cand.append((code, path))
    cand.sort(key=lambda x: x[0])
    if not cand:
        raise SystemExit("闸：vipdoc 里没有可用的 A 股 day 文件")
    cand = _select_pool(pool_mode, cand, panel, GATE_POOL)

    # 截面：日历每 8 天一个，取最后 60 个
    pos_of = {d: i for i, d in enumerate(cal)}
    grid = cal[::GATE_STEP][-GATE_N_SECTIONS:]

    per_sec: Dict[int, List[Tuple[float, ...]]] = {d: [] for d in grid}
    # （half 是为噪声底准备的子样本容器，键与 grid 相同）
    half: Dict[int, List[Tuple[float, ...]]] = {d: [] for d in grid}
    t0 = time.time()
    for k, (code, path) in enumerate(cand):
        raw = read_day_all(path)
        if len(raw) < WARMUP + H_MAIN + 2:
            continue
        bars = _gate_bars(raw)
        fv = compute_factors(bars, {n: i for i, n in enumerate(PANEL_COLS)})
        dts = np.asarray([int(r["date"]) for r in raw], dtype=np.int64)

        pi = qidx[code]
        qbars, qdates = panel.slice(pi)
        q_close = qbars[:, panel.col["close"]].astype(np.float64)
        qd = qdates.astype(np.int64)

        for d in grid:
            if d not in pos_of:
                continue
            r = int(np.searchsorted(dts, d))
            if r >= len(dts) or dts[r] != d or r < WARMUP or r + H_MAIN >= len(dts):
                continue
            # 标签：前复权 close→close
            if label_mode == "open":
                # T+1 开盘建仓：起点用标签源（前复权）里**下一交易日**的开盘价
                q_open = qbars[:, panel.col["open"]].astype(np.float64)
                q1 = int(np.searchsorted(qd, dts[r + 1]))
                qh = int(np.searchsorted(qd, dts[r + H_MAIN]))
                if (q1 >= len(qd) or qd[q1] != dts[r + 1] or qh >= len(qd)
                        or qd[qh] != dts[r + H_MAIN]):
                    continue
                p0, p1 = float(q_open[q1]), float(q_close[qh])
                if not (p0 > 0) or not (p1 > 0):
                    continue
                ret = p1 / p0 - 1.0
            else:
                q0 = int(np.searchsorted(qd, d))
                qh = int(np.searchsorted(qd, dts[r + H_MAIN]))
                if (q0 >= len(qd) or qd[q0] != d or qh >= len(qd)
                        or qd[qh] != dts[r + H_MAIN]):
                    continue
                c0, c1 = float(q_close[q0]), float(q_close[qh])
                if not (c0 > 0) or not (c1 > 0):
                    continue
                ret = c1 / c0 - 1.0
            row = tuple(float(fv[GATE_MAP[m]][r]) for m in GATE_MAP)
            per_sec[d].append(row + (ret,))
            if k % 2 == 0:
                half[d].append(row + (ret,))
        if (k + 1) % 300 == 0:
            print(f"  闸读入 {k + 1}/{len(cand)} … {time.time() - t0:.1f}s", flush=True)

    def _ic_table(bucket: Dict[int, List[Tuple[float, ...]]]) -> Dict[str, Optional[float]]:
        names = list(GATE_MAP)
        acc: Dict[str, List[float]] = {n: [] for n in names}
        for rows in bucket.values():
            if len(rows) < MIN_FACTOR_VALID:
                continue
            arr = np.asarray(rows, dtype=np.float64)
            for j, n in enumerate(names):
                col = arr[:, j]
                ok = np.isfinite(col) & np.isfinite(arr[:, -1])
                if int(ok.sum()) < MIN_FACTOR_VALID:
                    continue
                rho = spearman(col[ok].tolist(), arr[ok, -1].tolist())
                if rho is not None:
                    acc[n].append(rho)
        return {n: (statistics.mean(v) if v else None) for n, v in acc.items()}

    mine = _ic_table(per_sec)
    h1 = _ic_table({d: [r for i, r in enumerate(v) if i % 2 == 0]
                    for d, v in per_sec.items()})
    h2 = _ic_table({d: [r for i, r in enumerate(v) if i % 2 == 1]
                    for d, v in per_sec.items()})

    rows: List[Dict[str, Any]] = []
    for name, mine_name in GATE_MAP.items():
        old = float(arch[name]["ic_mean"])
        new = mine.get(name)
        delta = None if new is None else abs(new - old)
        rows.append({
            "archive_key": name, "factor": mine_name,
            "archive_ic": old, "recomputed_ic": new, "abs_delta": delta,
            "pass": bool(delta is not None and delta <= tol),
            "n_sections": int(arch[name]["n"]) if isinstance(arch[name], dict) else None,
        })
    n_pass = sum(1 for r in rows if r["pass"])

    noise: Dict[str, Optional[float]] = {}
    for name in GATE_MAP:
        a, b = h1.get(name), h2.get(name)
        noise[name] = None if (a is None or b is None) else abs(a - b)
    noise_floor = (max(v for v in noise.values() if v is not None)
                   if any(v is not None for v in noise.values()) else None)

    status = gate_status(rows, min_pass)

    return {
        "meta": run_meta(),
        "status": status,
        "policy": {"tol": tol, "min_pass": min_pass, "n_factors": len(rows),
                   "sections": len(grid), "pool_requested": GATE_POOL,
                   "pool_used": len(cand), "step": GATE_STEP,
                   "pool_mode": pool_mode, "label_mode": label_mode},
        "comparison": rows,
        "n_pass": n_pass,
        "noise_floor": noise_floor,
        "noise_by_factor": noise,
        "assumptions": [
            f"池：vipdoc sh+sz A 股，选法={pool_mode}，取前 1500 只"
            "（归档只写 stocks=1500，未写选法）",
            "网格：日历每 8 个交易日一个截面，取最后 60 个（归档未写起点）",
            "收益：close→close（归档未声明是否为 T+1 开盘）",
            "复权：因子用原始价、标签用数据集前复权价（归档 note 明写）",
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PREREG_02 量价微观结构因子检验")
    ap.add_argument("cmd", choices=("build-cache", "selfcheck", "gate", "ic",
                                    "dsort", "all"))
    ap.add_argument("--sections", type=int, default=0, help="限制截面数（调试用）")
    ap.add_argument("--pool", choices=("code", "liquid"), default="code",
                    help="闸的股票池选法（默认 code；liquid=按成交额取前 1500）")
    ap.add_argument("--gate-out", default="gate.json", help="闸产物文件名")
    ap.add_argument("--label", choices=("close", "open"), default="close",
                    help="闸的标签口径：close=T→T+h 收盘；open=T+1 开盘→T+h 收盘")
    args = ap.parse_args(argv)

    if args.cmd == "build-cache":
        build_cache()
        return 0

    panel = Panel()

    if args.cmd == "selfcheck":
        sc = run_selfcheck(panel)
        print("闸 B：", sc["status"], "对比点", sc["n_points_checked"],
              "超差因子", sc["over_tol"])
        print("写出", write_json("selfcheck.json", sc))
        return 0 if sc["status"] == "passed" else 2

    if args.cmd in ("gate", "all"):
        g = run_gate(panel, pool_mode=args.pool, label_mode=args.label)
        path = write_json(args.gate_out, g)
        print(f"闸：{g['status']}（{g['n_pass']}/{len(g['comparison'])} 通过，"
              f"噪声底 {g['noise_floor']}）→ {path}")
        for r in g["comparison"]:
            print(f"  {r['archive_key']:9s} 归档={r['archive_ic']:+.6f} "
                  f"重算={(r['recomputed_ic'] if r['recomputed_ic'] is None else round(r['recomputed_ic'], 6))!s:>10s} "
                  f"|Δ|={r['abs_delta'] if r['abs_delta'] is None else round(r['abs_delta'], 6)} "
                  f"{'PASS' if r['pass'] else 'FAIL'}")
        if g["status"] == "blocked":
            print("闸未通过 ⇒ 按预注册 §3.0 不出 H1/H0 判定，终止。")
            return 2
        if args.cmd == "gate":
            return 0

    dates = load_section_dates()
    if args.sections > 0:
        dates = dates[:args.sections]
    print(f"截面 {len(dates)} 个：{dates[0]} ~ {dates[-1]}（池 {len(panel)} 只）")
    asm = assemble_sections(panel, dates)
    fields = asm["fields"]

    if args.cmd in ("ic", "all"):
        out: Dict[str, Any] = {"meta": run_meta(), "section_dates": dates,
                               "n_sec": asm["n_sec"], "factors": {}}
        for f in FAMILY_13:
            series = factor_ic_series(fields, f, f"_ret{H_MAIN}_open")
            row = summarize_ic([x for x in series["ic_series"] if x is not None])
            row["n_skipped"] = series["n_skipped"]
            row["median_valid_per_section"] = series["median_valid_per_section"]
            row["year_stability"] = year_stability(dates, series["ic_series"])
            sens = {}
            for b in BLOCK_SENS:
                sens[f"block_{b}"] = summarize_ic(
                    [x for x in series["ic_series"] if x is not None], block=b)
            row["block_sensitivity"] = sens
            row["direction_declared"] = DIRECTION.get(f, +1)
            row["ic_series"] = series["ic_series"]
            out["factors"][f] = row
            print(f"  {f:26s} IC̄={row.get('ic_mean')!s:>10.10} "
                  f"CI低={row.get('ci95_lower')!s:>10.10} n={row['n_eff']}")
        # ---- S-2 BH + S-4 DSR：必须喂**整个 13 因子族**，不能只喂 3 个新因子----
        pvals = {f: out["factors"][f].get("p_one_sided") for f in FAMILY_13}
        bh = bh_adjust(pvals, q=0.10)
        series_by_factor: Dict[str, Sequence[Any]] = {
            f: [x for x in out["factors"][f]["ic_series"] if x is not None]
            for f in FAMILY_13
        }
        fam = deflated_family(series_by_factor, alpha=0.05)
        out["family"] = {
            "m_nominal": len(FAMILY_13),
            "bh": bh,
            "dsr_n_trials": fam.get("n_trials"),
            "dsr_expected_max_sr": fam.get("expected_max_sr"),
            "dsr_sr_variance": fam.get("sr_variance"),
            "dsr_notes": fam.get("notes"),
            "trials": {f: {k: v for k, v in tr.items() if k != "series"}
                       for f, tr in (fam.get("trials") or {}).items()},
        }
        print("写出", write_json("ic_h20.json", out))
        for f in NEW_FACTORS:
            tr = (fam.get("trials") or {}).get(f, {})
            print(f"  {f:26s} p={pvals[f]!s:>8.8} BH={bh['p_adjusted'].get(f)!s:>9.9} "
                  f"dsr={tr.get('dsr')!s:>8.8} mtrl={tr.get('mtrl_deflated')!s:>8.8}")

    if args.cmd in ("dsort", "all"):
        out2: Dict[str, Any] = {"meta": run_meta(), "n_sec": asm["n_sec"], "factors": {}}
        for f in NEW_FACTORS:
            res = double_sort(fields, f, f"_ret{H_MAIN}_open")
            out2["factors"][f] = res
            print(f"  双排序 {f:26s} D={res.get('spread_mean')} "
                  f"CI低={res.get('ci95_lower')} n_valid={res.get('n_valid')}")
        print("写出", write_json("double_sort_h20.json", out2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
