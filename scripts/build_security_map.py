# -*- coding: utf-8 -*-
"""构建证券代码映射表（DATA_CHANNEL_PREREG 组件 B，②）。

输入：``D:/tdx_dataset_v3/stocks/*.metadata.json``（5,667 个）。
输出：``security_map.json``（表本体）+ ``security_map.meta.json``
（真实来源、条数、对表本体的指纹）。

可选 ``--secucode-from``：拿东财预约披露表（`fetch/disclosure_eastmoney.py`
的产物）里的 ``SECUCODE`` 后缀做**市场交叉校验**（M-6）——
分歧只登记，不静默改规则。

用法::

    python scripts/build_security_map.py
    python scripts/build_security_map.py \
        --secucode-from D:/tdx_dataset_v3/disclosure_eastmoney.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch.fingerprint import fingerprint_file  # noqa: E402
from pit.security_map import SecurityMap  # noqa: E402

SUFFIX_TO_MARKET = {".SH": "sh", ".SZ": "sz", ".BJ": "bj"}


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def crosscheck_markets(smap: SecurityMap, secucode_jsonl: Path) -> Dict[str, Any]:
    """映射表 market vs 东财 SECUCODE 后缀（M-6）。

    返回一致率与分歧清单。**分歧不修规则** —— 规则是否要改是另一个决定，
    必须先看见分歧长什么样。
    """
    from pit.security_map import (
        MarketMismatchError,
        SecurityMapError,
        market_of_code,
    )
    seen: Dict[str, set] = {}
    with secucode_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = str(r.get("code") or "").zfill(6)
            secucode = str(r.get("secucode") or "")
            for suf, mkt in SUFFIX_TO_MARKET.items():
                if secucode.upper().endswith(suf):
                    seen.setdefault(code, set()).add(mkt)
    agree, disagree, unmapped = 0, [], []
    for code, mkts in sorted(seen.items()):
        if len(mkts) > 1:
            disagree.append({"code": code, "secucode_markets": sorted(mkts),
                             "reason": "同一代码在东财出现多个市场后缀"})
            continue
        mkt = next(iter(mkts))
        try:
            entry = smap.resolve(code, mkt)
        except MarketMismatchError:
            # 代码段不属于 SECUCODE 指认的市场 ⇒ **分歧**（不是缺失）：
            # 库内按规则推断的市场与外部源指认的不一致。
            try:
                inferred = market_of_code(code)
                entry = smap.resolve(code, inferred)
            except SecurityMapError:
                unmapped.append({"code": code, "secucode_market": mkt})
                continue
            disagree.append({"code": code, "map_market": inferred,
                             "secucode_market": mkt, "name": entry.name})
            continue
        except SecurityMapError:
            unmapped.append({"code": code, "secucode_market": mkt})
            continue
        if entry.market == mkt:
            agree += 1
        else:  # 理论不可达（resolve 成功即条目市场 = 请求市场），防御性保留
            disagree.append({"code": code, "map_market": entry.market,
                             "secucode_market": mkt, "name": entry.name})
    return {"compared": agree + len(disagree) + len(unmapped),
            "agree": agree, "disagree": disagree, "unmapped": unmapped,
            "agree_ratio": (agree / (agree + len(disagree) + len(unmapped))
                            if (agree + len(disagree) + len(unmapped)) else None)}


def main() -> int:
    ap = argparse.ArgumentParser(description="构建证券代码映射表（②）")
    ap.add_argument("--stocks", default="D:/tdx_dataset_v3/stocks")
    ap.add_argument("--out", default="D:/tdx_dataset_v3/security_map.json")
    ap.add_argument("--secucode-from", default="",
                    help="东财预约披露表 JSONL（可选，做市场交叉校验 M-6）")
    ap.add_argument("--audit-sample", type=int, default=0,
                    help="delist 对账抽样数（0 = 全量）")
    args = ap.parse_args()

    stocks = Path(args.stocks)
    if not stocks.is_dir():
        print(f"股票元数据目录不存在：{stocks}", flush=True)
        return 2

    smap = SecurityMap.build_from_metadata(stocks)
    print(f"映射表：{len(smap):,} 条；市场分布 {smap.market_counts()}", flush=True)
    print(f"successor 已知条数：{smap.successor_known_count}"
          f"（预期 0 —— 无本地来源，不硬凑）", flush=True)
    an = smap.anomalies
    for k in ("unknown_market", "missing_list_date", "delisted_without_date"):
        if an.get(k):
            print(f"  ⚠️ 异常 {k}：{len(an[k])} 条 {an[k][:10]}", flush=True)
    if an.get("undated"):
        print(f"  ⚠️ 无法解析的 metadata：{an['undated']} 个", flush=True)

    audit = smap.audit_delist_consistency(
        stocks, sample=args.audit_sample if args.audit_sample > 0 else None)
    print(f"delist 对账：核对 {audit['checked']:,} 条，全库最后交易日 "
          f"{audit['dataset_end']}；判定分布 {audit['counts']}", flush=True)
    for key, v in audit["verdicts"].items():
        if v["verdict"] in ("mismatch", "stale_but_active"):
            print(f"  ⚠️ {key}: {v['verdict']} last_bar={v['last_bar']} "
                  f"meta_delisted={v['meta_delisted']!r}", flush=True)

    out = Path(args.out)
    payload = smap.to_dict(built_at=_now())
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8", newline="\n")

    meta: Dict[str, Any] = {
        "source": f"本地数据集 stocks/*.metadata.json（{stocks}）",
        "built_at": _now(),
        "schema": smap.SCHEMA,
        "count": len(smap),
        "market_counts": smap.market_counts(),
        "successor_known_count": smap.successor_known_count,
        "anomaly_counts": {k: (len(v) if isinstance(v, list) else v)
                           for k, v in an.items()},
        "delist_audit_counts": audit["counts"],
        "delist_audit_dataset_end": audit["dataset_end"],
        "caveats": [
            "market 由代码段规则推断（2026-10-18 全库扫描实证），"
            "未知代码段不猜、记异常",
            "裸码 000000-000999 为歧义区（SH 指数 ∩ SZ 股票），"
            "resolve 必须显式给 market",
            "successor 一律空（无本地来源）；002190/302132 经核实为"
            "两家不同公司，行情重叠不构成 successor 证据",
            "delist 对账的 mismatch/stale_but_active 只登记不修改",
        ],
    }

    if args.secucode_from:
        sj = Path(args.secucode_from)
        if sj.is_file():
            xc = crosscheck_markets(smap, sj)
            meta["secucode_crosscheck"] = {
                "source": str(sj), "compared": xc["compared"],
                "agree": xc["agree"], "agree_ratio": xc["agree_ratio"],
                "disagree_count": len(xc["disagree"]),
                "unmapped_count": len(xc["unmapped"]),
                "disagree_head": xc["disagree"][:20],
                "unmapped_head": xc["unmapped"][:20],
            }
            print(f"SECUCODE 交叉校验：比对 {xc['compared']:,} 个代码，"
                  f"一致 {xc['agree']:,}（{xc['agree_ratio']:.4%}），"
                  f"分歧 {len(xc['disagree'])}，映射表缺失 {len(xc['unmapped'])}",
                  flush=True)
            for d in xc["disagree"][:10]:
                print(f"  ⚠️ 分歧 {d}", flush=True)
        else:
            print(f"（--secucode-from 文件不存在，跳过 M-6：{sj}）", flush=True)

    fp = fingerprint_file(out)
    meta["fingerprint"] = fp
    out.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"\n已写出：{out}（{fp['lines']:,} 行 / {fp['bytes']:,} B / "
          f"md5={fp['md5']}）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
