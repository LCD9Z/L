# -*- coding: utf-8 -*-
"""Regime 分层归因：把「六窗口全负超额」按市场状态切片（**只做尸检**）。

预注册：`REGIME_ATTRIBUTION_PREREG.md`（含 §三.0 动手前核定的事实）。
判定：`REGIME_ATTRIBUTION_VERDICT.md`。

## 这个脚本**不做**什么

- 不实现 regime 过滤，**不**传 `position_scaler` 给回测引擎；
- 不调任何阈值/窗口/股票池；
- 不重跑回测 —— 输入是 `run_tdx_rolling_eval.py --dump-logs` 的产物
  （`equity_curve` + `trade_log` + `execution_stats`），与「六窗口全负超额」
  **完全同源**。

## 三个口径（事前固定，见预注册 §四）

- **4.1 日频（主证据）**：`equity_curve` → 日收益 → 按**当日** regime 聚合；
- **4.2 交易（入场日）**：按 `signal_date`（= 入场日前一交易日）的 regime 分组；
- **4.3 交易（出场日）**：按 `exit_date` 的 regime 分组（跨 regime 持有时的敏感性）。

4.2 与 4.3 结论若不同，**两套都报**，不择一。

## G-3「有效观测」的可复算定义

`horizon=5, top_n=5` ⇒ 相邻交易日的收益高度重叠，原始天数不是独立样本。
本脚本按 `n_eff = floor(n_days / horizon)` 计，窗口上限 = `floor(aligned/5)`
（最长窗口 894 日 → 179）。⇒ 只有某档占据该窗口 **≥56%** 交易日才可能达到 100，
这是**有意从严**：H1 若成立，必须在大样本上成立。

用法::

    python scripts/regime_attribution.py \
        --logged D:/_ext_verify/regime_attr/rolling_eval_v3_logged.json \
        --dataset D:/tdx_dataset_v3 \
        --out D:/_ext_verify/regime_attr/regime_attribution.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import sys
from pathlib import Path
from itertools import pairwise
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 三档顺序固定，产物里的键顺序也固定（便于 diff）
REGIMES: Tuple[str, ...] = ("震荡", "萌芽", "明确")
#: 数据不足 / 无标签的桶（不参与 G-1~G-3，但如实报出，避免「静默丢弃」）
UNLABELED = "无标签"
#: 年化折算交易日数：与 alpha.alpha_survival_lab.annualized_excess_arithmetic 的
#: 默认 252 一致（项目统一年化口径；预注册初稿误写 242，已在 §4.1 订正）
TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# 块自举（循环块，复刻 alpha.alpha_survival_lab.block_bootstrap_mean_ci 的算法）
# ---------------------------------------------------------------------------

def block_bootstrap_means(values: Sequence[float], reps: int = 1000,
                          block_size: int = 5, seed: int = 20261018) -> List[float]:
    """返回**升序**的块自举均值序列。

    复刻既有实现的理由：本脚本既需要置信区间（G-2）又需要单侧 p 值（G-4），
    同一次抽样应同时产出两者，不能跑两遍（跑两遍会得到互相矛盾的数字）。
    `--self-check` 会把它与 `block_bootstrap_mean_ci` 对账，确保没有走样。
    """
    vals = [float(x) for x in values]
    if len(vals) < 2:
        return []
    n = len(vals)
    block_size = max(1, min(int(block_size), n))
    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(int(reps)):
        sample: List[float] = []
        while len(sample) < n:
            start = rng.randrange(n)
            for j in range(block_size):
                sample.append(vals[(start + j) % n])
                if len(sample) >= n:
                    break
        means.append(sum(sample) / len(sample))
    means.sort()
    return means


def ci_from_means(means: Sequence[float], alpha: float = 0.05) -> Optional[Dict[str, float]]:
    """与 `block_bootstrap_mean_ci` 同一分位索引公式的 95% CI。"""
    if not means:
        return None
    m = len(means)
    lo_i = max(0, int((alpha / 2) * (m - 1)))
    hi_i = min(m - 1, int((1 - alpha / 2) * (m - 1)))
    return {"lower": means[lo_i], "upper": means[hi_i]}


def one_sided_p(means: Sequence[float], reps: int) -> Optional[float]:
    """H1: mean > 0 的单侧自举 p 值 = P(自举均值 <= 0)。"""
    if not means:
        return None
    le = sum(1 for x in means if x <= 0.0)
    return (le + 1) / (int(reps) + 1)


# ---------------------------------------------------------------------------
# 数据读取
# ---------------------------------------------------------------------------

def load_bars(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                out.append({"date": str(row["date"]),
                            "open": float(row["open"]), "high": float(row["high"]),
                            "low": float(row["low"]), "close": float(row["close"])})
            except (KeyError, TypeError, ValueError):
                continue
    out.sort(key=lambda b: b["date"])
    return out


def curve_returns(curve: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """权益曲线 → 日收益（与 real_alpha_pipeline._curve_returns 同定义）。"""
    out: Dict[str, float] = {}
    for prev, cur in pairwise(curve):
        try:
            pe = float(prev["equity"])
        except (KeyError, TypeError, ValueError):
            continue
        if pe > 0:
            out[str(cur["date"])] = float(cur["equity"]) / pe - 1.0
    return out


def bar_returns(bars: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for a, b in pairwise(bars):
        if a["close"] > 0:
            out[str(b["date"])] = b["close"] / a["close"] - 1.0
    return out


def labels_by_date(index_bars: Sequence[Dict[str, Any]],
                   oscillation_lt: float = 20.0,
                   trending_ge: float = 25.0) -> Dict[str, Dict[str, Any]]:
    """逐日 regime 标签（ADX 三档，**默认阈值不调参**）。

    直接用 `regime.adx_router` 的两个纯函数，而不是 `RegimeRouter.decide`：
    `decide` 在 `enabled=False` 时返回空标签，而 `enabled=True` 又会被误读成
    「叠加层已开」。这里只要标签，**不产生任何仓位系数**，从根上排除接线风险。
    """
    from regime.adx_router import classify_regime, compute_adx_by_date

    adx = compute_adx_by_date(list(index_bars), period=14)
    out: Dict[str, Dict[str, Any]] = {}
    for d in sorted(adx):
        out[d] = {"regime": classify_regime(adx[d], oscillation_lt, trending_ge),
                  "adx": round(adx[d], 6)}
    return out


def label_of(labels: Dict[str, Dict[str, Any]], day: str) -> str:
    """取该日标签；该日无 ADX（数据不足）⇒ 归入 `无标签`，不猜。"""
    rec = labels.get(str(day))
    return rec["regime"] if rec else UNLABELED


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------

def load_returns_source(path: str) -> Dict[str, float]:
    """读取等权基准日收益：`.json`（`reports/ew_benchmark_v3.json` 的 `series`）
    或 `.csv`（`<dataset>/benchmark_ew.csv`，列含 date/close）。

    两种来源**不是**逐位相同：CSV 的 close 只保留 6 位小数，日收益最大差
    `1.04e-8`（实测 1239 个共同交易日）。对账 `reports/_recalc/*` 时用 CSV 更严格，
    故两路都支持，由调用方按对账对象选择。
    """
    if path.lower().endswith(".csv"):
        return bar_returns(load_bars(path))
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "series" not in data:
        raise ValueError(f"等权基准 JSON 缺少 series 键: {path}")
    return {str(k): float(v) for k, v in data["series"].items()}


def _agg(values: Sequence[float]) -> Dict[str, Any]:
    """一组日收益的基础统计（**不做显著性判断**，判断留给 gates）。"""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "sum": None}
    mean = sum(values) / n
    std = statistics.pstdev(values) if n > 1 else 0.0
    return {"n": n, "mean": mean, "std": std, "sum": sum(values)}


def _daily_block(days: Sequence[str], strat: Dict[str, float],
                 benches: Dict[str, Dict[str, float]],
                 labels: Dict[str, Dict[str, Any]],
                 n_total_days: int, horizon: int, reps: int, block: int,
                 seed: int, alpha: float) -> Dict[str, Any]:
    """4.1 日频归因：按当日 regime 分桶，两套基准各自算超额。"""
    buckets: Dict[str, List[str]] = {r: [] for r in REGIMES}
    buckets[UNLABELED] = []
    for d in days:
        buckets[label_of(labels, d)].append(d)

    out: Dict[str, Any] = {}
    for regime, ds in buckets.items():
        n_days = len(ds)
        # n_eff：按 horizon 折算成「非重叠观测」个数（G-3 的门槛量）
        n_eff = n_days // horizon if horizon > 0 else n_days
        rec: Dict[str, Any] = {
            "n_days": n_days,
            "n_eff": n_eff,
            "share_of_window_pct": round(n_days / n_total_days * 100, 2) if n_total_days else None,
            "mean_strategy": (sum(strat[d] for d in ds) / n_days) if n_days else None,
            "benchmarks": {},
        }
        for bname, bser in benches.items():
            ex = [strat[d] - bser[d] for d in ds]
            agg = _agg(ex)
            means = block_bootstrap_means(ex, reps=reps, block_size=block, seed=seed) if len(ex) >= 2 else []
            ci = ci_from_means(means, alpha)
            p = one_sided_p(means, reps)
            rec["benchmarks"][bname] = {
                "n": agg["n"],
                "mean_excess": agg["mean"],
                "std_excess": agg["std"],
                # 朴素 t（仅参考；重叠观测下偏乐观，G-2 用块自举代替它）
                "t_naive": (agg["mean"] / (agg["std"] / math.sqrt(agg["n"]))
                            if agg["mean"] is not None and agg["std"] and agg["n"] > 1 else None),
                "ci95_lower": ci["lower"] if ci else None,
                "ci95_upper": ci["upper"] if ci else None,
                "p_one_sided": p,
                # 年化贡献：该档累计超额 / 窗口总交易日 × 242
                "ann_contrib": (agg["sum"] / n_total_days * TRADING_DAYS
                                if agg["sum"] is not None and n_total_days else None),
            }
        out[regime] = rec
    return out


def _trade_block(trades: Sequence[Dict[str, Any]], labels: Dict[str, Dict[str, Any]],
                 key: str) -> Dict[str, Any]:
    """4.2 / 4.3 交易归因：按 `key`（`signal_date` 或 `exit_date`）的 regime 分组。"""
    buckets: Dict[str, List[Dict[str, Any]]] = {r: [] for r in REGIMES}
    buckets[UNLABELED] = []
    for t in trades:
        d = t.get(key)
        buckets[label_of(labels, str(d) if d else "")].append(t)

    out: Dict[str, Any] = {}
    for regime, ts in buckets.items():
        rets = [float(t["return_pct"]) for t in ts if t.get("return_pct") is not None]
        held = [int(t["held_days"]) for t in ts if t.get("held_days") is not None]
        out[regime] = {
            "n_trades": len(ts),
            "n_with_return": len(rets),
            "win_rate_pct": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 2) if rets else None,
            # 单笔收益在产物里是百分数，这里另给 bps 便于跨表比较
            "mean_return_bps": round(sum(rets) / len(rets) * 100, 2) if rets else None,
            "mean_return_pct": round(sum(rets) / len(rets), 4) if rets else None,
            "mean_held_days": round(sum(held) / len(held), 2) if held else None,
        }
    return out


def bh_adjust(pvals: Dict[str, Optional[float]], q: float = 0.10) -> Dict[str, Any]:
    """Benjamini-Hochberg。

    **两个分母的区别（容易混，写清）**：

    - `m_total` = 名义假设数（3 档 × 2 基准 = 6），只用于**知情**；
    - 校正实际用 `k = m_tested` = **可检验**假设数（`p` 非 `None` 的那些）。

    为什么用 k：`None` 表示「样本不足，算不出 p」，该假设**没有被检验**，
    把它塞进分母会让其余假设凭空变宽松/变严，都不是它的语义。
    但 `None` 的假设在 `significant` 里必须显式为 `False` —— 不可检验
    **不等于**成立，也不允许从输出里消失（那是静默丢弃）。
    """
    items = [(k, v) for k, v in pvals.items() if v is not None]
    m = len(pvals)
    items.sort(key=lambda kv: kv[1])  # type: ignore[arg-type,return-value]
    out: Dict[str, Any] = {"m_total": m, "m_tested": len(items), "q_threshold": q,
                           "p_adjusted": {}, "significant": {}}
    if not items:
        return out
    k = len(items)
    adj = [0.0] * k
    prev = 1.0
    for i in range(k - 1, -1, -1):
        val = items[i][1] * k / (i + 1)
        prev = min(prev, val)
        adj[i] = min(1.0, prev)
    for i, (name, _) in enumerate(items):
        out["p_adjusted"][name] = adj[i]
        out["significant"][name] = adj[i] < q
    for name, v in pvals.items():
        if v is None:
            out["significant"][name] = False
    return out


# ---------------------------------------------------------------------------
# 失败单情景推演（Critic 的「跌停买不进 / 涨停买不进」担忧）
# ---------------------------------------------------------------------------

def _price_series(path: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                out[str(row["date"])] = float(row["close"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def failed_fill_sim(skips: Sequence[Dict[str, Any]], stock_dir: str,
                    horizon: int, initial_capital: float,
                    max_position_pct: float) -> Dict[str, Any]:
    """被一字涨停挡掉的买单：**假如成交**，持有 `horizon` 日（收盘买/收盘卖）会怎样。

    这是**情景推演**，不是结论：它假设「能在涨停价成交」，而这正是当时做不到的事，
    因此结果是**乐观上界**。存在的意义只有一个 —— 给出「执行约束把收益挪动了多少」
    的量级，回答「本引擎的负超额是否只是买不进而造成的假象」。
    """
    cache: Dict[str, Dict[str, float]] = {}
    rows: List[Dict[str, Any]] = []
    for s in skips:
        code, day = str(s.get("code")), str(s.get("next_date"))
        if code not in cache:
            p = os.path.join(stock_dir, f"{code}.csv")
            cache[code] = _price_series(p) if os.path.exists(p) else {}
        ser = cache[code]
        if day not in ser:
            rows.append({"code": code, "date": day, "status": "no_bar"})
            continue
        later = [d for d in sorted(ser) if d >= day]
        if len(later) < horizon:
            rows.append({"code": code, "date": day, "status": "insufficient_future"})
            continue
        exit_day = later[horizon - 1]
        r = ser[exit_day] / ser[day] - 1.0
        rows.append({"code": code, "date": day, "exit_date": exit_day,
                     "r": r, "status": "ok"})
    ok = [r for r in rows if r["status"] == "ok"]
    rets = [r["r"] for r in ok]
    notional = initial_capital * max_position_pct
    # Δtotal_return_pct（pp）= Σ(每笔假设成交的盈亏) / 初始资金 × 100
    delta_pp = sum(rets) * notional / initial_capital * 100 if rets else 0.0
    return {
        "n_skips": len(skips),
        "n_simulated": len(ok),
        "n_skipped_no_bar": sum(1 for r in rows if r["status"] == "no_bar"),
        "n_skipped_no_future": sum(1 for r in rows if r["status"] == "insufficient_future"),
        "mean_forward_return_pct": round(sum(rets) / len(rets) * 100, 3) if rets else None,
        "median_forward_return_pct": round(statistics.median(rets) * 100, 3) if rets else None,
        "share_positive_pct": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 2) if rets else None,
        "delta_total_return_pp": round(delta_pp, 3),
        "caveat": "乐观上界：假设能在涨停价成交，而当时恰恰做不到；只用于量级判断",
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Regime 分层归因（只读，不改交易逻辑）")
    ap.add_argument("--logged", required=True, help="run_tdx_rolling_eval.py --dump-logs 的产物")
    ap.add_argument("--dataset", required=True, help="数据集根（取 benchmark.csv 与 stocks/）")
    ap.add_argument("--ew-series", default="reports/ew_benchmark_v3.json",
                    help="等权基准日收益序列（G-4 的第二个基准）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--horizon", type=int, default=5, help="持仓周期，用于 n_eff 折算")
    ap.add_argument("--block", type=int, default=5, help="块自举块长")
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--q", type=float, default=0.10, help="BH 阈值（G-4）")
    ap.add_argument("--n-eff-min", type=int, default=100, help="G-3 门槛")
    ap.add_argument("--initial-capital", type=float, default=1_000_000.0)
    ap.add_argument("--max-position-pct", type=float, default=0.25)
    ap.add_argument("--oscillation-lt", type=float, default=20.0)
    ap.add_argument("--trending-ge", type=float, default=25.0)
    ap.add_argument("--self-check", action="store_true",
                    help="对账本脚本的块自举与 alpha.alpha_survival_lab 是否一致后退出")
    args = ap.parse_args()

    if args.self_check:
        return _self_check(args)

    logged = json.loads(Path(args.logged).read_text(encoding="utf-8"))
    bench_path = os.path.join(args.dataset, "benchmark.csv")
    bars300 = load_bars(bench_path)
    if not bars300:
        print(f"基准无数据: {bench_path}", file=sys.stderr)
        return 2
    ew = load_returns_source(args.ew_series)
    ew_ret = ew
    b300_ret = bar_returns(bars300)
    labels = labels_by_date(bars300, args.oscillation_lt, args.trending_ge)
    stock_dir = os.path.join(args.dataset, "stocks")

    window_out: List[Dict[str, Any]] = []
    all_skips: List[Dict[str, Any]] = []
    for w in logged.get("windows", []):
        curve = w.get("equity_curve") or []
        trades = w.get("trade_log") or []
        if not curve:
            window_out.append({"oos_start": w.get("oos_start"), "status": "NO_EQUITY_CURVE"})
            continue
        strat = curve_returns(curve)
        benches = {"hs300": b300_ret, "ew": ew_ret}
        common = sorted(set(strat) & set(b300_ret) & set(ew_ret))
        n_total = len(common)
        rec: Dict[str, Any] = {
            "oos_start": w.get("oos_start"),
            "aligned": w.get("aligned"),
            "n_days_used": n_total,
            "n_days_dropped_no_bench": len(set(strat) - set(common)),
            "total_return_pct": w.get("total_return_pct"),
            "daily": _daily_block(common, strat, benches, labels, n_total,
                                  args.horizon, args.reps, args.block, args.seed, args.alpha),
            "trades_by_signal_date": _trade_block(trades, labels, "signal_date"),
            "trades_by_exit_date": _trade_block(trades, labels, "exit_date"),
        }
        st = w.get("execution_stats") or {}
        rec["execution"] = {
            "rejects": st.get("rejects"),
            "opened": st.get("opened"),
            "limit_up_rate_pct": st.get("limit_up_rate_pct"),
            "n_limit_up_skips": len(st.get("limit_up_skips") or []),
            "skips_truncated": st.get("limit_up_skips_truncated"),
        }
        skips = st.get("limit_up_skips") or []
        all_skips.extend(skips)
        rec["failed_fill_sim"] = failed_fill_sim(
            skips, stock_dir, args.horizon, args.initial_capital, args.max_position_pct)
        window_out.append(rec)

    # ---- 判据（按窗口闭环：G-1..G-4 必须在**同一个**窗口内同时成立）----
    #
    # 为什么必须闭环：若 G-1/G-2 允许「任一窗口」而 G-4 另取一个窗口，就会出现
    # 「用第 5 窗满足 G-2、用第 1 窗满足 G-4」的拼接式证明 —— 那不是预注册的
    # 假设族，而是事后挑窗口。故 BH 在**每个窗口内**对 3 档 × 2 基准 = 6 个 p 值做，
    # H1 = 存在 (档位, 窗口) 使 G-1∧G-2∧G-3∧G-4 同时成立。
    gates: Dict[str, Any] = {"per_window": {}, "established": [], "G3_max_possible": {}}
    for w in window_out:
        oos = w.get("oos_start")
        if not w.get("daily"):
            continue
        hyp_p: Dict[str, Optional[float]] = {}
        for regime in REGIMES:
            d = w["daily"].get(regime) or {}
            for bname in ("hs300", "ew"):
                b = (d.get("benchmarks") or {}).get(bname) or {}
                hyp_p[f"{regime}/{bname}"] = b.get("p_one_sided")
        bh = bh_adjust(hyp_p, args.q)
        gates["G3_max_possible"][oos] = (w.get("n_days_used") or 0) // args.horizon

        per: Dict[str, Any] = {}
        for regime in REGIMES:
            d = w["daily"].get(regime) or {}
            b = (d.get("benchmarks") or {}).get("hs300") or {}
            t = w["trades_by_signal_date"].get(regime) or {}
            g1 = (b.get("mean_excess") is not None and b["mean_excess"] > 0
                  and t.get("mean_return_pct") is not None and t["mean_return_pct"] > 0)
            g2 = b.get("ci95_lower") is not None and b["ci95_lower"] > 0
            g3 = (d.get("n_eff") or 0) >= args.n_eff_min
            g4 = bool((bh.get("significant") or {}).get(f"{regime}/hs300"))
            ok = g1 and g2 and g3 and g4
            per[regime] = {
                "n_days": d.get("n_days"), "n_eff": d.get("n_eff"),
                "mean_excess_hs300": b.get("mean_excess"),
                "ci95_lower_hs300": b.get("ci95_lower"),
                "mean_trade_return_pct": t.get("mean_return_pct"),
                "p_hs300": b.get("p_one_sided"),
                "q_hs300": (bh.get("p_adjusted") or {}).get(f"{regime}/hs300"),
                "G-1": g1, "G-2": g2, "G-3": g3, "G-4": g4, "all": ok,
            }
            if ok:
                gates["established"].append({"oos_start": oos, "regime": regime})
        gates["per_window"][oos] = {"hypotheses": hyp_p, "bh": bh, "regimes": per}

    established = sorted({e["regime"] for e in gates["established"]})

    report: Dict[str, Any] = {
        "prereg": "REGIME_ATTRIBUTION_PREREG.md",
        "config": {
            "horizon": args.horizon, "block": args.block, "reps": args.reps,
            "seed": args.seed, "alpha": args.alpha, "q": args.q,
            "n_eff_min": args.n_eff_min,
            "regime_rule": {"adx_period": 14,
                            "oscillation_lt": args.oscillation_lt,
                            "trending_ge": args.trending_ge,
                            "index": "benchmark.csv(000300)"},
            "n_eff_definition": "floor(n_days / horizon)",
        },
        "inputs_sha256": {
            "logged": _sha256(args.logged),
            "benchmark": _sha256(bench_path),
            "ew_series": _sha256(args.ew_series),
        },
        "windows": window_out,
        "gates": gates,
        "failed_fill_all_windows": failed_fill_sim(
            all_skips, stock_dir, args.horizon, args.initial_capital, args.max_position_pct),
        "verdict": {
            "H": "H1" if established else "H0",
            "established": gates["established"],
            "regimes_meeting_all_gates": established,
            "note": ("H1 = 存在 (档位, 窗口) 使 G-1∧G-2∧G-3∧G-4 在该窗口内同时成立；"
                     "G-4 的 BH 在**每个窗口内**对 6 个假设（3 档 × 2 基准）做，"
                     "主判定用 hs300 口径，ew 口径同时报出。"
                     "G-3 的可行性上界见 gates.G3_max_possible。"),
        },
    }
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n",
        encoding="utf-8", newline="\n")
    print(f"已写入 {args.out}")
    print(f"判定: {report['verdict']['H']}"
          f"  达标档位: {established or '无'}")
    return 0


def _self_check(args: argparse.Namespace) -> int:
    """对账本地块自举与 `alpha.alpha_survival_lab.block_bootstrap_mean_ci`。"""
    from alpha.alpha_survival_lab import block_bootstrap_mean_ci

    series = [-0.012, 0.004, 0.009, -0.003, 0.0, 0.017, -0.008, 0.002,
              0.011, -0.005, 0.006, -0.001, 0.013, -0.007, 0.003, 0.001]
    mine = block_bootstrap_means(series, reps=args.reps, block_size=args.block, seed=args.seed)
    ci_mine = ci_from_means(mine, args.alpha)
    ci_ref = block_bootstrap_mean_ci(series, reps=args.reps, block_size=args.block,
                                     seed=args.seed, alpha=args.alpha)
    assert ci_mine is not None and ci_ref is not None
    diff = max(abs(ci_mine["lower"] - ci_ref["lower"]), abs(ci_mine["upper"] - ci_ref["upper"]))
    print(json.dumps({"mine": ci_mine,
                      "reference": {"lower": ci_ref["lower"], "upper": ci_ref["upper"]},
                      "max_abs_diff": diff,
                      "verdict": "CONSISTENT" if diff < 1e-15 else "MISMATCH"},
                     ensure_ascii=False, indent=1))
    return 0 if diff < 1e-15 else 1


if __name__ == "__main__":
    raise SystemExit(main())
