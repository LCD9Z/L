# -*- coding: utf-8 -*-
"""研究脚本共享 helper（CODE_REDUNDANCY_AUDIT P2 收敛落点）。

**为什么集中**：``scripts/`` 下 62 个一次性研究脚本各自搬运同一批 helper
（审计 §3.1：完全重复 13 组 203 行）。集中后语义唯一、改一遍即全覆盖。

**纪律**：
  * 本模块只放**纯数据加载/无副作用** helper —— 不写文件、不发请求；
  * 每个 helper 的 docstring 注明**吸收了哪些原实现的位置与差异**
    （审计 §3.1/§3.2 逐条对应）；
  * 行为兼容性由 ``tests/test_study_common.py`` 的等价性测试逐条锁定
    （与各原实现同夹具对比，不允许「看起来一样」）；
  * **不放占位函数** —— 未收敛的 helper（``_day_files``/``_load_universe``/
    ``_tstat`` 等）留在各自原处，见剩余事项，不在此留 NotImplementedError 地雷。

**导入方式**：``from _study_common import ...``
（conftest.py 与各脚本自身均把仓库根/scripts 目录放入 sys.path）。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Sequence

from real_alpha_pipeline import load_certified_csv

__all__ = [
    "load_certified_stocks",
    "load_codes",
    "make_filter",
    "pct_rank",
    "pool_codes",
]


def load_certified_stocks(
    dataset: str,
    max_stocks: int,
    min_rows: int = 0,
    digits_only: bool = True,
    skip_errors: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """从本地数据集目录加载**已认证 CSV**（sha256 校验过的日线）。

    统一了 6 处本地 ``_load``（审计 §3.1 #1 完全重复 4 处 + §3.2 同构 2 处），
    三个参数的分辨差异全部显式化：

    ================  ==========================  ==========================
    参数              原 A 族 4 站点              原 B 族 2 站点
    ================  ==========================  ==========================
    ``digits_only``   True（只收 6 位数字代码）     False（收全部 .csv）
    ``skip_errors``   True（加载异常静默跳过）      False（异常直接抛出）
    ``min_rows``      0（不按行数过滤）             200（默认过滤短历史）
    ================  ==========================  ==========================

    * A 族原位置：``run_expert_filter_study:68`` / ``run_industry_ic_attribution:123``
      / ``run_stop_loss_ab:56`` / ``run_valuation_weight_ab:63``
      → 直接以默认参数 import 即可（``from _study_common import load_certified_stocks as _load``）；
    * B 族原位置：``run_contrarian_portfolio:59`` / ``run_contrarian_study:55``
      → 站点保留 2 行**参数绑定包装**（``min_rows=200, digits_only=False,
      skip_errors=False``），不把差异藏进默认值。

    ⚠️ ``max_stocks > 0`` 时按**等步长抽样**（``codes[int(i*step)]``）——
    与 6 处原实现逐字节一致；不是随机抽样（可复现）。
    ⚠️ 元数据缺失的代码**跳过**（6 处实现的共同行为：未认证不进研究样本）。
    """
    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                   if f.endswith(".csv") and (not digits_only or f[:-4].isdigit()))
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    out: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        try:
            bars = load_certified_csv(p, m)
        except Exception:
            if skip_errors:
                continue
            raise
        if min_rows > 0 and len(bars) < min_rows:
            continue
        out[c] = bars
    return out


def pool_codes(dataset: str) -> List[str]:
    """完整 PIT 股票池中**实际有认证文件**的代码（升序）。

    吸收：``run_concentration_study:64`` / ``run_universe_replication:47``
    （审计 §3.1 完全重复对；两处仅 docstring 差异）。读
    ``pit_universe.json`` 的 ``snapshots`` 并集，再按 csv+metadata 双存在过滤。
    """
    d = os.path.join(dataset, "stocks")
    with open(os.path.join(dataset, "pit_universe.json"), encoding="utf-8") as f:
        snaps = json.load(f)["snapshots"]
    pool: set = set()
    for v in snaps.values():
        pool.update(v)
    return sorted(c for c in pool
                  if os.path.exists(os.path.join(d, f"{c}.csv"))
                  and os.path.exists(os.path.join(d, f"{c}.metadata.json")))


def load_codes(dataset: str, codes: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    """按代码清单加载已认证 CSV（缺文件的代码跳过，**不抛错**）。

    吸收：``run_concentration_study:76`` / ``run_universe_replication:60``
    （审计 §3.1 完全重复对，字节级相同）。
    """
    d = os.path.join(dataset, "stocks")
    out: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p, m = os.path.join(d, f"{c}.csv"), os.path.join(d, f"{c}.metadata.json")
        if os.path.exists(p) and os.path.exists(m):
            out[c] = load_certified_csv(p, m)
    return out


def make_filter(excl: Dict[str, Dict[str, set]], factors: Sequence[str]):
    """「尾部排除」过滤器工厂：``flt(code, hist, day) -> bool``。

    吸收：``run_tail_exclusion_study:148`` / ``run_universe_replication:102``
    （审计 §3.1 完全重复对，字节级相同）。``factors`` 为空 ⇒ 返回 ``None``
    （调用方据此跳过整个过滤步骤，与原实现一致）。
    """
    if not factors:
        return None

    def flt(code: str, hist: List[Dict[str, Any]], day: str) -> bool:
        return all(code not in excl.get(f, {}).get(day, ()) for f in factors)

    return flt


def pct_rank(values: Sequence[float]) -> List[float]:
    """截面秩标准化到 [0,1]（对离群值稳健，事前登记的方法）。

    吸收：``run_contrarian_portfolio:79`` / ``run_contrarian_study:75``
    （审计 §3.1 完全重复对；两处仅 docstring 差异）。
    """
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    for pos, i in enumerate(order):
        out[i] = pos / (n - 1)
    return out
