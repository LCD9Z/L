# -*- coding: utf-8 -*-
"""Phase 26: end-to-end, evidence-first real-data Alpha pipeline.

This module intentionally refuses to manufacture a verdict.  It can:
1) acquire/load certified price files,
2) re-check SHA-256 integrity,
3) split data chronologically without overlap,
4) run the project's executable A-share portfolio backtest,
5) align strategy and benchmark returns,
6) run the Alpha Survival analysis and emit a reproducible evidence bundle.

It does not download data itself; real_data_collector remains the acquisition layer.
"""
from __future__ import annotations
import csv, json, hashlib
from pathlib import Path
from datetime import datetime, timezone
from itertools import pairwise
from typing import Dict, List, Any

from portfolio_backtest import portfolio_backtest
from professional_audit import audit_research_evidence
from alpha.alpha_survival_lab import analyse_alpha
from pit.pit_integrity import audit_pit_rows
from historical_universe import point_in_time_universe
from release_gate import build_survivorship_audit, gate_alpha_claim


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_certified_csv(path: str | Path, metadata_path: str | Path | None = None) -> List[dict]:
    path = Path(path)
    if metadata_path is None:
        metadata_path = path.with_suffix(".metadata.json")
    mp = Path(metadata_path)
    if not path.exists() or not mp.exists():
        raise ValueError("certified_data_or_metadata_missing")
    meta = json.loads(mp.read_text(encoding="utf-8"))
    if not meta.get("strict") or not meta.get("sha256"):
        raise ValueError("dataset_not_strictly_certified")
    if _sha256(path) != meta["sha256"]:
        raise ValueError("dataset_sha256_mismatch")
    rows=[]
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            bar = {
                "date": r["date"], "open": float(r["open"]), "close": float(r["close"]),
                "high": float(r["high"]), "low": float(r["low"]),
                "volume": float(r.get("volume") or 0), "amount": float(r.get("amount") or 0),
            }
            # 逐日交易状态字段**透传**（数据集有则带上，没有则省略）。
            # 涨跌停判定需要它们：主板 ST 股票的涨跌幅与普通股不同
            # （2026-07-06 前 ±5%，之后 ±10%），缺了会产生**单向乐观偏差**
            # ——真实一字板买不进的票会被当成可买。见 exchange_rules.derive_limit_ratio。
            # ⚠️ `turnover` 必须在列：`walk_forward.score_history` 的换手率分项
            # 依赖它，缺失时该分项**静默失效**（恒为 0，−5~+10 的区分度全部丢失）。
            # 2026-09-26 实测：白名单漏掉它 → 阈值 70 的过线率只有 **6.65%**，
            # 而恢复后为 **18.71%**（近 3 倍）—— 即策略长期在**远窄于设计意图**的
            # 候选池里选股。CSV 中该列一直有值（认证字段），是加载器丢弃了它。
            for key in ("is_st", "limit_ratio", "limit_pct", "turnover", "turnover_rate"):
                if r.get(key) not in (None, ""):
                    bar[key] = r[key]
            rows.append(bar)
    if len(rows) != int(meta.get("rows", -1)):
        raise ValueError("dataset_row_count_mismatch")
    if sorted(r["date"] for r in rows) != [r["date"] for r in rows]:
        raise ValueError("dataset_not_sorted")
    return rows


def split_chronological(data: Dict[str, List[dict]], oos_start: str) -> tuple[Dict[str,List[dict]], Dict[str,List[dict]]]:
    train={}; oos={}
    for code,bars in data.items():
        a=[b for b in bars if str(b["date"]) < oos_start]
        b=[x for x in bars if str(x["date"]) >= oos_start]
        if a: train[code]=a
        if b: oos[code]=b
    if not oos:
        raise ValueError("no_out_of_sample_data")
    return train,oos


def _curve_returns(curve: List[dict]) -> Dict[str,float]:
    out={}
    for prev,cur in pairwise(curve):
        if prev["equity"] > 0:
            out[str(cur["date"])] = cur["equity"]/prev["equity"]-1
    return out


def _benchmark_returns(bars: List[dict]) -> Dict[str,float]:
    out={}
    for a,b in pairwise(bars):
        if a["close"] > 0:
            out[str(b["date"])] = b["close"]/a["close"]-1
    return out


