# -*- coding: utf-8 -*-
"""H-F5 五因子组合 A/B 实验（事前登记见 `FIVE_FACTOR_PREREG.md`）。

A 臂 = 内置基线动量打分（`walk_forward.score_history`）
B 臂 = 五因子等权秩合成（ret20/vol20/amihud20/loga20/maxret20，方向事前固定）

两臂共用同一执行框架（T+1 开盘、跌停递延、停牌不建仓、现行成本、PIT 股票池、
C20 分散），**唯一变量是信号**。基准为等权全A（`benchmark_ew.csv`）。

用法::

    python run_five_factor_ab.py --dataset D:/tdx_dataset_v2 --max-stocks 400
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_WINDOWS = ["2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02", "2025-07-01"]
DIRECTIONS = {"ret20": -1, "vol20": -1, "amihud20": 1, "loga20": -1, "maxret20": -1}
VERDICT_MAP = {"SUPPORTED": "ALPHA_SUPPORTED", "NOT_SUPPORTED": "ALPHA_NOT_ESTABLISHED",
               "INCONCLUSIVE": "INCONCLUSIVE"}


def _ranks(items: List[Tuple[str, float]]) -> Dict[str, float]:
    """平均秩百分位（并列取平均秩）。"""
    vals = sorted(items, key=lambda t: t[1])
    n = len(vals)
    out: Dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[j + 1][1] == vals[i][1]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[vals[k][0]] = avg / n
        i = j + 1
    return out


def _factors(closes: List[float], amounts: List[float]) -> Dict[str, float] | None:
    n = len(closes)
    if n < 22 or closes[-22] <= 0:
        return None
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, n)]
    amt = [abs(rets[i - 1]) / amounts[i] if amounts[i] > 0 else None
           for i in range(1, n)]
    amt_vals = [v for v in amt[-20:] if v is not None]
    if not amt_vals:
        return None
    m = sum(rets[-20:]) / 20.0
    return {
        "ret20": closes[-1] / closes[-22] - 1,
        "vol20": math.sqrt(sum((r - m) ** 2 for r in rets[-20:]) / 20.0),
        "amihud20": sum(amt_vals) / len(amt_vals),
        "loga20": math.log1p(sum(amounts[-20:]) / 20.0),
        "maxret20": max(rets[-20:]),
    }


def build_beta_panel(data: Dict[str, List[dict]], days: List[str],
                     bench_ret: Dict[str, float], win: int = 60) -> Dict[str, Dict[str, float]]:
    """逐日个股 beta（对等权全A基准，滚动 win 日 OLS 斜率）。"""
    pos = {d: i for i, d in enumerate(days)}
    closes = {c: {b["date"]: float(b["close"]) for b in bars} for c, bars in data.items()}
    out: Dict[str, Dict[str, float]] = {}
    for d in days:
        k = pos[d]
        wd = days[max(0, k - win): k + 1]
        betas: Dict[str, float] = {}
        for c in data:
            cm = closes[c]
            ys: List[float] = []
            xs: List[float] = []
            for i in range(1, len(wd)):
                br = bench_ret.get(wd[i])
                c0 = cm.get(wd[i - 1])
                c1 = cm.get(wd[i])
                if br is None or not c0 or not c1:
                    continue
                ys.append(c1 / c0 - 1)
                xs.append(br)
            if len(ys) < 30:
                continue
            my = sum(ys) / len(ys)
            mx = sum(xs) / len(xs)
            sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(ys)))
            sxx = sum((xs[i] - mx) ** 2 for i in range(len(ys)))
            betas[c] = sxy / sxx if sxx > 0 else 0.0
        if betas:
            out[d] = betas
    return out


def _solve3(a: List[List[float]], b: List[float]) -> List[float] | None:
    """3×3 线性方程组（高斯消元，带部分选主元）。奇异时返回 None。"""
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    n = 3
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / m[col][col]
            for c2 in range(col, n + 1):
                m[r][c2] -= f * m[col][c2]
    return [m[i][n] / m[i][i] for i in range(n)]


def neutralize_by_day(raw: Dict[str, Dict[str, float]], composite: Dict[str, float],
                      beta: Dict[str, float], size: Dict[str, float]) -> Dict[str, float]:
    """横截面回归 composite ~ 1 + beta + size，返回残差。"""
    codes = [c for c in composite if c in beta and c in size]
    if len(codes) < 50:
        return {}
    X = [[1.0, beta[c], size[c]] for c in codes]
    y = [composite[c] for c in codes]
    # 正规方程 (X'X) b = X'y
    a = [[sum(X[k][i] * X[k][j] for k in range(len(codes))) for j in range(3)]
         for i in range(3)]
    bb = [sum(X[k][i] * y[k] for k in range(len(codes))) for i in range(3)]
    coef = _solve3(a, bb)
    if coef is None:
        return {}
    return {c: y[i] - (coef[0] + coef[1] * X[i][1] + coef[2] * X[i][2])
            for i, c in enumerate(codes)}


def build_score_panel(data, days, keep_ret20=False, keep_raw=False, subsets=None):
    """返回 (panels, ret20_rank_panel, raw_panel)。

    panels: {子集名: {day: {code: 合成分}}}；subsets 为 None 时只算 "S5_all"+DIRECTIONS 全集
    ret20_rank_panel: 逐日 ret_20 的百分位秩（用于 V1 尾部剔除）
    raw_panel: 逐日原始因子值（用于风格中性化的回归）

    性能：预先建 date→下标 映射与 date→close/amount 映射，避免在逐日循环里
    调用 `list.index()`（O(n²)，曾导致单窗口耗时 15+ 分钟）。
    """
    pos = {d: i for i, d in enumerate(days)}
    closes = {c: {b["date"]: float(b["close"]) for b in bars} for c, bars in data.items()}
    amounts = {c: {b["date"]: float(b["amount"] or 0) for b in bars} for c, bars in data.items()}
    panel: Dict[str, Dict[str, float]] = {}
    ret_rank: Dict[str, Dict[str, float]] = {}
    raws: Dict[str, Dict[str, Dict[str, float]]] = {}
    panels: Dict[str, Dict[str, Dict[str, float]]] = {
        s: {} for s in (subsets or {"S5_all": list(DIRECTIONS)})}
    for d in days:
        k = pos[d]
        win = days[max(0, k - 21): k + 1]
        raw: Dict[str, Dict[str, float]] = {}
        for c in data:
            cm = closes[c]
            am = amounts[c]
            cl = [cm[x] for x in win if x in cm]
            if len(cl) < 22:
                continue
            aml = [am[x] for x in win if x in am]
            if len(aml) < 22:
                continue
            f = _factors(cl, aml)
            if f:
                raw[c] = f
        if len(raw) < 50:
            continue
        ranks = {k2: _ranks([(c, v[k2]) for c, v in raw.items()]) for k2 in DIRECTIONS}
        # 方向化分位：正向因子取 rank_pct，反向因子取 1-rank_pct → 合成分落在
        # (0, 1]，分数越高越好（与"高分为优"的选股约定一致）。
        for sname, keys in (subsets or {"S5_all": list(DIRECTIONS)}).items():
            panels[sname][d] = {
                c: sum((ranks[k2][c] if DIRECTIONS[k2] > 0 else 1.0 - ranks[k2][c])
                       for k2 in keys) / len(keys)
                for c in raw}
        if keep_ret20:
            ret_rank[d] = ranks["ret20"]
        if keep_raw:
            raws[d] = raw
    return panels, ret_rank, raws


def _limit_for_bar(code: str, bar: Dict[str, Any]) -> float:
    """该股在给定 bar 当日的涨跌停幅度（ST 5%、主板 10%、双创 20%、北交所 30%）。"""
    c = str(code).zfill(6)
    is_st = str(bar.get("is_st", "0")) == "1"
    if c.startswith(("83", "87", "43", "92")):
        return 0.30
    if c.startswith(("300", "301", "688", "689")):
        return 0.20
    return 0.05 if is_st else 0.10


def make_jump_filter(lookback: int = 21):
    """V2 过滤：信号日回溯 lookback 根内若出现超涨跌停跳空则剔除。"""
    def f(code, hist, day):
        seg = hist[-lookback:]
        for k in range(1, len(seg)):
            p0 = float(seg[k - 1].get("close") or 0)
            p1 = float(seg[k].get("close") or 0)
            if p0 <= 0 or p1 <= 0:
                continue
            lim = _limit_for_bar(code, seg[k]) - 0.002
            if abs(p1 / p0 - 1) > lim:
                return False
        return True
    return f


def main() -> int:
    ap = argparse.ArgumentParser(description="H-F5 五因子组合 A/B 实验")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v2")
    ap.add_argument("--max-stocks", type=int, default=400)
    ap.add_argument("--min-rows", type=int, default=504)
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--position-pct", type=float, default=0.05)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--windows", default=",".join(DEFAULT_WINDOWS))
    ap.add_argument("--benchmark", default="", help="默认 <dataset>/benchmark_ew.csv")
    ap.add_argument("--survivorship-evidence", default="")
    ap.add_argument("--exclude-ret20-top", type=float, default=0.0,
                    help=">0 时改为 C20×V1 实验：在 A 臂上剔除当日 ret_20 最高分位"
                         "（如 0.20），与 A 臂做苹果对苹果对照")
    ap.add_argument("--neutralize", action="store_true",
                    help="风格中性化实验：composite ~ 1 + beta(60d) + size(log成交额) 取残差")
    ap.add_argument("--regime-switch", action="store_true",
                    help="按市场状态切换：明确→动量侧(score_history)，震荡/萌芽→反转侧"
                         "（先验映射，见 STYLE_REGIME_PREREG.md）")
    ap.add_argument("--style-switch", action="store_true",
                    help="风格维度状态切换（含反向证伪臂），见 STYLE_SWITCH_PREREG.md")
    ap.add_argument("--max-participation", type=float, default=0.0,
                    help="容量约束：单笔买入名义 ≤ 信号日成交额 × 比例（H-TC 的 T2）")
    ap.add_argument("--impact-model", action="store_true",
                    help="用 sqrt 冲击成本（k·σ·√(Q/V)）替换阶梯滑点，见 IMPACT_COST_PREREG.md")
    ap.add_argument("--compare-factors", default="",
                    help="H-F4：附加一个因子子集臂，如 'ret20,vol20,loga20,maxret20'"
                         "（同时输出 S5_all 与子集两臂），见 FACTOR_SUBSET_PREREG.md")
    ap.add_argument("--exclude-jump", action="store_true",
                    help="H-V2：在 V1 基础上再剔除信号日前 21 根内含超涨跌停跳空的候选")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    ds = args.dataset
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]
    bench_path = args.benchmark or os.path.join(ds, "benchmark_ew.csv")
    t0 = time.time()

    from real_alpha_pipeline import load_certified_csv, _benchmark_returns, _curve_returns
    from portfolio_backtest import portfolio_backtest
    from alpha.alpha_survival_lab import analyse_alpha
    from historical_universe import point_in_time_universe
    from release_gate import (build_survivorship_audit, gate_alpha_claim,
                              load_survivorship_evidence)

    stock_dir = os.path.join(ds, "stocks")
    codes = sorted(f[:-4] for f in os.listdir(stock_dir) if f.endswith(".csv"))
    if args.max_stocks > 0 and len(codes) > args.max_stocks:
        step = len(codes) / args.max_stocks
        codes = [codes[int(i * step)] for i in range(args.max_stocks)]
    data: Dict[str, List[dict]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if os.path.exists(p) and os.path.exists(m):
            bars = load_certified_csv(p, m)
            if len(bars) >= args.min_rows:
                data[c] = bars
    print(f"[1/3] 载入 {len(data)} 只，共 {sum(len(v) for v in data.values()):,} 行", flush=True)

    with open(os.path.join(ds, "pit_universe.json"), encoding="utf-8") as f:
        universe = json.load(f)["snapshots"]
    bench = load_certified_csv(bench_path, bench_path + ".metadata.json")
    audit = build_survivorship_audit(
        load_survivorship_evidence(args.survivorship_evidence or None),
        pit_universe_verified=True)

    rows: List[Dict[str, Any]] = []
    for w in windows:
        _t = time.time()
        days_all = sorted({b["date"] for bars in data.values() for b in bars})
        days = [d for d in days_all if d >= w]
        allowed = {d: set(point_in_time_universe(universe, d)) for d in days}
        restricted: Dict[str, List[dict]] = {}
        for c, bars in data.items():
            kept, ever = [], False
            for b in bars:
                d = b["date"]
                if d >= w and c not in allowed.get(d, set()):
                    continue
                kept.append(b)
                if d >= w:
                    ever = True
            if ever:
                restricted[c] = kept
        bench_w = [b for b in bench if b["date"] >= w]
        b_ret = _benchmark_returns(bench_w)

        # 风格切换需要预热：状态变量 S_t 用过去 20 日风格收益，故面板向前多算 60 天
        warmup = 60 if args.style_switch else 0
        i0 = max(0, days_all.index(w) - warmup)
        panel_days = days_all[i0:]
        subset_specs = {"S5_all": list(DIRECTIONS)}
        if args.compare_factors:
            keys = [k.strip() for k in args.compare_factors.split(",") if k.strip()]
            for k in keys:
                if k not in DIRECTIONS:
                    raise SystemExit(f"未知因子 {k}，可选 {list(DIRECTIONS)}")
            subset_specs["S_subset"] = keys
        panels, ret_rank, raws = build_score_panel(
            restricted, panel_days, keep_ret20=True,
            keep_raw=bool(args.neutralize), subsets=subset_specs)
        panel = panels["S5_all"]
        print(f"      因子面板 {len(panel)} 天"
              + (f"（另含子集 {subset_specs['S_subset']}）" if args.compare_factors else ""),
              flush=True)

        # --- 风格中性化：composite ~ 1 + beta(60d) + size(log 成交额) 取残差 ---
        if args.neutralize:
            bench_ret_map: Dict[str, float] = {}
            for i in range(1, len(bench_w)):
                p0 = float(bench_w[i - 1]["close"])
                p1 = float(bench_w[i]["close"])
                if p0 > 0:
                    bench_ret_map[bench_w[i]["date"]] = p1 / p0 - 1
            beta_panel = build_beta_panel(restricted, days, bench_ret_map)
            neu_panel: Dict[str, Dict[str, float]] = {}
            for d, comp in panel.items():
                raw_d = raws.get(d, {})
                size_d = {c: v["loga20"] for c, v in raw_d.items()}
                res = neutralize_by_day(raw_d, comp, beta_panel.get(d, {}), size_d)
                if res:
                    neu_panel[d] = {c: _ranks(list(res.items()))[c] for c in res}
            print(f"      中性化面板 {len(neu_panel)} 天（beta 覆盖 {len(beta_panel)} 天）",
                  flush=True)

        # --- 风格维度状态：S_t = 近20日(反转TopK收益 − 动量TopK收益)，阈值固定 0 ---
        style_state: Dict[str, float] = {}
        if args.style_switch:
            closes_map = {c: {b["date"]: float(b["close"]) for b in bars}
                          for c, bars in restricted.items()}
            k_top = max(20, int(0.10 * len(restricted)))
            rev_ret: Dict[str, float] = {}
            mom_ret: Dict[str, float] = {}
            for j, d in enumerate(panel_days[:-1]):
                nd = panel_days[j + 1]
                comp = panel.get(d)
                rr = ret_rank.get(d)
                if not comp or not rr:
                    continue

                def _fwd(codes, _d=d, _nd=nd):
                    vals = []
                    for c in codes:
                        cm = closes_map.get(c, {})
                        a = cm.get(_d)
                        b = cm.get(_nd)
                        if a and b:
                            vals.append(b / a - 1)
                    return sum(vals) / len(vals) if vals else 0.0

                rev_ret[d] = _fwd(sorted(comp, key=lambda c: -comp[c])[:k_top])
                mom_ret[d] = _fwd(sorted(rr, key=lambda c: -rr[c])[:k_top])
            for j, d in enumerate(panel_days):
                seg = panel_days[max(0, j - 20): j]      # 仅用 t 之前的信息
                if len(seg) < 10:
                    continue
                style_state[d] = sum(rev_ret.get(x, 0.0) - mom_ret.get(x, 0.0)
                                     for x in seg)
            n_rev = sum(1 for d in days if style_state.get(d, 0.0) > 0)
            print(f"      风格状态：反转占优 {n_rev}/{len(days)} 天（K={k_top}）",
                  flush=True)

        # --- 按市场状态切换：明确→动量侧，萌芽/震荡→反转侧（先验映射）---
        regime_by_day: Dict[str, str] = {}
        if args.regime_switch:
            from regime.adx_router import RegimeRouter
            router = RegimeRouter({"enabled": True}, index_bars=bench_w)
            for d in days:
                regime_by_day[d] = router.decide(d).regime
            from collections import Counter
            print(f"      状态分布 {dict(Counter(regime_by_day.values()))}", flush=True)

        def score_b(code, hist, day):
            v = panel.get(day, {}).get(code)
            if v is None:
                return {"score": 0.0, "risk": 9.0}
            return {"score": float(v) * 100.0, "risk": 5.0}

        rec: Dict[str, Any] = {"window": w, "assets": len(restricted)}
        # B 臂不设分数阈值（复合分已是"越高越好"的分位合成，纯按 top_n 取），
        # A 臂保持 score ≥ 70 的既有信号门槛 —— 差异即"信号本身"，见 PREREG。
        arms: List[Tuple[str, Dict[str, Any]]] = []
        if args.neutralize:
            def score_neu(code, hist, day, _np=neu_panel):
                v = _np.get(day, {}).get(code)
                if v is None:
                    return {"score": 0.0, "risk": 9.0}
                return {"score": float(v) * 100.0, "risk": 5.0}

            arms.append(("A_baseline", {"threshold": 70}))
            arms.append(("N_neutral_reversal", {"threshold": 0.0, "score_func": score_neu}))
        elif args.regime_switch:
            from walk_forward import score_history

            def score_switch(code, hist, day, _p=panel, _rg=regime_by_day):
                if _rg.get(day) == "明确":
                    return score_history(hist)          # 动量侧（趋势市）
                v = _p.get(day, {}).get(code)           # 反转侧（萌芽/震荡）
                if v is None:
                    return {"score": 0.0, "risk": 9.0}
                return {"score": float(v) * 100.0, "risk": 5.0}

            arms.append(("RS_regime_switch", {"threshold": 0.0, "score_func": score_switch}))
        elif args.style_switch:
            def _ss(code, hist, day, inv, _p=panel, _rr=ret_rank, _st=style_state):
                s = _st.get(day)
                use_rev = (s is not None and s > 0)
                if inv:
                    use_rev = not use_rev
                v = (_p.get(day, {}) if use_rev else _rr.get(day, {})).get(code)
                if v is None:
                    return {"score": 0.0, "risk": 9.0}
                return {"score": float(v) * 100.0, "risk": 5.0}

            arms.append(("SS_style_switch", {"threshold": 0.0,
                                             "score_func": lambda c, h, d: _ss(c, h, d, False)}))
            arms.append(("SS_inv_falsify", {"threshold": 0.0,
                                            "score_func": lambda c, h, d: _ss(c, h, d, True)}))
        elif args.compare_factors:
            def _mk(pan):
                def sc(code, hist, day, _p=pan):
                    v = _p.get(day, {}).get(code)
                    if v is None:
                        return {"score": 0.0, "risk": 9.0}
                    return {"score": float(v) * 100.0, "risk": 5.0}
                return sc

            arms.append(("A_baseline", {"threshold": 70}))
            arms.append(("B_fivefactor", {"threshold": 0.0,
                                          "score_func": _mk(panels["S5_all"])}))
            arms.append(("B_subset", {"threshold": 0.0,
                                      "score_func": _mk(panels["S_subset"])}))
        elif args.exclude_ret20_top > 0:
            cut = 1.0 - args.exclude_ret20_top

            def flt(code, hist, day, _rr=ret_rank, _cut=cut):
                v = _rr.get(day, {}).get(code)
                return True if v is None else v <= _cut

            arms.append(("A_baseline", {"threshold": 70}))
            arms.append(("A_plus_V1", {"threshold": 70, "candidate_filter": flt}))
            if args.exclude_jump:
                def flt2(code, hist, day, _f=flt):
                    return _f(code, hist, day) and make_jump_filter()(code, hist, day)
                arms.append(("A_plus_V1_V2", {"threshold": 70,
                                              "candidate_filter": flt2}))
        else:
            arms.append(("A_baseline", {"threshold": 70}))
            arms.append(("B_fivefactor", {"threshold": 0.0, "score_func": score_b}))
        for arm, kwargs in arms:
            res = portfolio_backtest(restricted, top_n=args.top_n,
                                     max_position_pct=args.position_pct,
                                     horizon=args.horizon, start_signal_date=w,
                                     universe_snapshot_map=universe,
                                     max_participation=args.max_participation,
                                     impact_model=args.impact_model,
                                     **kwargs)
            s_ret = _curve_returns(res.get("equity_curve", []))
            common = sorted(set(s_ret) & set(b_ret))
            entry: Dict[str, Any] = {
                "total_return_pct": res.get("total_return_pct"),
                "max_drawdown_pct": res.get("max_drawdown_pct"),
                "trades": res.get("trades"), "win_rate_pct": res.get("win_rate_pct"),
                "capacity_capped_buys": res.get("capacity_capped_buys", 0),
            }
            if len(common) >= 252:
                a = analyse_alpha({d: s_ret[d] for d in common},
                                  {d: b_ret[d] for d in common}, min_periods=252)
                gated = gate_alpha_claim(
                    VERDICT_MAP.get(a.get("verdict"), a.get("verdict")), audit)
                entry.update({"annualized_excess": a.get("annualized_excess_estimate"),
                              "t_stat": a.get("t_stat_normal_approx"),
                              "verdict": gated["verdict"]})
            rec[arm] = entry
        arm_names = [a for a, _ in arms]
        base_arm, test_arm = arm_names[0], arm_names[-1]
        if rec[base_arm].get("annualized_excess") is not None \
                and rec[test_arm].get("annualized_excess") is not None:
            rec["delta_excess_pp"] = round(
                (rec[test_arm]["annualized_excess"]
                 - rec[base_arm]["annualized_excess"]) * 100, 2)
        rows.append(rec)
        print(f"  {w}  {base_arm}: {rec[base_arm].get('total_return_pct')}% "
              f"(超额 {rec[base_arm].get('annualized_excess', 0):+.2%})  |  "
              f"{test_arm}: {rec[test_arm].get('total_return_pct')}% "
              f"(超额 {rec[test_arm].get('annualized_excess', 0):+.2%})  |  "
              f"Δ {rec.get('delta_excess_pp', 0):+.2f}pp  ({time.time()-_t:.0f}s)",
              flush=True)

    print("\n汇总（按 FIVE_FACTOR_PREREG 判定标准）")
    deltas = [r["delta_excess_pp"] for r in rows if r.get("delta_excess_pp") is not None]
    if deltas:
        n_pos = sum(1 for d in deltas if d > 0)
        med = sorted(deltas)[len(deltas) // 2]
        print(f"  后臂优于前臂的窗口: {n_pos} / {len(deltas)}，Δ超额中位 {med:+.2f}pp")
    out = {"windows": rows, "args": vars(args),
           "prereg": "FIVE_FACTOR_PREREG.md", "runtime_sec": round(time.time() - t0, 1)}
    text = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"  已写入: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
