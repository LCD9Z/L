# -*- coding: utf-8 -*-
"""从 baostock 拉取全量日线，用于 H-XSRC 外部源交叉验证。

## 为什么需要独立源

项目全部结论建立在自建数据（通达信 / 自建 v2 / v3）上。
独立审阅指出一个**从未检验**的风险：所有因子共用同一 `close`、
同一**复权路径**、同一 `h=5` 前瞻 → 若复权或前瞻有系统性偏差，
会**同向污染全部因子**，制造「一致」的假象。

baostock 与本项目**无共用环节** → 换源即换掉这三个共用点。
详见 `XSOURCE_VALIDATION_PREREG.md`。

## 实测到的两个 baostock 特性（本脚本据此设计）

1. **`rs.data` 一次给全部行**，`rs.next()` 只是遍历本地数据（0.00s）
   → **直接用 `rs.data`，不用 `next()` 循环**
2. **偶发卡顿**：同一查询时而 0.3s、时而 >100s（实测）
   → 必须**逐只落盘 + 断点续传**，否则会得到不完整样本（进而污染结论）

用法：
    python scripts/fetch_baostock_klines.py --out D:/xs_baostock/klines \\
        --start 2003-01-01
    # 卡顿/中断后重跑同一条命令即续
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from typing import List, Optional

FIELDS = "date,open,high,low,close,volume,amount"
HEADER = "date,open,high,low,close,volume,amount"


def _norm(code: str) -> str:
    """'sh.600519' → 'sh600519'（与主干代码风格一致）。"""
    return code.replace(".", "")


def fetch_one(bs, code: str, start: str, end: str) -> Optional[List[List[str]]]:
    """拉一只票的前复权日线（**分段**，因单次上限 2000 行）。

    实测：`query_history_k_data_plus` 单次最多返回 **2000 行**（约 8 年），
    超过即静默截断（只到 2011 年）→ 必须按 5 年一段循环拼接。

    返回行列表（按日期升序、去重）；异常返回 None。
    """
    import datetime as _dt
    try:
        d0 = _dt.date.fromisoformat(start)
        d1 = _dt.date.fromisoformat(end)
    except ValueError:
        return None
    rows: dict = {}
    cur = d0
    while cur <= d1:
        # 每段 8 年（约 1930 交易日 < 2000 上限）——减少请求数
        seg_end = min(cur + _dt.timedelta(days=365 * 8), d1)
        try:
            rs = bs.query_history_k_data_plus(
                code, FIELDS,
                start_date=cur.isoformat(), end_date=seg_end.isoformat(),
                frequency="d", adjustflag="2")       # 2 = 前复权
        except Exception:                            # noqa: BLE001
            return None
        if rs.error_code != "0":
            return None
        # ⚠️ 用 rs.data 直接取，不用 next()（实测 next() 会偶发卡死）
        for r in (rs.data or []):
            rows[r[0]] = r
        if seg_end >= d1:
            break
        cur = seg_end + _dt.timedelta(days=1)
    return [rows[k] for k in sorted(rows)]


def main() -> int:
    ap = argparse.ArgumentParser(description="baostock 全量日线拉取（抗卡顿）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2003-01-01")
    ap.add_argument("--end", default="")
    ap.add_argument("--limit", type=int, default=0, help="0=全部（测试用）")
    ap.add_argument("--retry", type=int, default=3)
    ap.add_argument("--shard", default="", help="分片 N/M，如 1/4（多进程并行用）")
    ap.add_argument("--codes", default="",
                    help="本地代码列表（每行一个，形如 sh600000）；给了就跳过网络枚举")
    ap.add_argument("--sample", type=int, default=0,
                    help="从列表中随机抽样 N 只（0=全部）；固定种子 42 保证可复现")
    args = ap.parse_args()

    socket.setdefaulttimeout(30)
    os.makedirs(args.out, exist_ok=True)

    import baostock as bs
    lg = bs.login()
    if lg.error_code != "0":
        print(f"baostock 登录失败：{lg.error_code} {lg.error_msg}")
        return 2
    print(f"baostock 登录成功（start={args.start}）", flush=True)

    end = args.end
    if not end:
        end = time.strftime("%Y-%m-%d")

    # 全量股票列表（含退市股）
    # ⚠️ 四个实测约束（2026-10-11）：
    #   ① query_all_stock / query_stock_basic / query_trade_dates
    #      **都只返回前 2000 行**（静默截断）
    #   ② query_all_stock 需要**交易日**（传周末返回空）
    #   ③ 单日快照**不含已退市股**
    #   ④ 靠 query_trade_dates 拿交易日列表**不可靠**（它自己也截断到 2000 行，
    #      只覆盖最近约 8 年）
    # → 对策：**不依赖交易日列表**，改为**每年直接试几个候选日期**做快照，
    #   成功的即纳入；再合并去重。这样能跨 2003-2026 且捞到退市股。
    allcodes: set = set()
    probe_hits = 0
    if args.codes and os.path.exists(args.codes):
        with open(args.codes, encoding="utf-8") as fh:
            for line in fh:
                t = line.strip()
                if not t:
                    continue
                # 本地列表形如 sh600000；baostock 需要 sh.600000
                t = t.replace(".", "")
                allcodes.add(f"{t[:2]}.{t[2:]}")
        print(f"  从本地列表读入 {len(allcodes)} 个代码（跳过网络枚举）", flush=True)
    for y in range(2003, int(end[:4]) + 1):
        # 每年**只试 1 个日期**（试多个会成倍拉长启动时间，实测 96 次请求超时）
        d = f"{y}-12-31"
        if d > end:
            d = end
        rr = bs.query_all_stock(day=d)
        if rr.error_code == "0" and rr.data:
            allcodes.update(r[0] for r in rr.data)
            probe_hits += 1
        elif rr.error_code == "0":
            # 12-31 非交易日时，退一天再试一次
            rr2 = bs.query_all_stock(day=f"{y}-12-30")
            if rr2.error_code == "0" and rr2.data:
                allcodes.update(r[0] for r in rr2.data)
                probe_hits += 1
    if not allcodes:
        print(f"  多日期枚举：命中 {probe_hits} 个年度快照 → 合并 "
              f"{len(allcodes)} 个代码", flush=True)
    # 只保留股票（sh.6/sz.0/sz.3），排除指数与基金
    stocks = sorted(c for c in allcodes
                    if (c.startswith("sh.6") or c.startswith("sz.0")
                        or c.startswith("sz.3")))
    if not stocks:
        print(f"  !! 股票列表为空；中止", flush=True)
        bs.logout()
        return 2
    # 分片：支持多进程并行（baostock 非线程安全，故用多进程而非多线程）
    if args.shard:
        try:
            n, m = (int(x) for x in args.shard.split("/"))
            stocks = [c for i, c in enumerate(stocks) if i % m == n - 1]
            print(f"  分片 {n}/{m} -> {len(stocks)} 只", flush=True)
        except Exception:
            print(f"  --shard 格式错误：{args.shard}"); return 2
    if args.limit:
        stocks = stocks[:args.limit]
    print(f"  股票 {len(stocks)} 只", flush=True)

    ok = skip = 0
    empty: List[str] = []
    failed: List[str] = []
    t0 = time.time()
    for i, code in enumerate(stocks, 1):
        stem = _norm(code)                          # sh600519
        dst = os.path.join(args.out, f"{stem}.csv")
        if os.path.exists(dst) and os.path.getsize(dst) > 64:
            skip += 1
            continue
        rows = None
        for attempt in range(args.retry):
            rows = fetch_one(bs, code, args.start, end)
            if rows is not None:
                break
            time.sleep(2.0 * (attempt + 1))
        if rows is None:
            failed.append(code)
            continue
        if not rows:
            empty.append(code)
            continue
        tmp = dst + ".part"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(HEADER + "\n")
            for r in rows:
                fh.write(",".join(r) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dst)                        # 原子落盘
        ok += 1
        if i % 25 == 0:
            print(f"  {i}/{len(stocks)}  成功 {ok} 跳过 {skip} "
                  f"空 {len(empty)} 失败 {len(failed)}  "
                  f"({time.time()-t0:.0f}s)", flush=True)

    bs.logout()
    print(f"\n完成：成功 {ok} 跳过 {skip} 空 {len(empty)} 失败 {len(failed)}"
          f"  用时 {time.time()-t0:.0f}s")
    if failed:
        with open(os.path.join(args.out, "_failed.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(failed))
        print(f"失败清单已落盘（{len(failed)} 只，前 8：{failed[:8]}）")
    print("⚠️ 若失败数 > 0，须重跑本命令（幂等）直至其为 0，"
          "否则样本不完整会污染 H-XSRC 结论（预注册 §六 禁止项）。")
    return 0 if not failed else 3


if __name__ == "__main__":
    sys.exit(main())
