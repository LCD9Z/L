# -*- coding: utf-8 -*-
r"""五因子日度选股（v2 认证数据源版，零第三方依赖）。

因子定义与 `D:\lost\pipeline\engine\phase122_daily_auto.py`（冻结引擎）逐字一致，
方向与 `scripts/run_factor_study.py` 检验的先验一致（v1 数据集上 5/5 因子 |t|≥3.78）：

    ret20    = close/close.shift(20)-1              方向 -1（中期反转）
    vol20    = std(daily_returns, 20)               方向 -1（低波动异象）
    amihud20 = mean(|ret|/amount, 20)               方向 +1（非流动性溢价）
    loga20   = log1p(mean(amount, 20))              方向 -1（规模/流动性）
    maxret20 = max(daily_returns, 20)               方向 -1（MAX 效应/博彩偏好）

    流动性门槛：liq20 = mean(amount, 20) >= 1 亿元
    得分 = 五因子百分位秩 × 方向 的均值，取 Top-N。

相对 lost/pipeline 的升级（本脚本仅消费 v2 数据集）：
  - 前复权口径（除权假跳空不再污染动量因子）
  - **逐日 is_st 状态剔除**（源数据集自带，替代"按名称去 ST/退"）
  - 股票池来自 PIT 认证子集（含 239 只退市股），sha256 元数据在侧

声明：因子 IC 证据来自 v1 数据集检验；**该组合尚未在 v2 上重跑 IC 与门禁**，
输出仅供研究观察，不构成投资建议，不接入任何真实交易。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIRECTIONS = {"ret20": -1, "vol20": -1, "amihud20": 1, "loga20": -1, "maxret20": -1}
LIQ_MIN = 1e8
TAIL = 25  # 因子最长回看 20 + 1 个前收，取尾部 25 行足够（与流水线"尾 70"等价但更省）


def _pct_rank(values: List[float]) -> List[float]:
    """平均秩百分位（并列取平均秩，与 pandas rank(pct=True, method='average') 一致）。"""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return [r / n for r in ranks]


def _tail_bars(path: Path, tail: int) -> List[Dict[str, str]]:
    """只读文件尾部：简单起见整文件流式读取，仅保留最后 tail 行（单文件 ~100KB，快）。"""
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            if len(rows) > tail * 3:  # 控制内存：只留最近一段
                del rows[:-tail]
    return rows[-tail:]


def screen(dataset: str, top_n: int = 20, as_of: str = "", liq_min: float = LIQ_MIN,
           min_bars: int = 21) -> Dict[str, Any]:
    stock_dir = Path(dataset) / "stocks"
    codes = sorted(p.stem for p in stock_dir.glob("*.csv")
                   if (stock_dir / f"{p.stem}.metadata.json").exists())
    cands: List[Dict[str, Any]] = []
    n_total = n_st_removed = n_short = n_illiq = 0
    for code in codes:
        bars = _tail_bars(stock_dir / f"{code}.csv", TAIL)
        if as_of:
            bars = [b for b in bars if b["date"] <= as_of]
        if len(bars) < min_bars:
            n_short += 1
            continue
        last = bars[-1]
        if last.get("is_st") == "1":
            n_st_removed += 1
            continue
        closes = [float(b["close"]) for b in bars]
        amounts = [float(b["amount"] or 0) for b in bars]
        rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
        n = len(closes)
        liq20 = sum(amounts[-20:]) / 20.0
        if liq20 < liq_min:
            n_illiq += 1
            continue
        ret20 = closes[-1] / closes[-21] - 1
        vol20 = math.sqrt(sum((r - sum(rets[-20:]) / 20.0) ** 2 for r in rets[-20:]) / 20.0)
        abs_amt = [(abs(rets[i - 1]) / amounts[i] if amounts[i] > 0 else None)
                   for i in range(1, n)]
        vals = [v for v in abs_amt[-20:] if v is not None]
        amihud20 = sum(vals) / len(vals) if vals else None
        loga20 = math.log1p(liq20)
        maxret20 = max(rets[-20:])
        if None in (amihud20,) or closes[-21] <= 0:
            n_short += 1
            continue
        cands.append({
            "code": code, "name": last.get("name", ""),
            "ret20": ret20, "vol20": vol20, "amihud20": amihud20,
            "loga20": loga20, "maxret20": maxret20, "liq20": liq20,
        })
        n_total += 1

    ranks = {k: _pct_rank([c[k] for c in cands]) for k in DIRECTIONS}
    for i, c in enumerate(cands):
        c["score"] = sum(ranks[k][i] * d for k, d in DIRECTIONS.items()) / len(DIRECTIONS)
    cands.sort(key=lambda c: (-c["score"], c["code"]))
    top = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in c.items()}
           for c in cands[:top_n]]
    return {
        "signal_date": (bars[-1]["date"] if cands else as_of),
        "as_of": as_of or None,
        "universe": {"with_data": len(codes), "scored": n_total,
                     "st_removed": n_st_removed, "short_history": n_short,
                     "illiquid_removed": n_illiq, "liq_min": liq_min},
        "top": top,
        "note": "因子 IC 证据来自 v1 数据集（|t|≥3.78）；组合未在 v2 重跑 IC 与门禁；"
                "仅供研究观察，不构成投资建议，不接入真实交易。",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="五因子日度选股（v2 数据源）")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v2")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--as-of", default="", help="历史时点（YYYY-MM-DD），缺省用各股最新日期")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    t0 = time.time()
    result = screen(args.dataset, top_n=args.top, as_of=args.as_of)
    result["runtime_sec"] = round(time.time() - t0, 1)
    out = json.dumps(result, ensure_ascii=False, indent=1)
    print(out[:2000])
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"\n已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
