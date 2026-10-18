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
import csv, json
from pathlib import Path
from datetime import datetime, timezone
from itertools import pairwise
from typing import Dict, List, Any, Optional

from portfolio_backtest import portfolio_backtest
from professional_audit import audit_research_evidence
from alpha.alpha_survival_lab import analyse_alpha
from pit.pit_integrity import audit_pit_rows
from pit.pit_snapshot_store import sha256_of_file as _sha256  # P4 收敛（审计 4.2）：原 read_bytes 一次性读 → 分块读
from historical_universe import point_in_time_universe
from release_gate import build_survivorship_audit, gate_alpha_claim


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


def split_chronological(
    data: Dict[str, List[dict]],
    oos_start: str,
    embargo_days: int = 0,
    horizon: Optional[int] = None,
) -> tuple[Dict[str,List[dict]], Dict[str,List[dict]]]:
    """按 `oos_start` 切分训练/测试集，可选 embargo。

    Parameters
    ----------
    data:
        ``{code: bars}``，每个 ``bars`` 必须已按日期升序（本函数会校验）。
    oos_start:
        样本外起点（`YYYY-MM-DD` 或 `YYYYMMDD`）。
    embargo_days:
        在 `oos_start` 之前额外剔除的**交易日**数。默认 **0** ——
        即与改造前逐位相同的行为（见下「为什么默认是 0」）。
    horizon:
        标签持有期（交易日）。若提供，实际 embargo 取
        ``max(embargo_days, horizon)``：**小于 horizon 的 embargo 挡不住泄漏** ——
        训练集末尾第 1 个样本的标签仍会跨越 `oos_start`。

    Returns
    -------
    ``(train, oos)``；`oos` 为空时抛 ``ValueError``。

    Raises
    ------
    ValueError
        - ``data_not_sorted``：某只标的的 bars 非升序；
        - ``no_out_of_sample_data``：测试集为空（既有行为）；
        - ``embargo_exceeds_train``：embargo 把训练集清空了
          —— **不静默返回空训练集**，那会让调用方误以为「无训练数据」
          而不是「切分参数不合理」。

    Notes
    -----
    **为什么需要 embargo**：若不剔除，训练集的最后一天与测试集的第一天
    紧邻。若标签持有期为 `horizon`，训练集末尾的信号要用到 `oos_start`
    **之后**的价格才能知道结果 ⇒ **标签泄漏**（purged CV 的对偶问题）。
    `embargo_days` 就是在两者之间留出间隔。

    **为什么默认是 0**：默认值就是一处口径。本函数改造前零调用方，
    但「静默把默认行为改成带 embargo」会让将来第一个调用方在不知情的
    情况下拿到与旧版不同的切分。故保持 0，由调用方显式启用；
    启用时的最小安全值由 ``max(embargo_days, horizon)`` 保证。
    详见 `COST_AUTHORITY_AND_EMBARGO_PREREG.md` §三。

    ⚠️ **与 `run_real_alpha_pipeline` 的关系**：那个 pipeline 是**纯样本外**
    设计（pre-OOS bars 仅作因子 warm-up，不拟合参数），**不需要 embargo**，
    本函数的改动不影响它。见预注册 §1b 的作用对象检查。
    """
    eff_embargo = int(embargo_days or 0)
    if horizon is not None:
        eff_embargo = max(eff_embargo, int(horizon))
    if eff_embargo < 0:
        raise ValueError("embargo_days_must_be_non_negative")

    train: Dict[str, List[dict]] = {}
    oos: Dict[str, List[dict]] = {}
    for code, bars in data.items():
        if not bars:
            continue
        dates = [str(b["date"]) for b in bars]
        if dates != sorted(dates):
            raise ValueError(f"data_not_sorted:{code}")
        # 第一个 >= oos_start 的位置（bars 已校验升序）
        i_oos = 0
        while i_oos < len(bars) and dates[i_oos] < str(oos_start):
            i_oos += 1
        cut = i_oos - eff_embargo
        if cut < 0:
            raise ValueError(
                f"embargo_exceeds_train:{code}:"
                f"train_len={i_oos},embargo={eff_embargo}"
            )
        a = bars[:cut]
        b = bars[i_oos:]
        if a:
            train[code] = a
        if b:
            oos[code] = b
    if not oos:
        raise ValueError("no_out_of_sample_data")
    return train, oos


def embargo_cutoff(data: Dict[str, List[dict]], oos_start: str, embargo_days: int) -> Optional[str]:
    """训练集允许的最后交易日（加 embargo 后），供日志/产物留痕。

    跨标的取**最早**的那个截止日（保守：宁可多剔，不可少剔）。
    无可用训练集时返回 None。
    """
    eff = int(embargo_days or 0)
    if eff <= 0:
        return None
    latest = None
    for code, bars in data.items():
        if not bars:
            continue
        dates = [str(b["date"]) for b in bars]
        i_oos = 0
        while i_oos < len(bars) and dates[i_oos] < str(oos_start):
            i_oos += 1
        cut = i_oos - eff
        if cut < 0:
            return None
        d = dates[cut - 1] if cut > 0 else None
        if d is None:
            return None
        latest = d if latest is None else min(latest, d)
    return latest


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
