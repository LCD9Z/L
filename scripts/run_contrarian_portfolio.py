# -*- coding: utf-8 -*-
"""组合层面对照实验：基线动量(A) vs H-C1 反转复合(B)，**同一框架** A/B。

**假设、口径、窗口、判定标准均已在 `PORTFOLIO_AB_PREREG.md` 事前登记**，
本文件只是实现，不得在看到结果后调整任何参数。

两臂唯一差异是**选股信号**；建仓/平仓/成本/滑点/流动性/持仓数/权重全部相同，
因此本实验是**相对 A/B**，其绝对数值不与生产 `portfolio_backtest` 并列。

用法::

    python run_contrarian_portfolio.py --dataset D:/tdx_dataset
    python run_contrarian_portfolio.py --dataset D:/tdx_dataset --max-stocks 600
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import Costs, _trade_cost  # noqa: E402
from factors.factor_ic_lab import compute_factors  # noqa: E402
from risk.liquidity import dynamic_slippage, is_liquid  # noqa: E402
from walk_forward import score_history  # noqa: E402

# ---------------------------------------------------------------------------
# 事前登记：因子方向（与 ALPHA_HYPOTHESIS_PREREG.md 一致）
# ---------------------------------------------------------------------------
SIGNS: Dict[str, int] = {
    "ret_20": -1,
    "ret_5": -1,
    "vol_20": -1,
    "log_amount_20": -1,
    "max_ret_20": -1,
    "vol_ratio": -1,
    "amihud_20": +1,
}

TOP_N = 20
HORIZON = 5
STEP = 5
MIN_AVG_AMOUNT = 100_000_000
THRESHOLD = 70
MAX_RISK = 7
MIN_HIST = 30
MIN_CROSS = 50
INITIAL_CAPITAL = 1_000_000.0
WINDOWS = [("2024-01-02", "2026-09-30"), ("2025-01-02", "2026-09-30")]


def _load(dataset: str, max_stocks: int, min_rows: int = 200) -> Dict[str, Any]:
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(dataset, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]
    data: Dict[str, Any] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        bars = load_certified_csv(p, m)
        if len(bars) >= min_rows:
            data[c] = bars
    return data


def _pct_rank(values: Sequence[float]) -> List[float]:
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    for pos, i in enumerate(order):
        out[i] = pos / (n - 1)
    return out


def _eligible_idx(data, idx_map, code, day) -> Optional[int]:
    i = idx_map[code].get(day)
    if i is None:
        return None
    bars = data[code]
    if i + 1 + HORIZON >= len(bars):
        return None
    if len(bars[:i + 1]) < MIN_HIST:
        return None
    if not is_liquid(bars[:i + 1], MIN_AVG_AMOUNT):
        return None
    return i


def pick_baseline(data, idx_map, codes, day) -> List[Tuple[float, str, int]]:
    """A 臂：动量打分 score>=70 且 risk<=7，按 score 降序。"""
    cands = []
    for code in codes:
        i = _eligible_idx(data, idx_map, code, day)
        if i is None:
            continue
        s = score_history(data[code][: i + 1])
        if s["score"] >= THRESHOLD and s["risk"] <= MAX_RISK:
            cands.append((s["score"], code, i))
    cands.sort(key=lambda x: -x[0])
    return cands[:TOP_N]


def pick_contrarian(data, idx_map, codes, day) -> List[Tuple[float, str, int]]:
    """B 臂：7 因子等权秩合成，按 composite 降序。"""
    entries = []
    for code in codes:
        i = _eligible_idx(data, idx_map, code, day)
        if i is None:
            continue
        f = compute_factors(data[code], i)
        if f is None:
            continue
        if any(f.get(k) is None for k in SIGNS):
            continue
        entries.append((code, i, f))
    if len(entries) < MIN_CROSS:
        return []
    comp = [0.0] * len(entries)
    for k in SIGNS:
        pr = _pct_rank([float(e[2][k]) for e in entries])
        s = SIGNS[k]
        for idx, v in enumerate(pr):
            comp[idx] += s * v
    scored = [(comp[idx], entries[idx][0], entries[idx][1]) for idx in range(len(entries))]
    scored.sort(key=lambda x: -x[0])
    return scored[:TOP_N]


def _trade_return(bars, i, costs: Costs, position_value: float,
                  slip_mode: str = "flat") -> Optional[float]:
    """单笔收益（含成本）。

    slip_mode:
      flat    —— 固定 base 滑点（第一阶段口径，会低估小盘/非流动性个股）
      dynamic —— 按个股 20 日均成交额分档（生产级口径，见 risk/liquidity.dynamic_slippage）
    """
    entry_bar = bars[i + 1]
    exit_idx = i + 1 + HORIZON
    exit_bar = bars[exit_idx]
    if slip_mode == "dynamic":
        slip_buy = dynamic_slippage(bars[: i + 1], costs.slippage_rate)
        slip_sell = dynamic_slippage(bars[: exit_idx + 1], costs.slippage_rate)
    else:
        slip_buy = slip_sell = costs.slippage_rate
    entry_px = float(entry_bar["open"]) * (1 + slip_buy)
    exit_px = float(exit_bar["close"]) * (1 - slip_sell)
    if entry_px <= 0:
        return None
    shares = math.floor(position_value / entry_px / 100) * 100
    if shares <= 0:
        return None
    gross_buy = shares * entry_px
    total_buy = gross_buy + _trade_cost(gross_buy, "buy", costs)
    gross_sell = shares * exit_px
    proceeds = gross_sell - _trade_cost(gross_sell, "sell", costs)
    return (proceeds - total_buy) / total_buy


def run_arm(data, picker, start: str, end: str, slip_mode: str = "flat") -> Dict[str, Any]:
    idx_map = {
        code: {str(b["date"]): k for k, b in enumerate(bars)}
        for code, bars in data.items()
    }
    codes = list(data.keys())
    all_days = sorted({d for m in idx_map.values() for d in m})
    days = [d for d in all_days if start <= d <= end]
    rebal = days[MIN_HIST::STEP]

    equity = INITIAL_CAPITAL
    peak = equity
    mdd = 0.0
    trade_rets: List[float] = []
    n_periods = 0

    for day in rebal:
        picks = picker(data, idx_map, codes, day)
        if not picks:
            continue
        pos_value = equity / len(picks)
        rets = []
        for _, code, i in picks:
            r = _trade_return(data[code], i, costs=COSTS, position_value=pos_value,
                              slip_mode=slip_mode)
            if r is not None:
                rets.append(r)
        if not rets:
            continue
        cohort = sum(rets) / len(rets)  # 等权、满仓
        equity *= (1 + cohort)
        trade_rets.extend(rets)
        n_periods += 1
        peak = max(peak, equity)
        mdd = max(mdd, (peak - equity) / peak * 100 if peak else 0.0)

    years = (n_periods * HORIZON) / 252 if n_periods else 0.0
    total_ret = equity / INITIAL_CAPITAL - 1
    ann = ((equity / INITIAL_CAPITAL) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    wins = sum(1 for r in trade_rets if r > 0)
    return {
        "periods": n_periods,
        "trades": len(trade_rets),
        "final_equity": round(equity, 2),
        "total_return_pct": round(total_ret * 100, 2),
        "annualized_pct": round(ann, 2),
        "max_drawdown_pct": round(mdd, 2),
        "win_rate_pct": round(wins / len(trade_rets) * 100, 2) if trade_rets else 0.0,
    }


COSTS = Costs()


def load_benchmark(dataset: str):
    """加载沪深300基准（与 run_tdx_rolling_eval 同款：benchmark.csv + 认证）。"""
    from real_alpha_pipeline import load_certified_csv

    p = os.path.join(dataset, "benchmark.csv")
    m = os.path.join(dataset, "benchmark.metadata.json")
    if not (os.path.exists(p) and os.path.exists(m)):
        return None
    return load_certified_csv(p, m)


def bench_stats(bench, start: str, end: str) -> Optional[Dict[str, float]]:
    """窗口内基准的总收益与年化（按 252 交易日年化，与策略口径一致）。"""
    if not bench:
        return None
    bars = [b for b in bench if start <= str(b["date"]) <= end]
    if len(bars) < 2:
        return None
    first, last = float(bars[0]["close"]), float(bars[-1]["close"])
    if first <= 0:
        return None
    total = last / first - 1
    years = len(bars) / 252
    ann = ((1 + total) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    return {"days": len(bars), "total_return_pct": round(total * 100, 2),
            "annualized_pct": round(ann, 2)}


def _result_payload(results, verdict, slip_mode):
    """组装落盘结果。

    **必须记录成本模型**（`slip_mode`）。历史缺陷：一阶段（固定滑点）与二阶段
    （动态滑点）用同一脚本、不同滑点模型，产出的 `verdict` 文本**完全相同**，
    且 `params` 未记录 `slip_mode` → 两份归档 JSON 无法区分属哪一阶段
    （见 `AB_STUDIES_EVIDENCE.md`）。结论文案也已带上滑点标记，双重可辨。
    """
    return {
        "results": results,
        "verdict": verdict,
        "params": {
            "top_n": TOP_N, "horizon": HORIZON, "step": STEP,
            "threshold": THRESHOLD, "signs": SIGNS, "slip_mode": slip_mode,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="组合层面对照实验 A/B（事前登记）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-stocks", type=int, default=1000)
    ap.add_argument("--slippage", choices=("flat", "dynamic"), default="flat",
                    help="flat=固定滑点(第一阶段口径)；dynamic=按成交额分档(生产级)")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    print("=" * 92)
    print("组合层面对照实验：基线动量(A)  vs  H-C1 反转复合(B)　同一框架 A/B（事前登记）")
    print("=" * 92)
    print(f"口径：top_n={TOP_N}  持有={HORIZON}日  调仓每{STEP}日  "
          f"次日开盘建仓/第5日收盘平仓  含成本  滑点={args.slippage}")

    t0 = time.time()
    print("[1/3] 加载数据 ...")
    data = _load(args.dataset, args.max_stocks)
    bench = load_benchmark(args.dataset)
    print(f"      股票 {len(data):,} 只"
          + (f" / 基准 {len(bench):,} 根" if bench else " / 基准：缺失")
          + f"  ({time.time()-t0:.0f}s)")

    print("[2/3] 逐窗口运行两臂 ...")
    results: Dict[str, Dict[str, Any]] = {}
    for start, end in WINDOWS:
        a = run_arm(data, pick_baseline, start, end, args.slippage)
        b = run_arm(data, pick_contrarian, start, end, args.slippage)
        bm = bench_stats(bench, start, end)
        results[f"{start}~{end}"] = {"A_baseline": a, "B_contrarian": b,
                                     "benchmark": bm}
        print(f"\n  【窗口 {start} ~ {end}】")
        if bm:
            print(f"    {'基准 沪深300':<12} 年化 {bm['annualized_pct']:>+7.2f}%  "
                  f"总收益 {bm['total_return_pct']:>+7.2f}%  ({bm['days']}个交易日)")
        for label, r in (("A 基线动量", a), ("B H-C1反转", b)):
            ex = (r["annualized_pct"] - bm["annualized_pct"]) if bm else None
            exs = f"  超额 {ex:>+7.2f}pp" if ex is not None else ""
            print(f"    {label:<12} 年化 {r['annualized_pct']:>+7.2f}%  "
                  f"总收益 {r['total_return_pct']:>+7.2f}%  "
                  f"回撤 {r['max_drawdown_pct']:>6.2f}%  "
                  f"胜率 {r['win_rate_pct']:>5.1f}%{exs}")

    # 判定（事前登记，第三阶段含基准）
    print("\n" + "=" * 92)
    diffs, excesses = [], []
    for k, v in results.items():
        d = v["B_contrarian"]["annualized_pct"] - v["A_baseline"]["annualized_pct"]
        diffs.append(d)
        bm = v["benchmark"]
        if bm:
            e = v["B_contrarian"]["annualized_pct"] - bm["annualized_pct"]
            excesses.append(e)
            print(f"  {k}: B - A = {d:+.2f} pp    B - 基准 = {e:+.2f} pp")
        else:
            print(f"  {k}: B - A = {d:+.2f} pp    （无基准）")

    if excesses:
        if all(e > 2 for e in excesses):
            verdict = "B 年化超额两窗口均 > 2pp → 存在可实现 Alpha（样本内限定仍在）"
        elif all(e > 0 for e in excesses):
            verdict = "B 年化超额两窗口均 > 0 但 ≤ 2pp → 弱正超额"
        elif all(e <= 0 for e in excesses):
            verdict = "B 年化超额两窗口均 ≤ 0 → 无 Alpha（跑输基准）"
        else:
            verdict = "两窗口超额符号相反 → 证据不足"
    else:
        verdict = "无基准数据，仅能判定 A/B 相对优劣"

    if excesses:
        pass
    else:
        all_better = all(d > 2 for d in diffs)
        both_pos = all(v["B_contrarian"]["annualized_pct"] > 0 for v in results.values())
        if all_better and both_pos:
            verdict = "B 优于 A 且扣费后为正 → 支持「存在可实现 Alpha」（待基准指数复核）"
        elif all_better:
            verdict = "B 优于 A，但扣费后年化仍为负 → 仅支持「反转优于动量」，不支持「有 Alpha」"
        elif all(d > 0 for d in diffs):
            verdict = "B 略优于 A（差值 ≤ 2pp）→ 弱于/无显著差异"
        else:
            verdict = "B 未稳定优于 A → 无差异或更差"
    # 把成本模型写进结论文案：一/二阶段仅滑点模型不同，verdict 文本曾完全相同，
    # 导致归档结果无法区分属哪一阶段（见 AB_STUDIES_EVIDENCE.md）。
    verdict = f"[滑点={args.slippage}] {verdict}"
    print(f"\n判定：{verdict}")
    print("=" * 92)
    print(f"总耗时 {time.time()-t0:.0f}s")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(_result_payload(results, verdict, args.slippage),
                      fh, ensure_ascii=False, indent=1, default=str)
        print(f"结果已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
