# -*- coding: utf-8 -*-
"""双源披露日交叉校验（DATA_CHANNEL_PREREG 组件 C，判据 D-2~D-5）。

比对两个独立来源的「报告期 → 公告日」：

* **巨潮表** `disclosure_dates.jsonl`（PIT 首选依据，来自
  `fetch.fundamentals_source.fetch_disclosure_period`）；
* **东财表** `disclosure_eastmoney.jsonl`（本立项新建的第二源）。

同语义字段对齐：``first_scheduled ↔ first_appoint``、
``actual_disclose ↔ actual_publish``。**冲突不静默覆盖** ——
两列并存，逐条列出；PIT 主口径（`pit.pit_fundamentals`）不接线。

同时量化 D-5：池内现走「法定截止日」兜底的记录里，东财表有日期的
比例 —— 只量化「接线会改变什么」，**不接线**。

用法::

    python scripts/crosscheck_disclosure_sources.py
    python scripts/crosscheck_disclosure_sources.py --sample-size 200
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pit.pit_fundamentals import (  # noqa: E402
    load_records,
    resolve_availability,
)

_ISO = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _load_jsonl_map(path: Path, fields: Tuple[str, ...]
                    ) -> Tuple[Dict[Tuple[str, str], Dict[str, str]], int]:
    """读 JSONL → ``{(code, period): {field: value}}``；坏日期/坏行跳过并计数。"""
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    bad = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            code = str(r.get("code") or "").zfill(6)
            period = str(r.get("report_period") or "")
            if not code or not _ISO.match(period):
                bad += 1
                continue
            rec = {f: str(r.get(f) or "") for f in fields}
            out[(code, period)] = rec
    return out, bad


def _days(later: str, earlier: str) -> Optional[int]:
    from datetime import date
    try:
        return (date.fromisoformat(later) - date.fromisoformat(earlier)).days
    except (ValueError, TypeError):
        return None


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def main() -> int:
    ap = argparse.ArgumentParser(description="巨潮 vs 东财 披露日交叉校验")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v3")
    ap.add_argument("--fundamentals", default="D:/tdx_dataset_v3/fundamentals.jsonl")
    ap.add_argument("--sample-size", type=int, default=100)
    ap.add_argument("--out", default="D:/tdx_dataset_v3/disclosure_crosscheck.json")
    args = ap.parse_args()

    ds = Path(args.dataset)
    cn_path = ds / "disclosure_dates.jsonl"
    em_path = ds / "disclosure_eastmoney.jsonl"
    for p in (cn_path, em_path):
        if not p.is_file():
            print(f"缺少输入：{p}", flush=True)
            return 2

    cn, cn_bad = _load_jsonl_map(cn_path, ("actual_disclose", "first_scheduled"))
    em, em_bad = _load_jsonl_map(em_path, ("actual_publish", "first_appoint"))
    print(f"巨潮表 {len(cn):,} 键（坏行 {cn_bad}）；东财表 {len(em):,} 键"
          f"（坏行 {em_bad}）", flush=True)

    common = sorted(set(cn) & set(em))
    only_cn = sorted(set(cn) - set(em))
    only_em = sorted(set(em) - set(cn))
    print(f"共同键 {len(common):,}；仅巨潮 {len(only_cn):,}；仅东财 {len(only_em):,}",
          flush=True)

    def _compare(field_cn: str, field_em: str) -> Dict[str, Any]:
        agree = conflict = cn_only = em_only = 0
        conflicts: List[Dict[str, str]] = []
        for key in common:
            a = cn[key].get(field_cn, "")
            b = em[key].get(field_em, "")
            if a and b:
                if a == b:
                    agree += 1
                else:
                    conflict += 1
                    if len(conflicts) < 20:
                        conflicts.append({"code": key[0], "report_period": key[1],
                                          "cninfo": a, "eastmoney": b})
            elif a:
                cn_only += 1
            elif b:
                em_only += 1
        both = agree + conflict
        return {"agree": agree, "conflict": conflict,
                "agree_ratio": (agree / both) if both else None,
                "cn_only_value": cn_only, "em_only_value": em_only,
                "conflicts_head": conflicts}

    xc_first = _compare("first_scheduled", "first_appoint")
    xc_actual = _compare("actual_disclose", "actual_publish")
    for name, xc in (("first_scheduled vs FIRST_APPOINT_DATE", xc_first),
                     ("actual_disclose vs ACTUAL_PUBLISH_DATE", xc_actual)):
        print(f"\n{name}：双方有值 {xc['agree'] + xc['conflict']:,}，"
              f"一致 {xc['agree']:,}（{xc['agree_ratio']:.4%}），"
              f"冲突 {xc['conflict']:,}；仅巨潮有值 {xc['cn_only_value']:,}，"
              f"仅东财有值 {xc['em_only_value']:,}", flush=True)
        for c in xc["conflicts_head"][:5]:
            print(f"  冲突样本 {c}", flush=True)

    # ---- D-2 抽样 100 条：公告日 ≥ 报告期 ----
    keys = [k for k in common if em[k]["actual_publish"]]
    step = max(1, len(keys) // args.sample_size)
    sample = keys[::step][:args.sample_size]
    bad_future = [{"code": k[0], "report_period": k[1],
                   "actual_publish": em[k]["actual_publish"]}
                  for k in sample
                  if (_days(em[k]["actual_publish"], k[1]) or 0) < 0]
    print(f"\nD-2 抽样 {len(sample)} 条：公告日早于报告期的 "
          f"{len(bad_future)} 条", flush=True)
    for b in bad_future[:10]:
        print(f"  ⚠️ {b}", flush=True)

    # ---- D-3 滞后分布 ----
    lags = sorted(d for d in (_days(em[k]["actual_publish"], k[1])
                              for k in keys) if d is not None)
    zeros = sum(1 for d in lags if d == 0)
    neg = sum(1 for d in lags if d < 0)
    dist = {"n": len(lags), "min": lags[0] if lags else None,
            "p25": _percentile(lags, 0.25), "median": _percentile(lags, 0.5),
            "p75": _percentile(lags, 0.75), "p90": _percentile(lags, 0.9),
            "max": lags[-1] if lags else None,
            "zeros": zeros, "negative": neg,
            "all_zero": bool(lags) and zeros == len(lags)}
    print(f"D-3 滞后（公告日−报告期，天）：n={dist['n']:,} min={dist['min']} "
          f"p25={dist['p25']} 中位={dist['median']} p75={dist['p75']} "
          f"p90={dist['p90']} max={dist['max']}；零滞后 {dist['zeros']:,}，"
          f"负滞后 {dist['negative']:,}，全零={dist['all_zero']}", flush=True)

    # ---- D-5 补缺潜力（只量化，不接线）----
    from pit.pit_fundamentals import load_disclosures
    gap = _gap_fill_potential(args.fundamentals, ds, em,
                              load_disclosures(ds / "disclosure_dates.jsonl"))
    print(f"\nD-5 补缺潜力（不接线）：池内记录 {gap['pool_records']:,}；"
          f"现走法定兜底 {gap['statutory']:,}（{gap['statutory_ratio']:.2%}）；"
          f"其中东财表有 actual_publish 的 {gap['fillable']:,}"
          f"（{gap['fill_ratio']:.2%}）", flush=True)

    payload = {
        "inputs": {"cninfo": str(cn_path), "eastmoney": str(em_path)},
        "cninfo_keys": len(cn), "eastmoney_keys": len(em),
        "bad_lines": {"cninfo": cn_bad, "eastmoney": em_bad},
        "common_keys": len(common), "only_cninfo": len(only_cn),
        "only_eastmoney": len(only_em),
        "compare_first_appoint": xc_first,
        "compare_actual_publish": xc_actual,
        "d2_sample": {"size": len(sample), "step": step,
                      "future_dated": len(bad_future), "bad_head": bad_future[:20]},
        "d3_lag_distribution": dist,
        "d5_gap_fill_potential": gap,
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                              encoding="utf-8", newline="\n")
    print(f"\n已写出：{args.out}", flush=True)
    return 0


def _gap_fill_potential(fundamentals_path: str, dataset: Path,
                        em: Dict[Tuple[str, str], Dict[str, str]],
                        cn_disc: Optional[Dict[Tuple[str, str], str]]) -> Dict[str, Any]:
    """池内现走 statutory_deadline 兜底（**带巨潮表**口径，与研究的
    `basis_counts` 同口径）的记录中，东财表能补多少。

    **只量化**：不改 `resolve_availability`，不产生任何新 PIT 口径。
    """
    records = load_records(fundamentals_path)
    import csv as _csv
    pool_path = dataset / "pool_v2.csv"
    if not pool_path.exists():
        pool_path = dataset / "pool.csv"
    pool_codes = set()
    if pool_path.exists():
        with pool_path.open(encoding="utf-8-sig", newline="") as fh:
            pool_codes = {r["code"].zfill(6) for r in _csv.DictReader(fh)}
    pool_records = [r for r in records
                    if str(r.get("code", "")).zfill(6) in pool_codes] if pool_codes else records
    statutory = fillable = 0
    for r in pool_records:
        _, basis = resolve_availability(r, cn_disc)
        if basis != "statutory_deadline":
            continue
        statutory += 1
        key = (str(r.get("code", "")).zfill(6), str(r.get("report_period") or ""))
        if em.get(key, {}).get("actual_publish"):
            fillable += 1
    return {"pool_records": len(pool_records), "statutory": statutory,
            "statutory_ratio": statutory / len(pool_records) if pool_records else 0.0,
            "fillable": fillable,
            "fill_ratio": fillable / statutory if statutory else 0.0}


if __name__ == "__main__":
    raise SystemExit(main())
