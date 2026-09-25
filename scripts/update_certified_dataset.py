# -*- coding: utf-8 -*-
r"""认证数据集**增量更新**：用新快照追加交易日。

## 为什么不能"直接往后 append"

数据集是**前复权（qfq）**序列。前复权价格**每次除权除息都会重新锚定** ——
新快照里同一只股票的历史价格可能与旧快照**不同**。若直接把新行追加到旧序列尾部，
会得到一条**锚定日不一致的混合序列**：历史段锚在旧日期、新增段锚在新日期，
跨接处出现**假跳空**。这类错误不会报错，只会静默污染全部趋势类信号。

## 本脚本的判定机制：**重叠日校验**

对每只股票取数据集最后一个交易日的收盘价，与新快照**同一天**的收盘价比较：

============================  ==========================================
判定                            处置
============================  ==========================================
相对偏差 <= ``--tolerance``     **锚定一致** → 安全追加末日之后的行
相对偏差 >  ``--tolerance``     **锚定已变** → 用新快照**整体替换**该股序列
新快照无该股 / 无重叠日         **无法判定** → **不动**，如实记入日志
============================  ==========================================

"无法判定"绝不当作"无需更新" —— 它必须出现在更新日志里，供人工核对。

## 同步更新的内容

* 个股 CSV（追加或整体替换）+ ``{code}.metadata.json``（rows / sha256 / 锚定说明）
* ``pool_v2.csv``（rows / last_date）
* ``pit_universe.json``（按上市/退市日把新交易日补进快照）
* ``update_log.json``（本次操作的可追溯记录）

## **不做**的事（必须随结论声明）

* **不复权源、复权因子事件、停牌区间不做增量推导** —— 它们依赖全量重扫，
  本脚本不假装能做。需要这三项更新时，应重跑
  ``scripts/build_certified_dataset_v2.py``（全量重建）。
* 不做除权调整层的重新推导；锚定变化的个股靠"整体替换"保证一致性。

用法::

    python scripts/update_certified_dataset.py --dataset D:/tdx_dataset_v3 \
        --src-qfq D:/原始数据/A股日K线_前复权_2016-2026.csv --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange_rules import derive_limit_ratio, is_st_flag  # noqa: E402

# 与 build_certified_dataset_v2.py 的 OUT_COLUMNS 保持一致
OUT_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount",
               "turnover", "is_st", "st_basis", "source", "name",
               "limit_ratio", "limit_basis"]

POOL_CANDIDATES = ("pool_v2.csv", "pool.csv")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_pool(dataset: Path) -> List[str]:
    for name in POOL_CANDIDATES:
        p = dataset / name
        if p.exists():
            with p.open(encoding="utf-8-sig", newline="") as fh:
                return [r["code"].zfill(6) for r in csv.DictReader(fh)]
    raise FileNotFoundError(f"{dataset} 下未找到 {'/'.join(POOL_CANDIDATES)}")


def tail_of_csv(path: Path) -> Optional[Tuple[str, float, int]]:
    """返回 ``(最后交易日, 最后收盘价, 行数)``；文件缺失或为空返回 ``None``。"""
    if not path.exists():
        return None
    last: Optional[Tuple[str, float]] = None
    n = 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            n += 1
            try:
                last = (row["date"], float(row["close"]))
            except (KeyError, TypeError, ValueError):
                continue
    return (last[0], last[1], n) if last else None


def scan_overlap_and_new(src: Path, known: Set[str],
                         last_dates: Dict[str, str]) -> Tuple[Dict[str, float],
                                                              Dict[str, List[dict]]]:
    """一趟扫描新快照：取重叠日收盘 + 末日之后的新行。"""
    overlap: Dict[str, float] = {}
    new_rows: Dict[str, List[dict]] = {}
    with src.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            code = str(row.get("code", "")).zfill(6)
            if code not in known:
                continue
            day = str(row.get("date", ""))
            ld = last_dates.get(code)
            if ld is None:
                continue
            if day == ld:
                try:
                    overlap[code] = float(row["close"])
                except (TypeError, ValueError):
                    pass
            elif day > ld:
                new_rows.setdefault(code, []).append(row)
    return overlap, new_rows


def collect_full_series(src: Path, codes: Set[str]) -> Dict[str, List[dict]]:
    """第二趟扫描：为需要整体替换的个股取全序列。"""
    out: Dict[str, List[dict]] = {}
    with src.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            code = str(row.get("code", "")).zfill(6)
            if code in codes:
                out.setdefault(code, []).append(row)
    return out


def to_out_row(row: dict, code: str) -> List[Any]:
    """源行 → 数据集列（含逐日涨跌幅限制派生，与全量构建口径一致）。"""
    vals = {k: row.get(k, "") for k in OUT_COLUMNS}
    try:
        t = float(row.get("turnover") or 0)
        vals["turnover"] = round(t * 100.0, 6) if t else ""
    except (TypeError, ValueError):
        vals["turnover"] = ""
    lr, basis = derive_limit_ratio(code, is_st=is_st_flag(row.get("is_st")),
                                   trade_date=row.get("date"))
    vals["limit_ratio"] = round(lr, 6)
    vals["limit_basis"] = basis
    return [vals[k] for k in OUT_COLUMNS]


def write_rows(path: Path, rows: List[List[Any]], header: Optional[List[str]] = None) -> None:
    """整体重写（LF 行尾，与项目约定一致）。"""
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if header:
            w.writerow(header)
        w.writerows(rows)


def append_rows(path: Path, rows: List[List[Any]]) -> None:
    with path.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)


def extend_pit(dataset: Path, pool_meta: Dict[str, Dict[str, str]],
               calendar: List[str]) -> Dict[str, Any]:
    """把新交易日补进 PIT 快照（按上市/退市日判定成员，停牌不除名）。"""
    p = dataset / "pit_universe.json"
    if not p.exists():
        return {"updated": False, "reason": "pit_universe.json 缺失"}
    payload = json.loads(p.read_text(encoding="utf-8"))
    snaps: Dict[str, List[str]] = payload["snapshots"]
    added = 0
    for day in calendar:
        if day in snaps:
            continue
        members = [c for c, v in pool_meta.items()
                   if (not v.get("list_date") or v["list_date"] <= day)
                   and (not v.get("delist_date") or v["delist_date"] > day)]
        snaps[day] = sorted(members)
        added += 1
    payload["as_of"] = max(snaps) if snaps else payload.get("as_of")
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"updated": added > 0, "days_added": added, "as_of": payload["as_of"]}


def main() -> int:
    ap = argparse.ArgumentParser(description="认证数据集增量更新（重叠日校验）")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--src-qfq", required=True)
    ap.add_argument("--tolerance", type=float, default=0.005,
                    help="重叠日收盘价的相对偏差容忍度（默认 0.5%%）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-log", default="")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    src = Path(args.src_qfq)
    if not dataset.is_dir() or not src.exists():
        print(f"路径不存在：dataset={dataset} src={src}", flush=True)
        return 2

    codes = load_pool(dataset)
    print(f"数据集 {dataset}：{len(codes)} 只", flush=True)

    last_dates: Dict[str, str] = {}
    last_close: Dict[str, float] = {}
    last_rows: Dict[str, int] = {}
    for c in codes:
        t = tail_of_csv(dataset / "stocks" / f"{c}.csv")
        if t:
            last_dates[c], last_close[c], last_rows[c] = t
    print(f"已读取 {len(last_dates)} 只的尾部状态", flush=True)

    print("[1/2] 扫描新快照（重叠日 + 新行）...", flush=True)
    overlap, new_rows = scan_overlap_and_new(src, set(last_dates), last_dates)

    append_ok, reanchor, undecidable = [], [], []
    for c in sorted(last_dates):
        oc = overlap.get(c)
        if oc is None or last_close[c] <= 0:
            undecidable.append(c)
        elif abs(oc / last_close[c] - 1.0) <= args.tolerance:
            append_ok.append(c)
        else:
            reanchor.append(c)
    n_new = sum(len(v) for v in new_rows.values())
    print(f"      锚定一致可追加 : {len(append_ok):>5} 只（新行 {n_new:,} 条）")
    print(f"      锚定已变需替换 : {len(reanchor):>5} 只")
    print(f"      无法判定(不动) : {len(undecidable):>5} 只", flush=True)

    if args.dry_run:
        print("\n--dry-run：未做任何写入。", flush=True)
        for c in reanchor[:5]:
            print(f"      替换样例 {c}: 旧收盘 {last_close[c]} vs 新快照 {overlap[c]}", flush=True)
        return 0

    print("[2/2] 执行写入 ...", flush=True)
    changed: List[Dict[str, Any]] = []
    for c in append_ok:
        rows = new_rows.get(c) or []
        if not rows:
            continue
        p = dataset / "stocks" / f"{c}.csv"
        append_rows(p, [to_out_row(r, c) for r in sorted(rows, key=lambda x: x["date"])])
        last_dates[c] = max(r["date"] for r in rows)

    replace_series = collect_full_series(src, set(reanchor)) if reanchor else {}
    for c in reanchor:
        rows = sorted(replace_series.get(c) or [], key=lambda x: x["date"])
        if not rows:
            continue
        p = dataset / "stocks" / f"{c}.csv"
        write_rows(p, [to_out_row(r, c) for r in rows], header=OUT_COLUMNS)
        last_dates[c] = rows[-1]["date"]

    # 元数据与 pool 同步（含 sha256）
    touched = [c for c in append_ok if new_rows.get(c)] + reanchor
    for c in touched:
        p = dataset / "stocks" / f"{c}.csv"
        mp = dataset / "stocks" / f"{c}.metadata.json"
        t = tail_of_csv(p)
        if t is None:
            continue
        last_dates[c], last_rows[c] = t[0], t[2]
        meta: Dict[str, Any] = {}
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}
        meta.update({
            "strict": True, "sha256": sha256_file(p), "rows": t[2], "code": c,
            "adjusted": True,
            "adjusted_mode": f"qfq(增量更新于 {datetime.now():%Y-%m-%d})",
            "last_date": t[0],
            "note": "增量更新；锚定一致性由重叠日校验保证（见 scripts/update_certified_dataset.py）",
        })
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        changed.append({"code": c, "action": "append" if c in append_ok else "reanchor",
                        "rows": t[2], "last_date": t[0]})

    pool_meta: Dict[str, Dict[str, str]] = {}
    pool_path = next((dataset / n for n in POOL_CANDIDATES if (dataset / n).exists()), None)
    if pool_path is not None:
        with pool_path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            fields = list(reader.fieldnames or [])
            for r in reader:
                c = r["code"].zfill(6)
                if c in last_dates:
                    r["last_date"] = last_dates[c]
                    r["rows"] = str(last_rows.get(c, r.get("rows", "")))
                pool_meta[c] = r
        with pool_path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for c in sorted(pool_meta):
                w.writerow(pool_meta[c])

    calendar: List[str] = []
    bm = dataset / "benchmark.csv"
    if bm.exists():
        with bm.open(encoding="utf-8-sig", newline="") as fh:
            calendar = sorted(r["date"] for r in csv.DictReader(fh))
    pit = extend_pit(dataset, pool_meta, calendar) if pool_meta else {"updated": False}

    log = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": str(dataset), "src_qfq": str(src),
        "tolerance": args.tolerance,
        "counts": {"append": len(append_ok), "reanchor": len(reanchor),
                   "undecidable": len(undecidable), "new_rows": n_new},
        "undecidable_codes": undecidable,
        "changed": changed,
        "pit": pit,
        "not_updated": ["不复权源", "复权因子事件", "停牌区间"],
        "not_updated_reason": "依赖全量重扫；需这三项更新时请重跑 build_certified_dataset_v2.py",
    }
    dest = Path(args.out_log) if args.out_log else dataset / "update_log.json"
    dest.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已更新 {len(changed)} 只；PIT 新增 {pit.get('days_added', 0)} 个交易日", flush=True)
    print(f"更新日志: {dest}", flush=True)
    if undecidable:
        print(f"⚠ {len(undecidable)} 只无法判定锚定一致性（未改动，已记入日志）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
