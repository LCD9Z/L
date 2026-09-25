# -*- coding: utf-8 -*-
r"""H-D2 检验：定期报告**预约披露日变更次数**是否预示负面收益。

事前登记见 ``ALPHA_HYPOTHESIS_PREREG_HD2.md`` —— **口径在跑之前已固定**，
本脚本不得事后调整因子定义、有效期或判定标准。

## 因子

``has_revision`` ∈ {0,1}：该报告期的预约披露日变更次数 ≥ 1 则为 1。
取值时点为 ``actual_disclose``（实际披露日）当日**收盘后** → T+1 开盘方可交易。

## 为什么用 ``revisions`` 而不用 ``first_scheduled``

预约变更发生在**实际披露之前**且**逐次公开**，故在 ``actual_disclose`` 之后取值时，
全部变更均已发生且已知 —— **无需版本历史即满足 PIT**。
而 ``first_scheduled`` 是"最终记录的首次预约日"，可能被事后修改（前视风险），
故本假设**不使用**该字段。

## 用法

::

    python scripts/run_disclosure_factor_study.py --dataset D:/tdx_dataset_v3 \
        --disclosures D:/tdx_dataset_v3/disclosure_dates.jsonl \
        --out reports/hd2_disclosure_revisions.json
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import statistics
import sys
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_artifacts import write_final  # noqa: E402
from factors.factor_ic_lab import (  # noqa: E402
    build_panel,
    compute_factors,
    forward_return,
    spearman,
)

# 事前登记固定的参数 —— 命令行可覆盖以做敏感性说明，但**判定以默认值为准**
DEFAULT_HORIZON = 5
DEFAULT_STEP = 5
DEFAULT_VALID_DAYS = 90
MIN_HISTORY = 60
SUBWINDOWS = [("2016-08-01", "2021-06-30"), ("2021-07-01", "2026-09-30")]
# 与既有价量因子的相关性诊断（不影响判定）
DIAGNOSTIC_FACTORS = ("ret_20", "vol_20", "log_amount_20", "max_ret_20")


def _load_revisions(path: str) -> Dict[str, List[Tuple[str, int, int]]]:
    """→ ``{code: [(actual_disclose, has_revision, revision_count), ...]}``（按日期升序）。"""
    out: Dict[str, List[Tuple[str, int, int]]] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = str(r.get("code") or "").zfill(6)
            actual = str(r.get("actual_disclose") or "")
            if not code or len(actual) != 10:
                continue
            rev = int(r.get("revisions") or 0)
            out.setdefault(code, []).append((actual, 1 if rev >= 1 else 0, min(rev, 2)))
    for v in out.values():
        v.sort()
    return out


def _lookup(records: List[Tuple[str, int, int]], day: str,
            valid_days: int) -> Optional[Tuple[int, int, str]]:
    """取 ``day`` 当日**已知**的最近一次披露（``actual_disclose <= day`` 且在有效期内）。"""
    dates = [r[0] for r in records]
    i = bisect.bisect_right(dates, day) - 1
    if i < 0:
        return None
    d, has_rev, count = records[i]
    if (date.fromisoformat(day) - date.fromisoformat(d)).days > valid_days:
        return None
    return has_rev, count, d


def _tstat(xs: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    sd = statistics.stdev(xs)
    if sd == 0:
        return None
    return statistics.mean(xs) / (sd / (len(xs) ** 0.5))


def _two_sided_p(t: Optional[float]) -> Optional[float]:
    if t is None:
        return None
    import math
    return math.erfc(abs(t) / (2 ** 0.5))


def _load_bars(dataset: str, max_stocks: int, min_rows: int,
               pool_path: str) -> Dict[str, List[Dict[str, Any]]]:
    from real_alpha_pipeline import load_certified_csv

    stock_dir = os.path.join(dataset, "stocks")
    codes: List[str] = []
    if pool_path and os.path.exists(pool_path):
        import csv as _csv
        with open(pool_path, encoding="utf-8-sig", newline="") as fh:
            codes = [r["code"].zfill(6) for r in _csv.DictReader(fh)]
    else:
        codes = sorted(f[:-4] for f in os.listdir(stock_dir)
                       if f.endswith(".csv") and f[:-4].isdigit())
    if max_stocks > 0 and len(codes) > max_stocks:
        step = len(codes) / max_stocks
        codes = [codes[int(i * step)] for i in range(max_stocks)]

    data: Dict[str, List[Dict[str, Any]]] = {}
    for c in codes:
        p = os.path.join(stock_dir, f"{c}.csv")
        m = os.path.join(stock_dir, f"{c}.metadata.json")
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        try:
            bars = load_certified_csv(p, m)
        except Exception:
            continue
        if len(bars) >= min_rows:
            data[c] = bars
    return data


def decide_verdict(mean_ic: Optional[float], t: Optional[float],
                   sub: List[Dict[str, Any]],
                   group_diff_mean: Optional[float]) -> str:
    r"""按**事前登记**判定（``ALPHA_HYPOTHESIS_PREREG_HD2.md``）。

    方向为负，故：

    * **强支持**：IC < 0 且 t ≤ −2，且两子窗口同号（均 < 0）且至少一个 t ≤ −2，
      且组差 < 0；
    * **不成立**：IC ≥ 0，**或两子窗口 IC 符号相反**；
    * **弱支持**：其余（IC < 0、子窗口同号，但 \|t\| < 2）。

    ⚠️ 该函数是 2026-09-25 一次真实缺陷的产物：原判定内联在 ``main()`` 里，
    把「子窗口符号相反」误判为「弱支持」，**与事前登记相矛盾**。
    抽成纯函数后由 ``tests/test_disclosure_factor_study.py`` 锁住。
    """
    if mean_ic is None:
        return "不成立"
    opposite = (len(sub) == 2 and sub[0]["ic_mean"] * sub[1]["ic_mean"] < 0)
    strong = (
        mean_ic < 0 and t is not None and t <= -2
        and len(sub) == 2
        and all(s["ic_mean"] < 0 for s in sub)
        and any(s["t"] is not None and s["t"] <= -2 for s in sub)
        and group_diff_mean is not None and group_diff_mean < 0
    )
    if strong:
        return "强支持"
    if mean_ic >= 0 or opposite:
        return "不成立"
    return "弱支持"


def main() -> int:
    ap = argparse.ArgumentParser(description="H-D2 披露变更次数检验（事前登记）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--disclosures", default="D:/tdx_dataset_v3/disclosure_dates.jsonl")
    ap.add_argument("--pool", default="")
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--step", type=int, default=DEFAULT_STEP)
    ap.add_argument("--valid-days", type=int, default=DEFAULT_VALID_DAYS)
    ap.add_argument("--min-cross-section", type=int, default=100)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    print("=" * 100)
    print("H-D2 检验 · 定期报告预约披露变更次数 → 未来收益（事前登记，方向为负）")
    print("=" * 100)
    print(f"口径：前瞻 {args.horizon} 日 / 每 {args.step} 日调仓 / 有效期 {args.valid_days} 自然日")
    print("取值时点：actual_disclose 当日收盘后 → T+1 开盘可交易（PIT 正确）\n")

    t0 = time.time()
    pool_path = args.pool or os.path.join(args.dataset, "pool_v2.csv")
    rev_map = _load_revisions(args.disclosures)
    print(f"披露记录：{sum(len(v) for v in rev_map.values()):,} 条 / {len(rev_map):,} 只",
          flush=True)
    data = _load_bars(args.dataset, args.max_stocks, args.min_rows, pool_path)
    print(f"行情：{len(data):,} 只（{time.time() - t0:.0f}s）", flush=True)
    if not data:
        print("无行情数据，终止。", flush=True)
        return 2

    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    panel = build_panel(data)
    rebal = panel[MIN_HISTORY::args.step]
    print(f"调仓日 {len(rebal)} 个（{rebal[0]} ~ {rebal[-1]}）\n", flush=True)

    # 逐期采集：IC 序列 + 分组差 + 诊断
    ic_series: List[Tuple[str, float]] = []
    group_diffs: List[Tuple[str, float]] = []
    sizes: List[int] = []
    n_with_rev = 0
    corr_pairs: Dict[str, List[Tuple[float, str]]] = {
        k: [] for k in DIAGNOSTIC_FACTORS}

    for i, day in enumerate(rebal, 1):
        vals: List[float] = []
        fwds: List[float] = []
        diag_vals: Dict[str, List[float]] = {k: [] for k in DIAGNOSTIC_FACTORS}
        for code, bars in data.items():
            bar_i = idx_map[code].get(day)
            if bar_i is None:
                continue
            fr = forward_return(bars, bar_i, args.horizon)
            if fr is None:
                continue
            recs = rev_map.get(code)
            if not recs:
                continue
            got = _lookup(recs, day, args.valid_days)
            if got is None:
                continue
            has_rev, _count, _d = got
            vals.append(float(has_rev))
            fwds.append(fr)
            if has_rev:
                n_with_rev += 1
            # 诊断：与既有价量因子的当期取值配对（不影响判定）
            pf = compute_factors(bars, bar_i)
            if pf is not None:
                for k in DIAGNOSTIC_FACTORS:
                    kv = pf.get(k)
                    if kv is not None:
                        diag_vals[k].append(float(kv))
        if len(vals) < args.min_cross_section:
            continue
        sizes.append(len(vals))

        ic = spearman(vals, fwds)
        if ic is not None:
            ic_series.append((day, ic))

        # 分组差：有变更组均值 − 无变更组均值
        a = [y for v, y in zip(vals, fwds, strict=True) if v == 1.0]
        b = [y for v, y in zip(vals, fwds, strict=True) if v == 0.0]
        if a and b:
            group_diffs.append((day, statistics.mean(a) - statistics.mean(b)))

        # 每期结算与既有因子的秩相关（诊断用）
        for k in DIAGNOSTIC_FACTORS:
            if len(diag_vals[k]) == len(vals) and len(vals) >= 30:
                rho = spearman(vals, diag_vals[k])
                if rho is not None:
                    corr_pairs[k].append((rho, day))

        if i % 200 == 0:
            print(f"  ... {i}/{len(rebal)}  有效 IC {len(ic_series)} 期", flush=True)

    if len(ic_series) < 10:
        print(f"有效期数不足（{len(ic_series)} < 10），无法检验。", flush=True)
        return 2

    ics = [v for _, v in ic_series]
    mean_ic = statistics.mean(ics)
    t = _tstat(ics)
    p = _two_sided_p(t)

    print("\n" + "=" * 100)
    print("全样本结果")
    print("=" * 100)
    print(f"  有效调仓期数        : {len(ics)}")
    print(f"  IC 均值             : {mean_ic:+.4f}")
    print(f"  IC 标准差           : {statistics.stdev(ics):.4f}")
    print(f"  t（H0: IC=0）       : {t:+.2f}" if t is not None else "  t: 无法计算")
    print(f"  p（双尾）           : {p:.4f}" if p is not None else "  p: —")
    print(f"  截面规模（中位/最小）: {statistics.median(sizes):.0f} / {min(sizes)}")
    print(f"  有变更的观测占比    : {n_with_rev / sum(sizes):.2%}")

    # ---- 子窗口（事前固定，不重叠）----
    print("\n" + "=" * 100)
    print("独立子窗口（事前划分，不重叠）")
    print("=" * 100)
    sub: List[Dict[str, Any]] = []
    for lo, hi in SUBWINDOWS:
        seg = [v for d, v in ic_series if lo <= d <= hi]
        if len(seg) < 10:
            print(f"  {lo} ~ {hi}: 期数不足（{len(seg)}）")
            continue
        mt = _tstat(seg)
        mp = _two_sided_p(mt)
        print(f"  {lo} ~ {hi}: n={len(seg):>4}  IC={statistics.mean(seg):+.4f}  "
              f"t={mt:+.2f}  p={mp:.4f}" if mt is not None else
              f"  {lo} ~ {hi}: n={len(seg)}  IC={statistics.mean(seg):+.4f}  t=—")
        sub.append({"start": lo, "end": hi, "n": len(seg),
                    "ic_mean": statistics.mean(seg), "t": mt, "p": mp})

    # ---- 分组差 ----
    print("\n" + "=" * 100)
    print("组合层面：有变更组 − 无变更组（前瞻收益差）")
    print("=" * 100)
    gd = [v for _, v in group_diffs]
    gmean = statistics.mean(gd) if gd else None
    gt = _tstat(gd)
    gp = _two_sided_p(gt)
    print(f"  有效期数 {len(gd)} | 差值均值 {gmean:+.4%}" if gmean is not None
          else "  无有效期")
    if gt is not None:
        print(f"  t = {gt:+.2f}  p = {gp:.4f}")

    # ---- 判定（严格按事前登记）----
    print("\n" + "=" * 100)
    print("判定（事前登记口径，方向为负）")
    print("=" * 100)
    # ⚠️ 判定必须严格按事前登记（ALPHA_HYPOTHESIS_PREREG_HD2.md）：
    #   不成立 = IC >= 0 **或两子窗口 IC 符号相反**
    #   （原登记中「弱支持」曾写「子窗口符号不一致」，与「不成立」的
    #     「符号相反」自相矛盾；2026-09-25 已按**更严**方向勘误。
    #     此处的 `opposite` 判断即落实该勘误 —— 符号相反一律判「不成立」。）
    verdict = decide_verdict(mean_ic, t, sub, gmean)
    opposite = (len(sub) == 2 and sub[0]["ic_mean"] * sub[1]["ic_mean"] < 0)
    if opposite:
        print("  ⚠️ 两个子窗口 IC 符号相反 → 按事前登记判「不成立」"
              "（不得表述为「前半段有效」）")
    print(f"  IC 均值 {mean_ic:+.4f}（假设方向为**负**）")
    print(f"  判定：**{verdict}**")
    if mean_ic > 0:
        print("  ⚠️ IC 为正 —— 与假设方向**相反**。按事前登记，结论为「不成立」，")
        print("     且**不得**改述为「反向有效」（禁止事后翻转方向）。")

    # ---- 诊断：与既有因子的相关性 ----
    print("\n" + "=" * 100)
    print("诊断（不影响判定）")
    print("=" * 100)
    print("  与既有价量因子的截面秩相关：")
    for k in DIAGNOSTIC_FACTORS:
        pair = corr_pairs[k]
        if len(pair) < 30:
            print(f"    {k:<16} 样本不足")
            continue
        rho = statistics.mean(x for x, _ in pair)
        print(f"    {k:<16} 平均 ρ = {rho:+.4f}（{len(pair)} 期）")

    print("\n  声明：")
    print("    · 本检验口径在跑之前已固定（ALPHA_HYPOTHESIS_PREREG_HD2.md），未做事后调整")
    print("    · 未做参数网格搜索；未翻转方向")
    print("    · 披露日 A 股池内覆盖 86.8%，2016~2019 年 73~83% 偏低")
    print("    · 未扣除交易成本；结论不构成投资建议")

    write_final(args.out, {
        "hypothesis": "H-D2",
        "factor": "has_revision (预约披露变更次数 >= 1)",
        "direction": "negative",
        "ic_mean": mean_ic, "ic_std": statistics.stdev(ics),
        "t": t, "p": p, "n_periods": len(ics),
        "subwindows": sub,
        "group_diff_mean": gmean, "group_diff_t": gt, "group_diff_p": gp,
        "verdict": verdict,
        "cross_section_median": statistics.median(sizes),
        "cross_section_min": min(sizes),
        "with_revision_ratio": n_with_rev / sum(sizes),
        "args": vars(args),
        "elapsed_sec": round(time.time() - t0, 1),
    })
    print(f"\n用时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
