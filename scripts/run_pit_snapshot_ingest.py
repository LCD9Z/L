# -*- coding: utf-8 -*-
"""PIT 快照采集：L1 上市日/退市日（baostock 零鉴权源）。

对应 ``PIT_SNAPSHOT_DESIGN.md`` 的 **P0**：L1 一次性回填 + 每日校验。

用法::

    python scripts/run_pit_snapshot_ingest.py --root D:/pit_snapshots
    python scripts/run_pit_snapshot_ingest.py --reconcile D:/tdx_dataset_v3

设计纪律（照 ``PIT_SNAPSHOT_DESIGN.md``）：

* **只追加** —— 已落盘日期不覆盖（``--force`` 需留痕）
* **失败即报** —— 自检不过 → 非零退出码，**不得静默通过**
* **阈值事前固定** —— 见 :data:`SELF_CHECK`
* **不复权、不填默认值** —— 缺失即缺失

> ⚠️ ``baostock`` 为**可选依赖**，故惰性导入（与本项目 pytdx/akshare 同约定）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pit.pit_snapshot_store import (  # noqa: E402
    OverwriteRefusedError,
    PitSnapshotStore,
    dataset_meta,
    make_run_id,
    now_cst,
    sha256_of_file,
)

DATASET = "l1_stock_basic"
SOURCE = "baostock"
ENDPOINT = "query_stock_basic"

#: 自检阈值 —— **事前固定**，不得依据结果调整。
SELF_CHECK: Dict[str, float] = {
    "min_rows": 4000.0,          # 股票总数下限（实测 5561）
    "max_missing_rate": 0.01,    # 关键字段缺失率上限
    "max_delist_share": 0.15,    # 退市占比上限（实测 337/5561 ≈ 6.1%）
}


def _fetch_stock_basic() -> List[Dict[str, Any]]:
    """从 baostock 取全部标的基本信息（含已退市）。

    ``type == '1'`` 才是股票；``2``=指数、``4``=可转债、``5``=ETF 一律剔除
    —— **不剔除会让「退市股」统计混入指数**（实测全量 8992 行里 3431 行非股票）。
    """
    try:
        import baostock as bs  # 惰性导入：可选依赖
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise RuntimeError(
            "未安装 baostock（可选依赖）。安装: pip install baostock"
        ) from exc

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_code} {lg.error_msg}")
    try:
        rs = bs.query_stock_basic()
        if rs.error_code != "0":
            raise RuntimeError(f"baostock 查询失败: {rs.error_code} {rs.error_msg}")
        rows: List[Dict[str, Any]] = []
        while rs.next():
            rows.append(dict(zip(rs.fields, rs.get_row_data(), strict=False)))
    finally:
        bs.logout()

    out: List[Dict[str, Any]] = []
    for r in rows:
        if str(r.get("type", "")).strip() != "1":
            continue
        code_full = str(r.get("code", "")).strip()      # sh.600519
        code6 = code_full.split(".")[-1]
        out.append(
            {
                "code": code6,
                "bs_code": code_full,
                "code_name": str(r.get("code_name", "")).strip(),
                "ipo_date": str(r.get("ipoDate", "")).strip(),
                "out_date": str(r.get("outDate", "")).strip(),
                "status": str(r.get("status", "")).strip(),
                "_raw": r,
            }
        )
    return out


def _normalize(records: List[Dict[str, Any]], run_id: str, as_of: str) -> List[Dict[str, str]]:
    """规范化：加双时间轴三字段。``effective_date`` 取上市日（该股事实起点）。"""
    rows: List[Dict[str, str]] = []
    for r in records:
        rows.append(
            {
                "code": r["code"],
                "code_name": r["code_name"],
                "ipo_date": r["ipo_date"],
                "out_date": r["out_date"],
                "status": r["status"],
                "is_delisted": "1" if r["out_date"] else "0",
                "effective_date": r["ipo_date"],
                "as_of": as_of,
                "ingest_run_id": run_id,
            }
        )
    return rows


def _self_check(rows: List[Dict[str, str]]) -> Tuple[List[str], Dict[str, Any]]:
    """自检；返回 (告警/失败清单, 指标字典)。"""
    problems: List[str] = []
    n = len(rows)

    if n < SELF_CHECK["min_rows"]:
        problems.append(
            f"FAIL 行数 {n} < 下限 {SELF_CHECK['min_rows']:.0f}（源可能变更或抓取不完整）"
        )

    dup = PitSnapshotStore.check_primary_key_unique(rows, "code")
    if dup:
        problems.append(f"FAIL 主键 code 重复 {len(dup)} 个，例: {dup[:5]}")

    for f in ("code", "ipo_date", "effective_date", "as_of"):
        rate = PitSnapshotStore.check_missing_rate(rows, f)
        if rate > SELF_CHECK["max_missing_rate"]:
            problems.append(
                f"WARN 字段 {f} 缺失率 {rate:.2%} > 上限 {SELF_CHECK['max_missing_rate']:.2%}"
            )

    n_del = sum(1 for r in rows if r["is_delisted"] == "1")
    share = n_del / n if n else 0.0
    if share > SELF_CHECK["max_delist_share"]:
        problems.append(
            f"WARN 退市占比 {share:.2%} > 上限 {SELF_CHECK['max_delist_share']:.2%}"
        )

    metrics = {"n_rows": n, "n_delisted": n_del, "delist_share": round(share, 6)}
    return problems, metrics


def _reconcile(store: PitSnapshotStore, dataset_dir: str, ingest_date: str) -> Dict[str, Any]:
    """与本地数据集交叉核对：本地缺了哪些**已退市**股票（= 幸存者偏差量化）。"""
    stocks_dir = os.path.join(dataset_dir, "stocks")
    if not os.path.isdir(stocks_dir):
        return {"error": f"目录不存在: {stocks_dir}"}

    local = {
        f[:-4] for f in os.listdir(stocks_dir) if f.endswith(".csv") and f[:-4].isdigit()
    }
    rows = store.records_as_of(DATASET, ingest_date)
    all_codes = {r["code"] for r in rows}
    delisted = {r["code"] for r in rows if r["is_delisted"] == "1"}
    listed = all_codes - delisted

    missing_del = sorted(delisted - local)
    by_year: Dict[str, int] = {}
    out_by_code = {r["code"]: r["out_date"] for r in rows}
    for c in missing_del:
        y = out_by_code.get(c, "")[:4]
        by_year[y] = by_year.get(y, 0) + 1

    return {
        "dataset_dir": dataset_dir,
        "local_total": len(local),
        "src_total": len(all_codes),
        "src_listed": len(listed),
        "src_delisted": len(delisted),
        "local_covers_delisted": len(delisted & local),
        "local_missing_delisted": len(missing_del),
        "delisted_coverage_pct": round(len(delisted & local) / len(delisted) * 100, 2)
        if delisted
        else None,
        "local_only_not_in_src": len(local - all_codes),
        "missing_by_year": dict(sorted(by_year.items())),
        "missing_sample": missing_del[:15],
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PIT 快照采集（L1 上市/退市日）")
    ap.add_argument("--root", default="D:/pit_snapshots", help="快照库根目录")
    ap.add_argument("--date", default=None, help="落盘日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--force", action="store_true", help="覆盖已落盘日期（留痕）")
    ap.add_argument("--reconcile", default=None, help="与本地数据集交叉核对（如 D:/tdx_dataset_v3）")
    ap.add_argument("--out", default=None, help="对账结果 JSON 输出路径")
    args = ap.parse_args(argv)

    ts = now_cst()
    ingest_date = args.date or ts.strftime("%Y-%m-%d")
    run_id = make_run_id(ts)
    as_of = ts.isoformat(timespec="seconds")

    store = PitSnapshotStore(args.root)
    meta = dataset_meta(DATASET)

    print(f"[1/5] 采集 {SOURCE}:{ENDPOINT} ...", flush=True)
    records = _fetch_stock_basic()
    print(f"      股票 {len(records)} 只（含已退市）", flush=True)

    print("[2/5] 规范化（双时间轴）...", flush=True)
    rows = _normalize(records, run_id, as_of)
    print(f"      effective_date = ipo_date · as_of = {as_of} · run_id = {run_id}", flush=True)

    print("[3/5] 自检（阈值事前固定）...", flush=True)
    problems, metrics = _self_check(rows)
    for p in problems:
        print(f"      {p}", flush=True)
    fails = [p for p in problems if p.startswith("FAIL")]
    print(f"      指标: {json.dumps(metrics, ensure_ascii=False)}", flush=True)

    print("[4/5] 落盘（只追加）...", flush=True)
    raw_records = [r["_raw"] for r in records]
    try:
        raw_p = store.append_raw(SOURCE, ENDPOINT, ingest_date, raw_records, force=args.force)
        norm_p = store.write_normalized(DATASET, ingest_date, rows, force=args.force)
        print(f"      raw  : {raw_p}", flush=True)
        print(f"      norm : {norm_p}", flush=True)
    except OverwriteRefusedError as exc:
        print(f"      SKIP {exc}（用 --force 覆盖）", flush=True)
        raw_p = store.raw_path(SOURCE, ENDPOINT, ingest_date)
        norm_p = store.norm_path(DATASET, ingest_date)

    entry: Dict[str, Any] = {
        "ts": as_of,
        "ingest_run_id": run_id,
        "dataset": DATASET,
        "source": SOURCE,
        "endpoint": ENDPOINT,
        "ingest_date": ingest_date,
        "pit_mode": meta["pit_mode"],
        "rows": len(rows),
        "raw_sha256": sha256_of_file(raw_p) if raw_p.exists() else None,
        "norm_sha256": sha256_of_file(norm_p) if norm_p.exists() else None,
        "status": "FAIL" if fails else ("WARN" if problems else "OK"),
        "problems": problems,
        "metrics": metrics,
        "force": bool(args.force),
    }
    store.log_ingest(entry)

    rc = 0
    if fails:
        print("      ❌ 自检 FAIL → 非零退出（不得静默通过）", flush=True)
        rc = 2

    if args.reconcile:
        print(f"[5/5] 与 {args.reconcile} 交叉核对 ...", flush=True)
        rec = _reconcile(store, args.reconcile, ingest_date)
        print(f"      本地 {rec.get('local_total')} 只 · 源 {rec.get('src_total')} 只"
              f"（在市 {rec.get('src_listed')} / 退市 {rec.get('src_delisted')}）", flush=True)
        print(f"      本地覆盖退市股 {rec.get('local_covers_delisted')} 只"
              f"（{rec.get('delisted_coverage_pct')}%）；"
              f"缺 {rec.get('local_missing_delisted')} 只", flush=True)
        print(f"      缺失按年份: {rec.get('missing_by_year')}", flush=True)
        if args.out:
            outp = Path(args.out)
            outp.parent.mkdir(parents=True, exist_ok=True)
            with outp.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, indent=2))
            print(f"      已写 {outp}", flush=True)
    else:
        print("[5/5] 跳过对账（未传 --reconcile）", flush=True)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
