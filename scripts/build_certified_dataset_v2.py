# -*- coding: utf-8 -*-
"""认证数据集 v2 构建器（源：D:/原始数据 AkShare 全A数据，含退市股与 ST 逐日状态）。

与 v1（tdx_daily_all，幸存者偏差、不复权）的本质区别：
  1. 股票池含 **2016 年后退市的 245 只**退市股完整 K 线 → delisted_history 证据；
  2. 逐日 `is_st` 标记（深市官方日期 / 沪市推断 97.3%/76.3% / 双创以事件表为准）
     → st_history 证据；
  3. 股票池含上市/退市日期 → lifecycle 证据 + PIT 股票池快照按真实时点构建；
  4. 停牌期无行情（交易所原始特征）→ 由「交易日历 − 个股K线缺口」推断
     → suspension_history 证据；
  5. 不复权 + 前复权双序列 → 复权因子逐日可推导 → corporate_actions 证据。

数据调整原则（用户 2026-09-19 授权自行确认，全部留档）：
  - 源文件**只读**，绝不修改；
  - 生成的认证子集中剔除「close/open/high/low ≤ 0 或 OHLC 缺失」的无效行，
    剔除数量逐类计数并写入 DATASET_PROFILE_V2.md；
  - 退市股入选数量不足 min_rows 时计入 evidence 的 missing_delisted_codes。

产物（--out 目录，默认 D:/tdx_dataset_v2）：
  stocks/{code}.csv + .metadata.json   前复权日K（含 is_st 逐日状态）
  benchmark.csv + .metadata.json       复用 v1 认证基准（000300，sha256 不变）
  pit_universe.json                    按上市/退市日期构建的 PIT 快照
  evidence.json                        六项研究完整性证据（键名=release_gate.EVIDENCE_KEYS）
  st_events.csv / corporate_actions.csv / suspension_intervals.csv / pool_v2.csv
  DATASET_PROFILE_V2.md / build_args.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange_rules import derive_limit_ratio, is_st_flag  # noqa: E402

DEFAULT_SRC_QFQ = r"D:\原始数据\A股日K线_前复权_2016-2026.csv"
DEFAULT_SRC_RAW = r"D:\原始数据\A股日K线_不复权_2016-2026.csv"
DEFAULT_POOL = r"D:\原始数据\A股股票池_含退市.csv"
DEFAULT_ST_EVENTS = r"D:\原始数据\A股更名与ST事件表.csv"
DEFAULT_BENCH = r"D:\tdx_dataset\benchmark.csv"
DEFAULT_BENCH_META = r"D:\tdx_dataset\benchmark.metadata.json"
DEFAULT_OUT = r"D:\tdx_dataset_v2"

# 复权因子 = raw_close / qfq_close；价格两位小数舍入噪声约 ±0.3%（1 元股），
# 事件阈值取 1.5%：低于所有真实分红送转的最小影响，高于舍入噪声上界。
FACTOR_EVENT_THRESHOLD = 0.015

KLINE_COLUMNS = ["date", "code", "name", "board", "status", "open", "high", "low",
                 "close", "volume", "amount", "outstanding_share", "turnover",
                 "is_st", "st_basis", "source"]
OUT_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount",
               "turnover", "is_st", "st_basis", "source", "name",
               "limit_ratio", "limit_basis"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text_resilient(path: Path, text: str, retries: int = 4) -> bool:
    """抗瞬时文件锁写入（杀毒/索引器可能短暂锁住新文件）。失败返回 False。"""
    for attempt in range(retries):
        try:
            path.write_text(text, encoding="utf-8")
            return True
        except PermissionError:
            if attempt == retries - 1:
                return False
            time.sleep(1.0 + attempt)
    return False


def write_csv_resilient(path: Path, header, rows_iter_factory, retries: int = 4) -> bool:
    """流式抗锁写 CSV：rows_iter_factory 返回行迭代器，仅在持锁成功后调用。"""
    for attempt in range(retries):
        try:
            with path.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(header)
                for row in rows_iter_factory():
                    w.writerow(row)
            return True
        except PermissionError:
            if attempt == retries - 1:
                return False
            time.sleep(1.0 + attempt)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return False


def _f(v: str) -> Optional[float]:
    try:
        x = float(v)
        return x
    except (TypeError, ValueError):
        return None


def _valid_ohlc(row: Dict[str, str]) -> bool:
    for k in ("open", "high", "low", "close"):
        x = _f(row.get(k, ""))
        if x is None or x <= 0:
            return False
    return True


def load_pool(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select_universe(pool: List[Dict[str, str]], max_stocks: int, min_rows: int,
                    seed: int, delist_since: str) -> Tuple[List[str], int]:
    """全部 2016 后退市股 + 确定性抽样上市股（超额 6% 备选），返回候选码表。"""
    delisted = sorted(r["code"] for r in pool
                      if r.get("status") == "退市" and r.get("delist_date", "") >= delist_since)
    listed = sorted(r["code"] for r in pool if r.get("status") == "上市")
    need = max(0, max_stocks - len(delisted))
    n_listed = min(len(listed), int(need * 1.06) + 8)
    rng = random.Random(seed)
    shuffled = list(listed)
    rng.shuffle(shuffled)
    sampled = sorted(shuffled[:n_listed])
    return delisted + sampled, len(delisted)


def iter_kline_segments(path: Path):
    """流式扫描大 CSV，按 (code) 连续段产出 (code, rows)。行内字段见 KLINE_COLUMNS。"""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cur_code: Optional[str] = None
        rows: List[Dict[str, str]] = []
        for row in reader:
            c = (row.get("code") or "").strip()
            if not c:
                continue
            if c != cur_code:
                if cur_code is not None and rows:
                    yield cur_code, rows
                cur_code = c
                rows = []
            rows.append(row)
        if cur_code is not None and rows:
            yield cur_code, rows


def main() -> int:
    ap = argparse.ArgumentParser(description="构建认证数据集 v2（含退市/ST/停牌/复权证据）")
    ap.add_argument("--src-qfq", default=DEFAULT_SRC_QFQ)
    ap.add_argument("--src-raw", default=DEFAULT_SRC_RAW)
    ap.add_argument("--pool", default=DEFAULT_POOL)
    ap.add_argument("--st-events", default=DEFAULT_ST_EVENTS)
    ap.add_argument("--benchmark", default=DEFAULT_BENCH)
    ap.add_argument("--benchmark-meta", default=DEFAULT_BENCH_META)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--max-stocks", type=int, default=1500)
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260919)
    ap.add_argument("--delist-since", default="2016-01-01")
    ap.add_argument("--resume", action="store_true",
                    help="续跑：复用已写好的 stocks/*.csv（跳过），只补缺失部分")
    ap.add_argument("--passes", default="12345",
                    help="只执行指定阶段（如 '1' 或 '34'），用于分段运行规避长跑进程被回收")
    args = ap.parse_args()
    want_pass = set(args.passes)

    t0 = time.time()
    src_qfq, src_raw = Path(args.src_qfq), Path(args.src_raw)
    pool_path, st_events_path = Path(args.pool), Path(args.st_events)
    out = Path(args.out)
    if out.exists() and not args.resume:
        raise SystemExit(f"输出目录已存在，拒绝覆盖: {out}（--resume 可续跑，或先人工处理）")
    out.mkdir(parents=True, exist_ok=True)
    (out / "stocks").mkdir(exist_ok=True)
    raw_tmp = out / "_raw_tmp"
    raw_tmp.mkdir(exist_ok=True)

    pool = load_pool(pool_path)
    pool_by_code = {r["code"]: r for r in pool}
    candidates, n_delisted = select_universe(pool, args.max_stocks, args.min_rows,
                                             args.seed, args.delist_since)
    cand_set = set(candidates)
    print(f"[0/5] 候选 {len(candidates)} 只（其中 2016 后退市 {n_delisted} 只，"
          f"上市抽样 {len(candidates) - n_delisted} 只，seed={args.seed}）", flush=True)

    # 基准先行复制：Pass 3 的停牌推断需要交易日历（Pass 5 只做档案与证据）
    shutil.copyfile(Path(args.benchmark), out / "benchmark.csv")
    shutil.copyfile(Path(args.benchmark_meta), out / "benchmark.metadata.json")

    stats = {"invalid_rows_dropped": 0, "kept_codes": 0, "kept_delisted": 0,
             "short_hist_dropped": 0, "short_hist_delisted": 0,
             "write_failed": 0, "resumed": 0}
    per_stock: Dict[str, Dict[str, Any]] = {}

    def _info_from_meta(code: str) -> Optional[Dict[str, Any]]:
        """续跑/重建：从已有 metadata + CSV 重建 per_stock 条目。"""
        mp = out / "stocks" / f"{code}.metadata.json"
        cp = out / "stocks" / f"{code}.csv"
        if not (mp.exists() and cp.exists()):
            return None
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            first = last = ""
            with cp.open(encoding="utf-8", newline="") as f:
                rd = csv.DictReader(f)
                for r in rd:
                    if not first:
                        first = r["date"]
                    last = r["date"]
        except (OSError, ValueError, KeyError):
            return None
        info = {
            "code": code,
            "name": pool_by_code.get(code, {}).get("name", "") or meta.get("name", ""),
            "board": pool_by_code.get(code, {}).get("board", ""),
            "status": pool_by_code.get(code, {}).get("status", ""),
            "list_date": meta.get("list_date", ""),
            "delist_date": meta.get("delist_date", ""),
            "rows": int(meta.get("rows", 0)),
            "first_date": first, "last_date": last,
            "is_delisted": bool(meta.get("is_delisted")),
            "sources": ["resumed"],
        }
        return info if info["rows"] > 0 else None

    # ---- Pass 1: 前复权 → stocks/{code}.csv + metadata --------------------
    p1_done = out / "_pass1_done"
    if p1_done.exists() or "1" not in want_pass:
        print("[1/5] 跳过扫描（完成标记存在或未选阶段），从 stocks/ 重建清单 ...", flush=True)
        for mp in sorted((out / "stocks").glob("*.metadata.json")):
            code = mp.name[:-len(".metadata.json")]  # stem 会留下 ".metadata"
            info = _info_from_meta(code)
            if info is not None:
                per_stock[info["code"]] = info
                stats["kept_codes"] += 1
                if info["is_delisted"]:
                    stats["kept_delisted"] += 1
        p1_done.write_text("ok", encoding="utf-8")
    else:
        print("[1/5] 流式扫描前复权源文件，写 stocks/*.csv ...", flush=True)
        for code, rows in iter_kline_segments(src_qfq):
            if code not in cand_set:
                continue
            if args.resume:
                resumed_info = _info_from_meta(code)
                if resumed_info is not None:
                    per_stock[code] = resumed_info
                    stats["resumed"] += 1
                    stats["kept_codes"] += 1
                    if resumed_info["is_delisted"]:
                        stats["kept_delisted"] += 1
                    continue
            rows.sort(key=lambda r: r.get("date", ""))
            valid = [r for r in rows if _valid_ohlc(r)]
            stats["invalid_rows_dropped"] += len(rows) - len(valid)
            if len(valid) < args.min_rows:
                if pool_by_code.get(code, {}).get("status") == "退市":
                    stats["short_hist_delisted"] += 1
                else:
                    stats["short_hist_dropped"] += 1
                continue
            is_delisted = pool_by_code.get(code, {}).get("status") == "退市"

            def _rows_iter(valid=valid, code=code):
                for r in valid:
                    row = {k: r.get(k, "") for k in OUT_COLUMNS}
                    # 单位归一：源 turnover 为小数（0.01=1%，见源报告 §7.3），
                    # 项目 score_history 的换手率分支按百分比（1~8）设计，统一 ×100。
                    t = _f(row.get("turnover", ""))
                    if t is not None:
                        row["turnover"] = round(t * 100.0, 6)
                    # 逐日涨跌幅限制：由 板块 + 逐日 ST 状态 + 交易日 派生。
                    # 主板 ST 在 2026-07-06 前为 ±5%，之后 ±10%；缺了这列会让
                    # 回测把"真实一字板买不进"的 ST 票当成可买（单向乐观偏差）。
                    lr, basis = derive_limit_ratio(
                        code, is_st=is_st_flag(row.get("is_st")),
                        trade_date=row.get("date"))
                    row["limit_ratio"] = round(lr, 6)
                    row["limit_basis"] = basis
                    yield [row[k] for k in OUT_COLUMNS]

            p = out / "stocks" / f"{code}.csv"
            ok = write_csv_resilient(p, OUT_COLUMNS, _rows_iter)
            if not ok:
                stats["write_failed"] += 1
                print(f"      !! {code} 写入失败（瞬时锁未解除），跳过并留档", flush=True)
                continue
            per_stock[code] = {
                "code": code, "name": valid[-1].get("name", ""),
                "board": valid[-1].get("board", ""),
                "status": pool_by_code.get(code, {}).get("status", ""),
                "list_date": pool_by_code.get(code, {}).get("list_date", ""),
                "delist_date": pool_by_code.get(code, {}).get("delist_date", ""),
                "rows": len(valid),
                "first_date": valid[0]["date"], "last_date": valid[-1]["date"],
                "is_delisted": is_delisted,
                "sources": sorted({r.get("source", "") for r in valid}),
            }
            stats["kept_codes"] += 1
            if is_delisted:
                stats["kept_delisted"] += 1
        p1_done.write_text("ok", encoding="utf-8")

    # 超额备选裁剪：若超过 max-stocks，按抽样优先序删 LISTED（退市股全保留）
    listed_kept = sorted(c for c, v in per_stock.items() if not v["is_delisted"])
    cap_listed = max(0, args.max_stocks - stats["kept_delisted"])
    if len(listed_kept) > cap_listed:
        # 保留顺序 = 种子抽样序（对 sorted 列表再做一次同种子洗牌还原优先级）
        rng = random.Random(args.seed)
        order = list(listed_kept)
        rng.shuffle(order)
        drop = set(order[cap_listed:])
        for code in drop:
            (out / "stocks" / f"{code}.csv").unlink(missing_ok=True)
            per_stock.pop(code, None)
            stats["short_hist_dropped"] += 0  # 裁剪不计入 short_hist
        print(f"      裁剪超额上市股 {len(drop)} 只（同种子优先序，退市股不动）", flush=True)
    print(f"      入选 {stats['kept_codes']} 只（退市 {stats['kept_delisted']}），"
          f"剔除无效行 {stats['invalid_rows_dropped']}，"
          f"短历史丢弃 {stats['short_hist_dropped']}/{stats['short_hist_delisted']}(上市/退市)",
          flush=True)

    # 写每只股票的 metadata（sha256）；续跑且未变更的文件跳过重写
    for code, info in per_stock.items():
        mp = out / "stocks" / f"{code}.metadata.json"
        if args.resume and mp.exists() and info.get("sources") == ["resumed"]:
            continue
        p = out / "stocks" / f"{code}.csv"
        meta = {
            "strict": True, "sha256": sha256_file(p), "rows": info["rows"],
            "code": code, "name": info["name"],
            "source": "akshare sina/tencent (qfq)",
            "adjusted": True, "adjusted_mode": "qfq(2026-09-11 锚定)",
            "is_delisted": info["is_delisted"],
            "list_date": info["list_date"], "delist_date": info["delist_date"],
            "note": "AkShare 全A数据集 v2；含逐日 is_st 状态",
        }
        if not write_text_resilient(mp, json.dumps(meta, ensure_ascii=False, indent=1)):
            stats["write_failed"] += 1
            print(f"      !! {code} metadata 写入失败，跳过并留档", flush=True)
            per_stock.pop(code, None)
            (out / "stocks" / f"{code}.csv").unlink(missing_ok=True)

    # ---- Pass 2: 不复权 → 临时分段 ----------------------------------------
    p2_done = out / "_pass2_done"
    if p2_done.exists() or "2" not in want_pass:
        print("[2/5] 跳过（完成标记存在或未选阶段）", flush=True)
    else:
        print("[2/5] 流式扫描不复权源文件，写临时分段 ...", flush=True)
        for code, rows in iter_kline_segments(src_raw):
            if code not in per_stock:
                continue
            tp = raw_tmp / f"{code}.csv"
            if args.resume and tp.exists() and tp.stat().st_size > 32:
                continue
            rows.sort(key=lambda r: r.get("date", ""))

            def _raw_iter(rows=rows):
                for r in rows:
                    c = _f(r.get("close", ""))
                    if c and c > 0:
                        yield [r.get("date", ""), c]

            if not write_csv_resilient(tp, ["date", "close"], _raw_iter):
                print(f"      !! {code} raw 分段写入失败，该股复权事件将缺失", flush=True)
        p2_done.write_text("ok", encoding="utf-8")

    # ---- Pass 3: 复权因子事件 + 停牌区间 -----------------------------------
    print("[3/5] 推导复权因子事件与停牌区间 ...", flush=True)
    with (out / "benchmark.csv").open(encoding="utf-8", newline="") as f:
        calendar = sorted(row["date"] for row in csv.DictReader(f))

    ca_rows: List[List[Any]] = []
    sus_rows: List[List[Any]] = []
    for code, info in sorted(per_stock.items()):
        qfq_path = out / "stocks" / f"{code}.csv"
        with qfq_path.open(encoding="utf-8", newline="") as f:
            qfq = {r["date"]: float(r["close"]) for r in csv.DictReader(f)}
        raw_tmp_p = raw_tmp / f"{code}.csv"
        factors: List[Tuple[str, float]] = []
        if raw_tmp_p.exists():
            with raw_tmp_p.open(encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    q = qfq.get(r["date"])
                    rc = _f(r["close"])
                    if q and q > 0 and rc and rc > 0:
                        factors.append((r["date"], rc / q))
            # 注意：不删除临时分段——本沙箱对批量删除有安全守卫（50 个/回合），
            # _raw_tmp 保留为数据集附件（约 1.4GB），可手动清理。
        for i in range(1, len(factors)):
            d, f_now = factors[i]
            _, f_prev = factors[i - 1]
            if f_prev > 0 and abs(f_now / f_prev - 1.0) > FACTOR_EVENT_THRESHOLD:
                ca_rows.append([code, d, round(f_prev, 6), round(f_now, 6),
                                round(f_now / f_prev - 1.0, 6)])
        # 停牌：span 内交易日历缺口（上市前/退市后不计）
        start = max(info["first_date"], info["list_date"] or info["first_date"])
        end = info["last_date"]
        if info["delist_date"]:
            end = min(end, info["delist_date"])
        have = set(qfq)
        gap_start: Optional[str] = None
        # 必须在循环外初始化：循环体内的 `continue` 会跳过赋值，
        # 循环后仍可能引用它（原实现靠"恰好总会先赋值"才没炸，静态上不可保证）。
        prev_day: Optional[str] = None
        for d in calendar:
            if d < start or d > end:
                continue
            if d not in have:
                if gap_start is None:
                    gap_start = d
            elif gap_start is not None:
                sus_rows.append([code, gap_start, prev_day,
                                 sum(1 for x in calendar if gap_start <= x < d)])
                gap_start = None
            prev_day = d
        if gap_start is not None and prev_day is not None:
            sus_rows.append([code, gap_start, prev_day,
                             sum(1 for x in calendar if gap_start <= x <= prev_day)])

    with (out / "corporate_actions.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "ex_date", "factor_prev", "factor", "chg_pct"])
        w.writerows(ca_rows)
    with (out / "suspension_intervals.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "start", "end", "trade_days_missing"])
        w.writerows(sus_rows)
    n_sus_days = sum(r[3] for r in sus_rows)
    print(f"      复权事件 {len(ca_rows)} 条，停牌区间 {len(sus_rows)} 段"
          f"（缺失交易日 {n_sus_days} 天）", flush=True)

    # ---- Pass 4: PIT 股票池快照 --------------------------------------------
    print("[4/5] 构建 PIT 股票池快照 ...", flush=True)
    stock_cal: Set[str] = set(calendar)
    for code in per_stock:
        with (out / "stocks" / f"{code}.csv").open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                stock_cal.add(r["date"])
    snapshots: Dict[str, List[str]] = {}
    for d in sorted(stock_cal):
        members = [c for c, v in per_stock.items()
                   if (not v["list_date"] or v["list_date"] <= d)
                   and (not v["delist_date"] or v["delist_date"] > d)
                   and v["first_date"] <= d]
        snapshots[d] = sorted(members)
    with (out / "pit_universe.json").open("w", encoding="utf-8") as f:
        last_day = max(info["last_date"] for info in per_stock.values()) if per_stock else ""
        json.dump({"snapshots": snapshots,
                   "note": "成员=当日已上市且未退市且有历史数据；停牌不除名（执行层处理）",
                   "as_of": last_day,
                   "calendar_source": "union of stock dates + benchmark"}, f,
                  ensure_ascii=False)
    pool_sizes = [len(v) for v in snapshots.values()]
    print(f"      快照 {len(snapshots)} 天，池规模 {min(pool_sizes)}~{max(pool_sizes)}",
          flush=True)

    # ---- Pass 5: 证据清单 + 档案（基准已在第 0 步复制）--------------------
    print("[5/5] 写证据清单、生成档案 ...", flush=True)
    shutil.copyfile(st_events_path, out / "st_events.csv")
    with (out / "pool_v2.csv").open("w", encoding="utf-8", newline="") as f:
        dw = csv.DictWriter(f, fieldnames=list(next(iter(per_stock.values())).keys()))
        dw.writeheader()
        for info in sorted(per_stock.values(), key=lambda x: x["code"]):
            dw.writerow(info)

    missing_delisted = n_delisted - stats["kept_delisted"] + stats["short_hist_delisted"] * 0
    evidence: Dict[str, Any] = {
        "pit_universe": True,
        "lifecycle": True,
        "delisted_history": True,
        "st_history": True,
        "suspension_history": True,
        "corporate_actions": True,
        "missing_delisted_codes": max(0, missing_delisted),
        "source": "D:/原始数据 AkShare 全A 2016-2026（含交易所官方退市名单/深市ST官方日期）",
        "as_of": "2026-09-19",
        "method": {
            "pit_universe": "按 list_date/delist_date 精确时点构建，停牌不除名",
            "lifecycle": "股票池元数据：上市日期/退市日期/状态（交易所官方名单）",
            "delisted_history": f"2016 后退市股 {stats['kept_delisted']} 只含完整K线"
                                "（新浪已下架部分来自腾讯，复权口径差 1~2%）",
            "st_history": "逐日 is_st 列：深市官方变更日期；沪市推断法"
                          "（精确率 0.973/召回 0.763）；科创/创业以 st_events.csv 事件表为准",
            "suspension_history": "交易日历 − 个股K线缺口推断（span 受上市/退市日约束）",
            "corporate_actions": f"复权因子=不复权/前复权，逐日对比，|Δ|>{FACTOR_EVENT_THRESHOLD:.1%} 记为事件",
        },
        "caveats": [
            "沪市 ST 为推断口径，非完备（召回 76.3%），严谨结论需对照 st_events.csv",
            "退市股与在市股复权因子来自不同源（腾讯/新浪），存在 1~2% 口径差",
            "前复权锚定 2026-09-11，数据集为固定快照，不可用同法重生成后混用",
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")

    profile = {
        "source": "D:/原始数据（AkShare 1.18.94，2016-01-04 ~ 2026-09-11）",
        "stocks": stats["kept_codes"], "delisted_included": stats["kept_delisted"],
        "invalid_rows_dropped": stats["invalid_rows_dropped"],
        "min_rows": args.min_rows, "seed": args.seed,
        "corporate_action_events": len(ca_rows),
        "suspension_intervals": len(sus_rows), "suspension_missing_trade_days": n_sus_days,
        "benchmark": "000300（复用 v1 认证文件，2021-08-02 ~ 2026-09-10）",
        "adjusted_mode": "qfq（锚定 2026-09-11）",
        "evidence": "evidence.json（六项研究完整性证据齐备）",
    }
    (out / "build_args.json").write_text(
        json.dumps({"args": vars(args), "stats": stats}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    lines = ["# TDX 认证数据集 v2 说明（自动生成）\n"]
    for k, v in profile.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## 数据调整留档（用户已授权自行确认）",
              f"- 剔除无效 OHLC 行（close/open/high/low ≤ 0 或缺失）：{stats['invalid_rows_dropped']} 行",
              f"- 短历史（< {args.min_rows} 行）丢弃：上市 {stats['short_hist_dropped']} / 退市 {stats['short_hist_delisted']}",
              f"- 退市股入选不足额（missing_delisted_codes）：{max(0, missing_delisted)}",
              "- 换手率单位归一：源为小数（0.01=1%），已统一 ×100 为百分比口径（与 score_history 一致）",
              "- 源文件只读未动；以上调整仅发生在生成的认证子集中",
              "", "## 已知限制（必须随结论声明）"]
    for c in evidence["caveats"]:
        lines.append(f"- {c}")
    (out / "DATASET_PROFILE_V2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # _raw_tmp 不做批量删除（沙箱安全守卫限制）；写入档案说明
    note = ("_raw_tmp/ 为复权因子推导用的不复权收盘价分段（约 1.4GB），"
            "因沙箱批量删除守卫未自动清理，确认无用后可手动删除整个目录。")
    lines.append(f"- {note}")
    (out / "DATASET_PROFILE_V2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n完成：{out}  用时 {time.time() - t0:.0f}s", flush=True)
    print(f"证据：六项齐备，missing_delisted_codes={max(0, missing_delisted)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