def run_real_alpha_pipeline(
    stock_files: Dict[str, str],
    benchmark_file: str,
    oos_start: str,
    *,
    metadata_files: Dict[str,str] | None = None,
    benchmark_metadata: str | None = None,
    backtest_kwargs: Dict[str,Any] | None = None,
    min_periods: int = 252,
    universe_snapshot_map: Dict[str, List[str]] | None = None,
    survivorship_evidence: Dict[str, Any] | None = None,
) -> Dict[str,Any]:
    """Run only on SHA-verified strict datasets. Returns INCONCLUSIVE on evidence gaps.

    ``survivorship_evidence`` 声明研究完整性证据的具备情况（键名见
    ``release_gate.EVIDENCE_KEYS``）。**未声明即视为缺失**，
    此时统计结论会被门禁降级为 ``INCONCLUSIVE``，但原始结论保留在
    ``statistical_verdict`` 字段中，不会丢失信息。
    """
    metadata_files = metadata_files or {}
    preflight=audit_research_evidence(stock_files, metadata_files, benchmark_file, benchmark_metadata, min_assets=2, min_rows_per_asset=min_periods*2)
    if preflight["verdict"] != "PASS":
        return {"verdict":"INCONCLUSIVE","reason":"professional_evidence_gate_failed","preflight":preflight}
    provenance: Dict[str, Any] = {"stocks": {}, "benchmark": {}}
    data={}
    try:
        for code,path in stock_files.items():
            data[code]=load_certified_csv(path, metadata_files.get(code))
            provenance["stocks"][code]={"path":str(path),"sha256":_sha256(Path(path))}
        benchmark=load_certified_csv(benchmark_file, benchmark_metadata)
        provenance["benchmark"]={"path":str(benchmark_file),"sha256":_sha256(Path(benchmark_file))}
    except Exception as exc:
        return {"verdict":"INCONCLUSIVE","reason":"data_integrity_failed","detail":str(exc)}

    if universe_snapshot_map is None:
        return {"verdict":"INCONCLUSIVE","reason":"pit_universe_required"}
    try:
        allowed_oos = {d: set(point_in_time_universe(universe_snapshot_map, d)) for d in sorted({str(b["date"]) for bars in data.values() for b in bars if str(b["date"]) >= oos_start})}
    except Exception as exc:
        return {"verdict":"INCONCLUSIVE","reason":"pit_universe_invalid","detail":str(exc)}
    for code, bars in data.items():
        # EOD market bars are timestamped by trade date. If a dataset carries
        # availability/publication/as-of timestamps, each field is checked against
        # the row's own trade date rather than a single global OOS cutoff.
        rows = [{"code": code, **b} for b in bars]
        audit = audit_pit_rows(rows, cutoff=None, require_timestamp=False)
        if not audit["ok"]:
            return {"verdict":"INCONCLUSIVE","reason":"market_data_pit_integrity_failed","code":code,"audit":audit}
    # Preserve pre-OOS bars as factor warm-up history; only signals after oos_start
    # are allowed to create positions. This avoids a hidden cold-start bias.
    restricted={}
    for code,bars in data.items():
        filtered=[]
        ever_allowed=False
        for b in bars:
            d=str(b["date"])
            if d >= oos_start and code not in allowed_oos.get(d, set()):
                continue
            filtered.append(b)
            if d >= oos_start and code in allowed_oos.get(d, set()):
                ever_allowed=True
        if ever_allowed:
            restricted[code]=filtered
    oos=restricted
    bench_oos=[b for b in benchmark if str(b["date"]) >= oos_start]
    # Evidence must not silently rest on a single surviving constituent.
    # Every submitted stock must have OOS observations and the benchmark must be long enough.
    missing_oos=sorted(set(data)-set(oos))
    if missing_oos or len(oos)<2 or len(bench_oos)<2:
        return {"verdict":"INCONCLUSIVE","reason":"insufficient_oos_coverage",
                "missing_stock_oos":missing_oos,"oos_assets":len(oos)}

    kwargs: Dict[str, Any] = {"threshold": 70, "top_n": 5, "horizon": 5}
    kwargs.update(backtest_kwargs or {})
    kwargs.setdefault("start_signal_date", oos_start)
    result=portfolio_backtest(oos, universe_snapshot_map=universe_snapshot_map, **kwargs)
    strategy_ret=_curve_returns(result.get("equity_curve",[]))
    bench_ret=_benchmark_returns(bench_oos)
    common=sorted(set(strategy_ret)&set(bench_ret))
    if len(common)<min_periods:
        return {
            "verdict":"INCONCLUSIVE","reason":"insufficient_aligned_oos_periods",
            "aligned_periods":len(common),"required_min_periods":min_periods,
            "backtest":result,"provenance":provenance,
        }
    analysis=analyse_alpha(
        {d:strategy_ret[d] for d in common},
        {d:bench_ret[d] for d in common},
        min_periods=min_periods,
    )
    verdict_map={"SUPPORTED":"ALPHA_SUPPORTED","NOT_SUPPORTED":"ALPHA_NOT_ESTABLISHED","INCONCLUSIVE":"INCONCLUSIVE"}
    statistical_verdict=verdict_map.get(analysis.get("verdict"),analysis.get("verdict"))
    # 研究完整性门禁：这是本管线唯一会「发布」Alpha 结论的位置。
    # PIT 股票池由本流程自行校验（否则前面已提前返回），故如实声明为已具备；
    # 其余证据一律要求调用方显式声明，未声明即视为缺失 —— 缺失证据不推断为有效。
    survivorship_audit=build_survivorship_audit(survivorship_evidence, pit_universe_verified=True)
    analysis.update(gate_alpha_claim(statistical_verdict, survivorship_audit))
    analysis["backtest"]=result
    analysis["aligned_periods"]=len(common)
    analysis["oos_start"]=oos_start
    analysis["provenance"]=provenance
    analysis["generated_at_utc"]=datetime.now(timezone.utc).isoformat()
    return analysis


def save_evidence_bundle(report: Dict[str,Any], path: str | Path) -> str:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    return str(path)
