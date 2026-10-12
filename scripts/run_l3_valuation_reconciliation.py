# -*- coding: utf-8 -*-
"""L3 估值历史的**抽样对账**（设计文档规定的「接入前必过闸门」）。

对账对象：**baostock 回溯估值** vs **本项目 `pit_fundamentals`**。

## 为什么要对账

设计文档 §九 明令：「不因为『源给了回溯窗口』就默认其 PIT 正确 —— **回溯值同样要对账**」。
L3 的价值全在于「能否用于历史回测」，而这取决于**源的每日估值是否只用了当时已公开的信息**。

## 口径要点（**这里最容易出错**）

| 项 | 本项目 v3 | baostock |
|---|---|---|
| 价格 | **qfq 前复权**（锚定 2026-09-11） | `adjustflag='3'` **不复权** |

→ **绝不能直接比 `pb` / `pe_ttm`**（会掺入复权因子，差异全是假信号）。
→ 改为比「**隐含分母**」：

```text
baostock 隐含 bps     = close / pbMRQ      ←→  我们的 bps
baostock 隐含 ttm_eps = close / peTTM      ←→  我们的 ttm_eps_as_of()
```

## 三项检验

1. **bps 一致性** —— 分母是否同源（净资产口径）
2. **ttm_eps 一致性** —— TTM 口径是否可比
3. **⚠️ PIT 对齐检验**（最关键）—— 以**巨潮实际披露日** `D` 为事件点，看 baostock 的隐含 EPS
   在 `D` 前后是否切换（`o_*` = 我们的值，`b_*` = baostock 的值）：

   | 分类 | 判据 | 含义 |
   |---|---|---|
   | `aligned` | `b_post != b_pre` | 在披露日切换 → **PIT 正确** |
   | **`early`** | `b_post == b_pre ≈ o_post` | **披露日之前就已用上新值 → 疑似前视** ⚠️ |
   | `late` | `b_post == b_pre ≈ o_pre` | 未在披露日切换 → 偏晚（保守） |
   | `no_event` | `o_pre == o_post` | 我们的值在该披露日未变（该期未改变 TTM），不构成检验 |
   | `no_data` | 任一侧缺值 | 无法判定 |

⚠️ **本脚本的局限（如实声明）**：只在**有披露日**的 `(code, period)` 上检验；
样本为**抽样**而非全市场；`early` 只是**嫌疑**，须人工核对具体披露事件后才能定性。

⚠️⚠️ **`early` 的一个已知误判源（2026-10-12 补）**：本脚本把 `disclosure_dates.jsonl`
的日期当作「**首次公开日**」，但该数据来自东财 `stock_yjbb_em`，记录的是 **A 股披露日**。
**对 A+H 公司，港股业绩公告通常早于 A 股年报 4~8 周** ——
例：688981（中芯国际）**2024-02-06** 已在官网发布 2023Q4/年度业绩，
而东财 A 股披露日为 **2024-03-29**；baostock 在 **2024-02-07** 切换 →
**baostock 正确，本脚本会把它误标为 `early`**。
→ **命中 `early` 时，必须先排除「该股为 A+H 且港股已先行公告」，才能定性为前视。**
（本脚本暂未自动识别 A+H，**须人工核对**。）
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pit.pit_fundamentals import (  # noqa: E402
    PitFundamentals,
    load_disclosures,
    load_records,
)

#: 待检验的报告期（都已过披露日，且跨年报/半年报/三季报）
PERIODS = ("2023-06-30", "2023-09-30", "2023-12-31", "2024-06-30",
           "2024-09-30", "2024-12-31", "2025-06-30", "2025-09-30")

Row = Tuple[str, Optional[float], Optional[float], Optional[float]]  # date, close, peTTM, pbMRQ


def _f(v: Any) -> Optional[float]:
    s = str(v or "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fetch(symbol: str, start: str, end: str) -> List[Row]:
    """取 (date, close, peTTM, pbMRQ)。``adjustflag='3'`` = **不复权**。"""
    import baostock as bs

    rs = bs.query_history_k_data_plus(
        symbol, "date,close,peTTM,pbMRQ", start_date=start, end_date=end,
        frequency="d", adjustflag="3")
    if rs.error_code != "0":
        raise RuntimeError(f"{symbol}: {rs.error_code} {rs.error_msg}")
    out: List[Row] = []
    while rs.next():
        r = rs.get_row_data()
        out.append((r[0], _f(r[1]), _f(r[2]), _f(r[3])))
    return out


def _prev_day(day: str) -> str:
    """``D`` 的前一**自然日**（用于取「披露前」的观测）。"""
    import datetime as dt

    return (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()


def _last_le(rows: List[Row], day: str) -> Optional[Row]:
    """``day`` 当日或之前**最近**的一条（无则 ``None``）。"""
    cands = [r for r in rows if r[0] <= day]
    return cands[-1] if cands else None


def _first_ge(rows: List[Row], day: str) -> Optional[Row]:
    """``day`` 当日或之后**最近**的一条（无则 ``None``）。"""
    cands = [r for r in rows if r[0] >= day]
    return cands[0] if cands else None


def _rel(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """相对差 ``|a-b| / |b|``；任一为空或 ``b == 0`` 返回 ``None``。"""
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b)


def _summary(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    return {
        "n": len(vals),
        "median": round(statistics.median(vals), 6),
        "p90": round(s[min(len(s) - 1, int(len(s) * 0.9))], 6),
        "max": round(s[-1], 6),
        "share_le_1pct": round(sum(1 for x in vals if x <= 0.01) / len(vals), 4),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="L3 估值历史抽样对账")
    ap.add_argument("--dataset", default="D:/tdx_dataset_v3")
    ap.add_argument("--codes", default="", help="逗号分隔的 6 位代码；留空则自动均匀抽样")
    ap.add_argument("--n", type=int, default=24, help="自动抽样的标的数")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    ds = Path(args.dataset)
    recs = load_records(ds / "fundamentals.jsonl")
    disc = load_disclosures(ds / "disclosure_dates.jsonl")
    pf = PitFundamentals(recs, disc)
    print(f"基本面 {len(recs):,} 条 · 披露日 {len(disc):,} 条", flush=True)

    if args.codes:
        codes = [c.strip().zfill(6) for c in args.codes.split(",") if c.strip()]
    else:
        pool = sorted(p.stem for p in (ds / "stocks").glob("*.csv") if p.stem.isdigit())
        step = max(1, len(pool) // args.n)
        codes = [pool[i * step] for i in range(args.n) if i * step < len(pool)]
    print(f"抽样 {len(codes)} 只 · 窗口 {args.start}~{args.end}", flush=True)

    import baostock as bs

    bs.login()
    data: Dict[str, List[Row]] = {}
    failed: List[str] = []
    try:
        for i, c in enumerate(codes, 1):
            pref = "sh" if c[0] in "569" else ("bj" if c[0] in "48" else "sz")
            try:
                data[c] = _fetch(f"{pref}.{c}", args.start, args.end)
            except Exception as exc:      # 单只失败不拖垮整批，但**必须记录**
                failed.append(f"{c}: {exc}")
            if i % 8 == 0:
                print(f"    ... {i}/{len(codes)}", flush=True)
    finally:
        bs.logout()
    print(f"取数成功 {len(data)} 只 · 失败 {len(failed)} 只", flush=True)

    bps_rels: List[float] = []
    eps_rels: List[float] = []
    eps_signed: List[float] = []
    pit: Dict[str, int] = {"aligned": 0, "early": 0, "late": 0, "no_event": 0, "no_data": 0}
    early_examples: List[Dict[str, Any]] = []

    for c, rows in data.items():
        for d, close, pe, pb in rows:
            rec = pf.as_of(c, d)
            if rec is None:
                continue
            # ① bps：隐含 = close / pbMRQ
            r_bps = _rel((close / pb) if (close and pb and pb > 0) else None, _f(rec.get("bps")))
            if r_bps is not None:
                bps_rels.append(r_bps)
            # ② ttm_eps：隐含 = close / peTTM
            eps_b = (close / pe) if (close and pe and pe > 0) else None
            eps_o = pf.ttm_eps_as_of(c, d)
            r_eps = _rel(eps_b, eps_o)
            if r_eps is not None:
                eps_rels.append(r_eps)
            if eps_b is not None and eps_o:
                eps_signed.append((eps_b - eps_o) / eps_o)

        # ③ PIT 对齐检验
        for p in PERIODS:
            D = disc.get((c, p))
            if not D:
                continue
            o_pre = pf.ttm_eps_as_of(c, _prev_day(D))
            o_post = pf.ttm_eps_as_of(c, D)
            r_pre = _last_le(rows, _prev_day(D))
            r_post = _first_ge(rows, D)
            b_pre_eps = ((r_pre[1] / r_pre[2]) if (r_pre and r_pre[1] and r_pre[2]) else None)
            b_post_eps = ((r_post[1] / r_post[2]) if (r_post and r_post[1] and r_post[2]) else None)
            if b_pre_eps is None or b_post_eps is None:
                pit["no_data"] += 1
                continue
            if o_pre == o_post:
                pit["no_event"] += 1
                continue
            if abs(b_post_eps - b_pre_eps) > 1e-9:
                pit["aligned"] += 1
            elif o_post is not None and abs(b_pre_eps - o_post) <= abs(o_post) * 0.01:
                pit["early"] += 1
                if len(early_examples) < 8:
                    early_examples.append({
                        "code": c, "period": p, "disclose": D,
                        "b_pre_eps": round(b_pre_eps, 4),
                        "b_post_eps": round(b_post_eps, 4),
                        "ours_post": round(o_post, 4),
                    })
            else:
                pit["late"] += 1

    total = sum(v for k, v in pit.items() if k != "no_data")
    res: Dict[str, Any] = {
        "sample_codes": len(data),
        "failed_codes": failed,
        "window": [args.start, args.end],
        "bps_relative_diff": _summary(bps_rels),
        "eps_relative_diff": _summary(eps_rels),
        "eps_signed_diff_median": (round(statistics.median(eps_signed), 6) if eps_signed else None),
        "pit_alignment": pit,
        "pit_early_share": (round(pit["early"] / total, 4) if total else None),
        "pit_aligned_share": (round(pit["aligned"] / total, 4) if total else None),
        "early_examples": early_examples,
        "caveats": [
            "PIT 检验仅覆盖有巨潮披露日的 (code, period) 对；样本为抽样而非全市场",
            "early 只是嫌疑，须人工核对具体披露事件后才能定性",
            "baostock 用不复权价、本项目 v3 用 qfq —— 故只比隐含分母，不比比率本身",
        ],
    }
    print()
    print("=" * 96)
    print(f"bps   相对差: {_summary(bps_rels)}")
    print(f"eps   相对差: {_summary(eps_rels)}  （有符号中位 "
          f"{res['eps_signed_diff_median']}；正=baostock 更高）")
    print(f"PIT   对齐 : {pit}   aligned {res['pit_aligned_share']}  early {res['pit_early_share']}")
    for e in early_examples:
        print(f"  early? {e}")
    print("=" * 96)
    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with outp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(res, ensure_ascii=False, indent=2))
        print(f"已写 {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
