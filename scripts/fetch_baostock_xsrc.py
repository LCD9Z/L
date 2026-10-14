# -*- coding: utf-8 -*-
"""H-XSRC 数据源 B：baostock 拉取（带「一页陷阱」守卫）。

## 为什么回到 baostock

腾讯**IP 级限流顽固**（实测：恢复后仅能拉 15~26 只即 501，等 4 分钟，
守护连跑 4 轮 20 分钟仍卡在 91/300）。而 baostock 有腾讯没有的优势：

| 项 | baostock | 腾讯 |
|---|---|---|
| 单次返回 | 一次给全历史（`beg=0&end=20500101`） | 1000 行/段，须 end 递推 |
| **amount** | ✅ **原始成交额（无需估算）** | ❌ 无（须 `volume×(H+L+C)/3` 估算） |
| 前复权 | `adjustflag='2'` | `qfq` |
| 限流 | 偶发挂起（login/next 各 1 次） | **IP 级，顽固** |

→ **baostock 的 amount 是原始值**，对 `amihud20` / `loga20` 是更强的证据
（腾讯那两个因子只能用估算 amount，属较弱证据）。

## 「一页陷阱」与规避

副本侧从源码定位（`baostock/data/resultset.py::ResultData.next()`）：

> 当某页**恰好**返回 2000 行（`PER_PAGE_COUNT`）时，客户端会去取下一页；
> **若该请求失败，静默返回 `False` 不抛异常** → 调用方看到「干净地结束在 2000 行」。

**规避方法（本脚本采用）**：**按日期分段**，每段只取约 4 年（约 960 交易日）
→ 单段行数**恒 < 2000** → **永不触发「恰好 2000」**，无需翻页。

**另加双保险**：`n % 2000 == 0` 即判为可疑（副本侧 `pit/baostock_guard.py` 判据）。

## 单位（已按副本侧三源裁决定案）

| 板块 | baostock volume 单位 |
|---|---|
| 科创板 `sh688xxx` | **股** |
| 其余 | **手** |

baostock 与通达信**逐位相同**（`sh600007@2026-10-08` 均 4,243,639），
故**不需要换算** —— 直接用 baostock 原值即与主干口径一致。

## 连接级超时（2026-10-14 补）

⚠️ 此前本脚本**没有任何连接级超时**：baostock 偶发挂起（login / 取数）
会让整个抓取**永久阻塞**，只能靠上层子进程超时兜底
（P010 后由信箱巡检登记为「主干内部待决项」）。

**修法**：在 `bs.login()` **之前**调用 `socket.setdefaulttimeout(args.timeout)`。
**为什么必须在 login 之前**：`setdefaulttimeout` 只影响**其后新建**的 socket，
而 baostock 的服务端连接正是在 `login()` 时建立的。

**超时后行为**：`_fetch_segment` 的 `except Exception` 会捕获 `socket.timeout`
→ 返回 `None` → 走既有的「退避重试」分支；重试仍失败则该只计入 `_failed.txt`，
**重跑即续**（不会再有「静默挂住不结束」的形态）。

用法::

    python scripts/fetch_baostock_xsrc.py --out D:/xs_baostock/klines \\
        --codes data/xs_codes_300.txt
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import socket
import sys
import time
from typing import Dict, List, Optional

PER_PAGE = 2000
FIELDS = "date,open,high,low,close,volume,amount"
HEADER = "date,open,close,high,low,volume,amount"


def _fetch_segment(bs, secid: str, start: str, end: str) -> Optional[List[List[str]]]:
    """取一段的日线。返回 None 表示源异常（须重试）。"""
    try:
        rs = bs.query_history_k_data_plus(
            secid, FIELDS, start_date=start, end_date=end,
            frequency="d", adjustflag="2")            # 2 = 前复权
    except Exception:                                  # noqa: BLE001
        return None
    if rs.error_code != "0":
        return None
    # ⚠️ 用 rs.data 直取（next() 会偶发卡死，且可能触发翻页静默截断）
    rows = list(rs.data or [])
    if rows and len(rows) % PER_PAGE == 0:
        # 保险：虽然日期分段应已规避，仍显式报告
        print(f"      ⚠️ {secid} {start}~{end} 返回 {len(rows)} 行"
              f"（2000 的整数倍 → 疑似一页截断）", flush=True)
    return rows


def fetch_full(bs, secid: str, start: str, end: str) -> Optional[List[List[str]]]:
    """取全历史：**先试一次拉全**（快，1 请求），
    若返回行数 ≥ 2000（可能是「一页」截断），**改为日期分段重拉**（安全）。

    ## 为什么要这样

    腾讯限流顽固（实测 30 分钟卡住），baostock 是唯一能给**原始 amount** 的源。
    但 baostock 有「一页陷阱」：某页**恰好** 2000 行时会去取下一页，
    若失败则**静默结束**（副本侧从源码定位）。

    → 权衡：一次拉全 1 请求/只（快）；**命中 2000 整数倍即判可疑**，
      自动降级为日期分段（每段 ≤4 年，恒 <2000，永不触发翻页）。
    """
    # 第一次：一次拉全
    whole = _fetch_segment(bs, secid, start, end)
    if whole is None:
        return None
    if len(whole) < PER_PAGE:
        return whole                                # 不足一页，安全

    # ≥2000 行：可能是截断，也可能是真的很多 —— 用分段复核
    print(f"      [{secid}] 一次拉全得 {len(whole)} 行（≥{PER_PAGE}）"
          f" → 降级为日期分段复核", flush=True)
    d0 = _dt.date.fromisoformat(start)
    d1 = _dt.date.fromisoformat(end)
    rows: Dict[str, List[str]] = {}
    cur = d0
    while cur <= d1:
        seg_end = min(cur + _dt.timedelta(days=365 * 4), d1)
        seg = _fetch_segment(bs, secid, cur.isoformat(), seg_end.isoformat())
        if seg is None:
            return None
        for r in seg:
            rows[r[0]] = r
        if seg_end >= d1:
            break
        cur = seg_end + _dt.timedelta(days=1)
    merged = [rows[k] for k in sorted(rows)]
    if len(merged) > len(whole):
        print(f"      [{secid}] ⚠️ 分段得 {len(merged)} > 一次拉全 {len(whole)}"
              f" → 确有一次拉全被截断（守卫判据有效）", flush=True)
    return merged


def _secid(code: str) -> str:
    """'sh600000' → 'sh.600000'（baostock 格式：9 位，含市场点号）。

    ⚠️ 2026-10-12 修正：初版写成 `1.600000`（东财的 secid 格式），
    baostock 报 `10004006 股票代码应为9位`。
    **两库的 secid 格式不同** —— 又一次「默认继承」踩坑。
    """
    return f"{code[:2]}.{code[2:]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="baostock 拉取（带一页守卫）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--codes", required=True, help="纯文本代码列表，每行 sh600000")
    ap.add_argument("--start", default="2003-01-01")
    ap.add_argument("--end", default="2026-10-09")
    ap.add_argument("--shard", default="", help="分片 N/M")
    ap.add_argument("--retry", type=int, default=3)
    ap.add_argument("--backoff", type=float, default=20.0)
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="连接级 socket 超时（秒）。⚠️ 2026-10-14 补："
                         "此前**无**连接级超时，baostock 挂起会永久阻塞，"
                         "仅靠调用方子进程超时兜底")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    # ⚠️ 2026-10-14 补：**连接级** socket 超时。
    # 须在 bs.login() **之前**设置 —— setdefaulttimeout 只影响其后新建的 socket，
    # 而 baostock 的服务端连接在 login() 时建立。
    # 见模块 docstring「连接级超时」节。
    socket.setdefaulttimeout(args.timeout)
    import baostock as bs
    lg = bs.login()
    if lg.error_code != "0":
        print(f"baostock 登录失败：{lg.error_code} {lg.error_msg}")
        return 2

    codes = [l.strip() for l in open(args.codes, encoding="utf-8") if l.strip()]
    if args.shard:
        n, m = (int(x) for x in args.shard.split("/"))
        codes = [c for i, c in enumerate(codes) if i % m == n - 1]
        print(f"  分片 {n}/{m} -> {len(codes)} 只", flush=True)

    ok = skip = 0
    failed: List[str] = []
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        dst = os.path.join(args.out, f"{code}.csv")
        if os.path.exists(dst) and os.path.getsize(dst) > 64:
            skip += 1
            continue
        rows = None
        for attempt in range(args.retry):
            rows = fetch_full(bs, _secid(code), args.start, args.end)
            if rows is not None:
                break
            if attempt == args.retry - 1:
                break
            wait = args.backoff * (2 ** attempt)
            print(f"      [{code}] 源异常 → 退避 {wait:.0f}s 后重试 "
                  f"({attempt+1}/{args.retry})", flush=True)
            time.sleep(wait)
        if rows is None:
            failed.append(code)
            continue
        if not rows:
            failed.append(code)
            continue
        tmp = dst + ".part"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(HEADER + "\n")
            for r in rows:
                # 重排列：baostock 是 date,open,high,low,close,volume,amount
                fh.write(",".join([r[0], r[1], r[4], r[2], r[3], r[5], r[6]]) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dst)
        ok += 1
        if i % 10 == 0:
            print(f"  {i}/{len(codes)}  成功 {ok} 跳过 {skip} "
                  f"失败 {len(failed)}  ({time.time()-t0:.0f}s)", flush=True)
        time.sleep(0.6)

    bs.logout()
    print(f"\n完成：成功 {ok} 跳过 {skip} 失败 {len(failed)}  "
          f"用时 {time.time()-t0:.0f}s")
    if failed:
        with open(os.path.join(args.out, "_failed.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(failed))
        print(f"失败 {len(failed)} 只（重跑即续）")
    return 0 if not failed else 3


if __name__ == "__main__":
    sys.exit(main())
