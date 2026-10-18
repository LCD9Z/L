# -*- coding: utf-8 -*-
r"""基本面因子横截面 IC 检验（PIT 财务数据）。

## 这是项目第一条**非价量**数据维度

此前全部因子结论都建立在纯价量数据上（`factors/factor_registry.py` 中 10 个
基本面/事件因子长期标记 `missing_source`）。本脚本检验其中 7 个可直接计算的因子。

## 检验设计（与 `factors/factor_ic_lab.py` 保持同一口径）

* 调仓频率每 5 个交易日、前瞻 5 个交易日（与调仓周期一致 → **无重叠**，t 检验有效）
* 横截面 **Spearman 秩 IC**（抗离群，且与秩口径一致）
* 因子值全部来自 `pit.pit_fundamentals` —— **只使用该日确实已公告的财务数据**
* 估值因子（`pb` / `pe_ttm`）用**当日收盘价**计算，不引入未来信息

## 先验方向（先有经济逻辑，再检验）

| 因子 | 先验 | 经济逻辑 |
|------|:---:|---------|
| `pb` | −1 | 价值/账面市值比（Fama-French HML）：低 PB 溢价 |
| `pe_ttm` | −1 | 价值/盈利收益率：低 PE 溢价 |
| `roe` | +1 | 质量：高 ROE 溢价 |
| `net_profit_growth` | +1 | 成长：高净利润增速溢价 |
| `revenue_growth` | +1 | 成长：高营收增速溢价 |
| `gross_margin` | +1 | 质量/定价权：高毛利率溢价 |
| `ocf_per_share` | +1 | 现金质量：高每股经营现金流溢价 |

**先验方向一经写定即不因结果调整**（否则就是用结果选参数）。

## 必须随结论声明的口径限制

1. `roe` 是**年初至今累计**口径，不是 TTM；同一日不同个股可能落在不同报告期。
2. 财务数据的**可用日**优先取**巨潮资讯真实披露日**（A 股池内覆盖 **86.8%**）；
   缺失时退回法定披露截止日（12.8%）。见 `pit/pit_fundamentals` 模块文档。
   注意：东财业绩报表混入新三板公司（占全量记录 38.7%），
   **统计覆盖率前必须按 `pool_v2.csv` 过滤到 A 股池**，否则分母被灌大。
3. 本脚本对**多因子同时检验**，故一并输出 BH-FDR 与 Bonferroni 校正结果 ——
   7 个因子同时检验时，"至少一个假阳性"的概率是 30.2%。

用法::

    python scripts/run_fundamental_factor_study.py --dataset D:/tdx_dataset_v3 \
        --fundamentals D:/tdx_dataset_v3/fundamentals.jsonl --max-stocks 1200
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.factor_ic_lab import (  # noqa: E402
    DEFAULT_HORIZON,
    DEFAULT_STEP,
    MIN_HISTORY,
    _t_pvalue,
    _winsorize,
    build_panel,
    compute_factors,
    forward_return,
    orthogonalize_panel,
    spearman,
)
from pit.pit_fundamentals import (  # noqa: E402
    PitFundamentals,
    audit_announce_dates,
    load_disclosures,
    load_records,
    resolve_availability,
)
from fetch.fingerprint import fingerprint_datasets  # noqa: E402
from validation.multiple_testing import (  # noqa: E402
    benjamini_hochberg,
    bonferroni,
    deflated_family,
)

# 因子 → (先验方向, 中文说明)
HYPOTHESES: Dict[str, Tuple[int, str]] = {
    "pb": (-1, "价值/账面市值比（低 PB 溢价）"),
    "pe_ttm": (-1, "价值/盈利收益率（低 PE 溢价）"),
    "roe": (+1, "质量（高 ROE 溢价，YTD 累计口径）"),
    "net_profit_growth": (+1, "成长（高净利润同比增速溢价）"),
    "revenue_growth": (+1, "成长（高营收同比增速溢价）"),
    "gross_margin": (+1, "质量/定价权（高毛利率溢价）"),
    "ocf_per_share": (+1, "现金质量（高每股经营现金流溢价）"),
}
NEEDS_PRICE = ("pb", "pe_ttm")


def load_universe(dataset: Path, codes: List[str]) -> Dict[str, List[str]]:
    raw = json.loads((dataset / "pit_universe.json").read_text(encoding="utf-8"))
    keep = set(codes)
    return {d: [c for c in members if c in keep]
            for d, members in raw["snapshots"].items()}


def quintile_spread(factor_vals: List[float], fwd: List[float],
                    n_groups: int = 5) -> Optional[List[float]]:
    """分位组平均前瞻收益（缩尾后），返回每组均值。"""
    pairs = sorted(zip(factor_vals, fwd, strict=True), key=lambda t: t[0])
    rets = _winsorize([p[1] for p in pairs])
    n = len(pairs)
    out = []
    for g in range(n_groups):
        lo, hi = g * n // n_groups, (g + 1) * n // n_groups
        if hi > lo:
            out.append(sum(rets[lo:hi]) / (hi - lo))
    return out if len(out) == n_groups else None


def main() -> int:
    ap = argparse.ArgumentParser(description="基本面因子横截面 IC 检验（PIT）")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v3")
    ap.add_argument("--fundamentals", default="D:/tdx_dataset_v3/fundamentals.jsonl")
    ap.add_argument("--disclosures", default="D:/tdx_dataset_v3/disclosure_dates.jsonl",
                    help="巨潮资讯真实披露日 JSONL（PIT 的首选依据）。"
                         "不存在时自动退回公告日/法定截止日口径。")
    ap.add_argument("--max-stocks", type=int, default=1200)
    ap.add_argument("--min-rows-asset", type=int, default=504)
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--step", type=int, default=DEFAULT_STEP)
    ap.add_argument("--min-cross-section", type=int, default=50)
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--control", default="log_amount_20",
                    help="价量控制变量（默认 log_amount_20 规模/流动性）。给定后额外输出"
                         "**控制该变量后的残差 IC** —— 用于判断基本面因子的溢价是否"
                         "独立于市值暴露。传空串则跳过。")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    t0 = time.time()

    # ---- 股票池（与 rolling eval 同一预过滤口径）----
    universe_raw = json.loads((dataset / "pit_universe.json").read_text(encoding="utf-8"))
    in_universe = set()
    for members in universe_raw["snapshots"].values():
        in_universe.update(members)
    stock_dir = dataset / "stocks"
    codes = sorted(c for c in in_universe
                   if (stock_dir / f"{c}.csv").exists()
                   and (stock_dir / f"{c}.metadata.json").exists())
    kept = []
    for c in codes:
        try:
            rows = int(json.loads((stock_dir / f"{c}.metadata.json")
                                  .read_text(encoding="utf-8")).get("rows", 0))
        except (OSError, ValueError):
            rows = 0
        if rows >= args.min_rows_asset:
            kept.append(c)
    if args.max_stocks > 0 and len(kept) > args.max_stocks:
        step = len(kept) / args.max_stocks
        kept = [kept[int(i * step)] for i in range(args.max_stocks)]
    print(f"股票池: {len(kept):,} 只（自 {len(codes):,} 只中按行数 >= "
          f"{args.min_rows_asset} 预过滤后等距抽样）", flush=True)

    # ---- 数据加载（认证校验）----
    from real_alpha_pipeline import load_certified_csv
    data: Dict[str, List[dict]] = {}
    for i, code in enumerate(kept):
        try:
            data[code] = load_certified_csv(stock_dir / f"{code}.csv",
                                            stock_dir / f"{code}.metadata.json")
        except ValueError as exc:
            print(f"  !! {code} 认证校验失败，跳过：{exc}", flush=True)
        if (i + 1) % 300 == 0:
            print(f"  已加载 {i + 1}/{len(kept)}", flush=True)
    print(f"已加载 {len(data):,} 只", flush=True)

    # ---- PIT 财务 ----
    records = load_records(args.fundamentals)
    disc = load_disclosures(args.disclosures)
    # 数据集指纹（DATA_CHANNEL_PREREG 组件 A）：一次 md5 + 行数 + 字节数。
    # 披露日表是可选输入（缺失时 PIT 自动退口径），故 required=False ——
    # 缺失记 {"missing": True}，不补造空指纹。
    ds_fp = fingerprint_datasets(
        {"fundamentals": args.fundamentals, "disclosure_dates": args.disclosures},
        required={"fundamentals": True, "disclosure_dates": False})
    _fp_desc = "；".join(
        (f"{k} md5={v['md5'][:12]}…（{v['lines']:,} 行 / {v['bytes']:,} B）"
         if not v.get("missing") else f"{k} 缺失（无指纹）")
        for k, v in ds_fp.items())
    print(f"数据集指纹：{_fp_desc}", flush=True)
    pf = PitFundamentals(records, disc)
    print(f"财务记录 {len(pf):,} 条 / {len(pf.codes()):,} 只"
          f"（真实披露日 {len(disc):,} 条）", flush=True)
    # ⚠️ 统计口径必须限定在**数据集声明的 A 股池**内。
    # 东财业绩报表混入了**新三板**公司（400xxx/430xxx/831xxx/832xxx/839xxx 等代码段，
    # 实测占全部记录的 38.7%）。这些记录永远不会被查询（池是 A 股），
    # 但会把覆盖率分母灌大、把"真实披露日占比"严重稀释。
    pool_codes = set()
    pool_path = dataset / "pool_v2.csv"
    if not pool_path.exists():
        pool_path = dataset / "pool.csv"
    if pool_path.exists():
        import csv as _csv
        with pool_path.open(encoding="utf-8-sig", newline="") as fh:
            pool_codes = {r["code"].zfill(6) for r in _csv.DictReader(fh)}
    pool_records = [r for r in records if str(r.get("code", "")).zfill(6) in pool_codes] \
        if pool_codes else records
    basis_counts: Dict[str, int] = {}
    for r in pool_records:
        _, b = resolve_availability(r, disc)
        basis_counts[b] = basis_counts.get(b, 0) + 1
    non_pool = len(records) - len(pool_records)
    print(f"记录范围：池内 {len(pool_records):,} / 全量 {len(records):,}"
          f"（非 A 股 {non_pool:,}，占 {non_pool / max(1, len(records)):.1%}，不参与统计）",
          flush=True)
    print(f"池内可用日依据分布：{basis_counts}", flush=True)
    diag = audit_announce_dates(pool_records, disc)

    # ---- 逐调仓日采集 ----
    idx_map = {c: {str(b["date"]): k for k, b in enumerate(bars)}
               for c, bars in data.items()}
    panel = build_panel(data)
    if args.start:
        panel = [d for d in panel if d >= args.start]
    if args.end:
        panel = [d for d in panel if d <= args.end]
    rebal = panel[MIN_HISTORY::args.step]
    print(f"调仓日 {len(rebal)} 个（{rebal[0]} ~ {rebal[-1]}）", flush=True)

    # 统计**实际被使用的因子值**的可用日依据 —— 这才是研究相关的覆盖率口径。
    # （记录级覆盖率会被"当时尚未上市的公司"拉低：它们有财务记录但无行情，
    #   永远不会被查询。实测缺口里大量是这类。）
    used_basis: Dict[str, int] = {}
    series: Dict[str, List[float]] = {k: [] for k in HYPOTHESES}
    groups: Dict[str, List[List[float]]] = {k: [] for k in HYPOTHESES}
    # 控制变量分析用：每期保留 (控制值, 因子值, 前瞻收益) 三元组
    panel_records: List[Dict[str, Any]] = []
    sizes: List[int] = []
    covered = 0
    seen = 0
    control = args.control.strip()

    for day in rebal:
        # ⚠️ 每个因子的**可用股票集合不同**（如 pe_ttm 需 EPS>0），
        # 因此必须为每个因子单独维护配对的 (因子值, 前瞻收益) ——
        # 共用一个 fwd 列表会导致错配，且不报错（B905 的 strict= 正是为此）。
        vals: Dict[str, List[float]] = {k: [] for k in HYPOTHESES}
        fwd_of: Dict[str, List[float]] = {k: [] for k in HYPOTHESES}
        ctrl_of: Dict[str, List[float]] = {k: [] for k in HYPOTHESES}
        n_fwd = 0
        for code, bars in data.items():
            bar_i = idx_map[code].get(day)
            if bar_i is None:
                continue
            seen += 1
            fr = forward_return(bars, bar_i, args.horizon)
            if fr is None:
                continue
            price = float(bars[bar_i]["close"])
            f = pf.factors_as_of(code, day, price=price)
            if not f:
                continue
            covered += 1
            n_fwd += 1
            _b = str(f.get("availability_basis") or "unknown")
            used_basis[_b] = used_basis.get(_b, 0) + 1
            ctrl_val = None
            if control:
                pf_fac = compute_factors(bars, bar_i)
                if pf_fac is not None:
                    ctrl_val = pf_fac.get(control)
            for k in HYPOTHESES:
                if k in f:
                    vals[k].append(float(f[k]))
                    fwd_of[k].append(fr)
                    if ctrl_val is not None:
                        ctrl_of[k].append(float(ctrl_val))
        if n_fwd < args.min_cross_section:
            continue
        sizes.append(n_fwd)
        for k in HYPOTHESES:
            v, y = vals[k], fwd_of[k]
            if len(v) < args.min_cross_section:
                continue
            ic = spearman(v, y)
            if ic is not None:
                series[k].append(ic)
            g = quintile_spread(v, y)
            if g:
                groups[k].append(g)
        if control:
            panel_records.append({"date": day, "vals": vals, "fwd": fwd_of, "ctrl": ctrl_of})

    if not sizes:
        print("无有效调仓日，无法检验。", flush=True)
        return 2

    # ---- 汇总 ----
    def summarize(k: str) -> Dict[str, Any]:
        ics = series[k]
        if len(ics) < 10:
            return {"error": "insufficient_periods", "n_periods": len(ics)}
        m = statistics.mean(ics)
        sd = statistics.pstdev(ics)
        icir = (m / sd) if sd > 0 else 0.0
        t = icir * math.sqrt(len(ics))
        prior, label = HYPOTHESES[k]
        out: Dict[str, Any] = {
            "ic_mean": m, "ic_std": sd, "icir": icir, "t": t,
            "p": _t_pvalue(t, len(ics) - 1), "n_periods": len(ics),
            "positive_rate": sum(1 for x in ics if x > 0) / len(ics),
            "prior_sign": prior, "label": label,
        }
        gm = groups[k]
        if gm:
            means = [statistics.mean(g) for g in zip(*gm, strict=True)]
            out["quintile_mean_returns"] = means
            out["long_short_pct"] = (means[-1] - means[0]) * 100
        return out

    results = {k: summarize(k) for k in HYPOTHESES}
    pvals = [results[k].get("p") for k in HYPOTHESES]
    bh = benjamini_hochberg(pvals, 0.05)
    bonf = bonferroni(pvals, 0.05)
    names = list(HYPOTHESES)
    for idx, k in enumerate(names):
        r = results[k]
        res = bh["results"][idx]
        if res:
            r["p_adjusted_bh"] = res["p_adjusted"]
            r["rejected_bh"] = res["rejected"]
        bres = bonf["results"][idx]
        if bres:
            r["p_adjusted_bonferroni"] = bres["p_adjusted"]
            r["rejected_bonferroni"] = bres["rejected"]

    # ---- 夏普比口径的紧缩：一族试验一起校正「挑最优」（DSR/PSR/MinTRL）----
    # 口径见 DSR_IC_FAMILY_PREREG.md §3.1；此处只做纯加法，不动上面任何字段。
    deflated = deflated_family({k: series[k] for k in HYPOTHESES}, alpha=0.05)
    for k in HYPOTHESES:
        d = deflated["trials"].get(k)
        if d:
            results[k]["dsr"] = d["dsr"]
            results[k]["psr"] = d["psr"]
            results[k]["min_trl_sufficient"] = d["min_trl_sufficient"]
            results[k]["min_trl_required"] = d["min_trl_required"]
    if not deflated.get("selection_bias_corrected"):
        print("\n⚠️ 未校正选择偏差（n_trials 或 sr_variance 不足）"
              "⇒ dsr 退化为 psr，不得读作「已扣选择偏差」", flush=True)

    # ---- 控制变量：残差 IC（判断基本面溢价是否独立于市值暴露）----
    controlled: Dict[str, Any] = {}
    if control and panel_records:
        for k in HYPOTHESES:
            periods = []
            for rec in panel_records:
                v, y, c = rec["vals"][k], rec["fwd"][k], rec["ctrl"][k]
                n = min(len(v), len(y), len(c))
                if n < args.min_cross_section:
                    continue
                periods.append({
                    "date": rec["date"],
                    "factors": {control: c[:n], k: v[:n]},
                    "forward": y[:n],
                })
            if len(periods) < 10:
                continue
            # 注意：变量名不能叫 panel —— 上面 `panel` 已是交易日序列（List[str]）
            orth_input = {"periods": periods, "panel_len": len(periods),
                          "factor_names": [control, k], "horizon": args.horizon,
                          "step": args.step}
            # 顺序残差化：控制变量在前（不被改动），待控因子在后（对其取残差）
            orth = orthogonalize_panel(orth_input, method="sequential",
                                       factors=[control, k], order=[control, k],
                                       min_cross_section=args.min_cross_section)
            ics = []
            for p in orth["periods"]:
                if not p.get("orthogonalized"):
                    continue
                # 变量名不能叫 r —— 上面的 BH 循环里 r 已绑定为 results[k]（dict）
                ic_r = spearman(p["factors"][k], p["forward"])
                if ic_r is not None:
                    ics.append(ic_r)
            if len(ics) < 10:
                continue
            m = statistics.mean(ics)
            sd = statistics.pstdev(ics)
            t = (m / sd * math.sqrt(len(ics))) if sd > 0 else 0.0
            controlled[k] = {
                "ic_mean": m, "t": t, "p": _t_pvalue(t, len(ics) - 1),
                "n_periods": len(ics), "control": control,
                "n_periods_orthogonalized": orth["n_periods_orthogonalized"],
            }

    # ---- 打印 ----
    print("\n" + "=" * 96)
    print("基本面因子横截面 IC 检验（PIT 财务数据）")
    print("=" * 96)
    print(f"有效调仓日 {len(sizes)} 个，平均截面 {statistics.mean(sizes):.0f} 只")
    tot_used = sum(used_basis.values()) or 1
    print(f"\n**实际使用**的因子值可用日依据（研究相关口径，共 {tot_used:,} 个）：")
    for b, n in sorted(used_basis.items(), key=lambda kv: -kv[1]):
        print(f"    {b:<20}{n:>10,}  {n / tot_used:>6.1%}")
    print(f"财务覆盖：{covered:,} / {seen:,} = "
          f"{(covered / seen if seen else 0):.1%}（有行情的个股-日中有财务数据者）")
    print(f"\n{'因子':<20}{'IC均值':>10}{'t':>8}{'p':>9}{'p_BH':>9}"
          f"{'ICIR':>8}{'多空%':>9}{'DSR':>8}  判定")
    for k in names:
        r = results[k]
        if "ic_mean" not in r:
            print(f"{k:<20}{'—':>10}{'—':>8}{'—':>9}{'—':>9}{'—':>8}{'—':>9}{'—':>8}  "
                  f"{r.get('error')}")
            continue
        verdict = "BH 显著" if r.get("rejected_bh") else "校正后不显著"
        if r.get("rejected_bonferroni"):
            verdict = "两者皆显著"
        ls = r.get("long_short_pct")
        dsr = r.get("dsr")
        print(f"{k:<20}{r['ic_mean']:>+10.4f}{r['t']:>8.2f}{r['p']:>9.4f}"
              f"{r.get('p_adjusted_bh', float('nan')):>9.4f}{r['icir']:>8.3f}"
              f"{(f'{ls:+.3f}' if ls is not None else '—'):>9}"
              f"{(f'{dsr:.4f}' if isinstance(dsr, float) else '—'):>8}  {verdict}")

    print(f"\n多重检验：m = {len(names)}，BH 拒绝 {bh['k']} 个，"
          f"Bonferroni 拒绝 {bonf['k']} 个")
    print(f"  未校正时族错误率 = {1 - 0.95 ** len(names):.1%}")
    if deflated.get("selection_bias_corrected"):
        print(f"  夏普比口径：n_trials = {deflated['n_trials']}，"
              f"sr_variance = {deflated['sr_variance']:.6f}，"
              f"E[max SR] = {deflated['expected_max_sr']:.4f}"
              f"（DSR < 0.95 即「扣掉挑最优后不构成证据」）")
        for k in names:
            d = deflated["trials"].get(k)
            if d and isinstance(d.get("dsr"), float):
                print(f"    {k:<20} DSR = {d['dsr']:.4f}"
                      f"   MinTRL = {d['min_trl_required'] if d['min_trl_required'] else '—'}"
                      f"（{'够' if d['min_trl_sufficient'] else '不够'}）")

    if controlled:
        # 残差 IC 也必须校正：本步把检验次数从 7 增至 14（原始 + 控制），
        # 未校正族错误率 30.2% → 51.2%。两个口径都报：
        #   · 控制组单独成族（m = 控制组有效因子数）
        #   · 原始 + 控制合并成族（m = 全家族）—— 更保守，作为主口径
        ctrl_names = [k for k in names if k in controlled]
        ctrl_p = [controlled[k]["p"] for k in ctrl_names]
        bh_c = benjamini_hochberg(ctrl_p, 0.05)
        bonf_c = bonferroni(ctrl_p, 0.05)
        for idx, k in enumerate(ctrl_names):
            res = bh_c["results"][idx]
            if res:
                controlled[k]["p_adjusted_bh_control_family"] = res["p_adjusted"]
                controlled[k]["rejected_bh_control_family"] = res["rejected"]
            bres = bonf_c["results"][idx]
            if bres:
                controlled[k]["p_adjusted_bonferroni_control_family"] = bres["p_adjusted"]
                controlled[k]["rejected_bonferroni_control_family"] = bres["rejected"]

        # 合并族：原始 7 + 控制 7 = 14（顺序与 names 一致，便于映射回因子）
        combined_p = [results[k].get("p") for k in names] + ctrl_p
        bh_all = benjamini_hochberg(combined_p, 0.05)
        bonf_all = bonferroni(combined_p, 0.05)
        for idx, k in enumerate(ctrl_names):
            pos = len(names) + idx
            res = bh_all["results"][pos]
            if res:
                controlled[k]["p_adjusted_bh_combined"] = res["p_adjusted"]
                controlled[k]["rejected_bh_combined"] = res["rejected"]
            bres = bonf_all["results"][pos]
            if bres:
                controlled[k]["p_adjusted_bonferroni_combined"] = bres["p_adjusted"]
                controlled[k]["rejected_bonferroni_combined"] = bres["rejected"]
        for idx, k in enumerate(names):
            res = bh_all["results"][idx]
            if res:
                results[k]["p_adjusted_bh_combined"] = res["p_adjusted"]
                results[k]["rejected_bh_combined"] = res["rejected"]

        m_all = len(names) + len(ctrl_p)
        print("\n" + "-" * 96)
        print(f"控制「{control}」（规模/流动性）后的残差 IC —— 检验基本面溢价是否独立于市值暴露")
        print("-" * 96)
        print(f"{'因子':<20}{'原始 IC':>10}{'原始 t':>9}{'残差 IC':>10}"
              f"{'残差 t':>9}{'p_BH(控制族)':>14}{'p_BH(合并14)':>14}  判读")
        for k in names:
            r, c = results[k], controlled.get(k)
            if "ic_mean" not in r or c is None:
                continue
            if abs(c["ic_mean"]) < 1e-9 or (r["ic_mean"] * c["ic_mean"] < 0):
                note = "符号翻转或归零 → 溢价主要来自市值暴露"
            elif abs(c["ic_mean"]) < abs(r["ic_mean"]) * 0.5:
                note = "残差 IC 大幅衰减 → 大部分来自市值暴露"
            else:
                note = f"残差 IC 保留（{abs(c['ic_mean']) / abs(r['ic_mean']):.0%}）→ 存在独立成分"
            mark = "✅" if c.get("rejected_bh_combined") else "—"
            print(f"{k:<20}{r['ic_mean']:>+10.4f}{r['t']:>9.2f}"
                  f"{c['ic_mean']:>+10.4f}{c['t']:>9.2f}"
                  f"{c.get('p_adjusted_bh_control_family', float('nan')):>14.4f}"
                  f"{c.get('p_adjusted_bh_combined', float('nan')):>14.4f}  {mark} {note}")
        print(f"\n  控制组单独成族：m = {len(ctrl_p)}，BH 拒绝 {bh_c['k']}，"
              f"Bonferroni 拒绝 {bonf_c['k']}")
        print(f"  原始 + 控制合并族：m = {m_all}，BH 拒绝 {bh_all['k']}，"
              f"Bonferroni 拒绝 {bonf_all['k']}"
              f"（未校正族错误率 {1 - 0.95 ** m_all:.1%}）")
        print(f"  注：控制变量 {control} 的残差化用项目已验证的顺序残差化"
              f"（factors/factor_ic_lab.orthogonalize_panel），"
              f"残差因子不再可单独解释。")
        print("  判读列以**合并族**为准（更保守）：✅ = 校正后仍显著。")
    else:
        print("\n（未启用控制变量分析：--control 为空）")

    print("\n口径限制（必须随结论声明）：")
    print("  · roe 为年初至今累计口径，非 TTM；跨报告期比较前须按 report_period 过滤")
    print("  · 可用日优先取巨潮资讯**真实披露日**（A 股池内覆盖 86.8%）；"
          "缺失时退回法定截止日（12.8%）")
    print("  · 检验之间不独立（同数据、因子相关）→ BH 结果为参考下界")

    if args.out:
        payload = {
            "factors": results, "n_rebalance_dates": len(sizes),
            "avg_cross_section": statistics.mean(sizes),
            "fundamental_coverage": (covered / seen) if seen else 0.0,
            "availability_basis_counts": basis_counts,
            "records_in_pool": len(pool_records),
            "records_total_raw": len(records),
            "records_non_ashare": non_pool,
            "used_availability_basis": used_basis,
            "disclosure_dates_loaded": len(disc),
            "dataset_fingerprint": ds_fp,
            "announce_date_audit": {"suspicious_ratio": diag["suspicious_ratio"],
                                    "records_total": diag["records_total"]},
            "controlled_by": control or None,
            "controlled": controlled,
            "multiple_testing_combined_family": (
                {"m": len(names) + len(controlled),
                 "bh_rejected": bh_all["k"], "bonferroni_rejected": bonf_all["k"],
                 "fwer_uncorrected": 1 - 0.95 ** (len(names) + len(controlled))}
                if controlled else None),
            "multiple_testing": {"m": len(names), "bh_rejected": bh["k"],
                                 "bonferroni_rejected": bonf["k"],
                                 "fwer_uncorrected": 1 - 0.95 ** len(names),
                                 "deflated": deflated},
            "args": vars(args), "elapsed_sec": round(time.time() - t0, 1),
            "caveats": [
                "roe 为 YTD 累计口径，非 TTM",
                "可用日优先取巨潮资讯真实披露日（A 股池内覆盖 86.8%），"
                "缺失时退回法定截止日（12.8%）",
                "检验之间不独立，BH 结果为参考下界而非严格 FDR 保证",
                "先验方向已事前写定，不因结果调整",
                f"残差 IC 的控制变量为 {control}；残差因子不再可单独解释",
                "DSR/PSR/MinTRL 口径见 DSR_IC_FAMILY_PREREG.md：sr 为逐期 ICIR"
                "（非收益率夏普、未年化）；E[max SR] 假设各试验独立，"
                "本族试验相关 ⇒ DSR 偏保守；只作证据强度参考，"
                "不作为否定既有 BH 结论的新门槛",
            ],
        }
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                  encoding="utf-8", newline="\n")
        print(f"\n结果已写入: {args.out}")
    print(f"用时 {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
