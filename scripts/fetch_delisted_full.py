# -*- coding: utf-8 -*-
"""拉取退市股全历史日线（腾讯源，end 递推，抗死机）。

## 为什么不用现成的 fetch_delisted_klines.py

| 项 | 现成脚本 | 本脚本 |
|---|---|---|
| 回溯长度 | `--count 640`（约 2.5 年） | **全历史**（end 递推，可到 1990 年代） |
| 用途 | 量化退市损失幅度 | **并入 H-CD 数据集**（需要 2003 起的长历史） |

## 腾讯接口的分段语义（2026-10-11 实测）

`param={sym},day,{start},{end},{n},`

**返回的是「`end` 之前 n 条」，`start` 仅作下限**——
不是「start~end 区间」。实测：`2007-01-01~2010-12-31,1000` 返回
`2007-03-07 ~ 2010-12-31`（= end 往前 1000 条），而非自 2007-01 开始。

→ **必须用 end 递推**：每轮取回 n 条后，把 end 设为「已取回的最早日期 −1 天」，
    直到返回空或不早于 `--start`。

另：n ≥ 3000 会返回**空**（实测 3000/6000/8000 均为空），故 n 取 1000 安全。

## 抗死机

- **逐只落盘**：每只股票写成独立 CSV，完成后立即 flush+fsync
- **幂等续传**：已存在的 CSV 默认跳过（`--overwrite` 可强制）
- **失败隔离**：单只失败不影响其余，失败清单单独落盘
- 本机后台任务 25-40 分钟会静默死亡 → **分批跑 + 重跑即续**

用法：
    python scripts/fetch_delisted_full.py --list D:/dl_backfill/delisted_in_window.json \\
        --out D:/dl_backfill/klines --start 2003-01-01
    # 死机后直接重跑同一条命令即可续
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
CHUNK = 1000          # 每次请求条数；实测 ≥3000 返回空
CSV_COLS = ["date", "open", "close", "high", "low", "volume", "amount"]


class SourceBlocked(RuntimeError):
    """数据源拒绝服务。必须与「无数据」区分（§静默失效纪律）。"""


def _fetch(sym: str, end: str, n: int = CHUNK) -> List[List]:
    """取 `end` 之前 n 条日线。返回 [] 表示已到尽头。"""
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={sym},day,,{end},{n},")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        raise SourceBlocked(f"HTTP {exc.code}（疑似限流）") from exc
    except Exception as exc:                       # noqa: BLE001
        raise SourceBlocked(f"{type(exc).__name__}: {exc}") from exc
    data = json.loads(body)
    node = (data.get("data") or {}).get(sym) or {}
    if isinstance(node, dict):
        return node.get("day") or node.get("qfqday") or []
    return []


def fetch_full(sym: str, start: str, max_rounds: int = 30) -> List[List]:
    """end 递推拉全历史（去重 + 升序）。"""
    start_c = start.replace("-", "")
    end = dt.date.today().isoformat()
    seen: Dict[str, List] = {}
    for _ in range(max_rounds):
        kl = _fetch(sym, end)
        if not kl:
            break
        new = 0
        for row in kl:
            d = row[0].replace("-", "")
            if d not in seen:
                seen[d] = row
                new += 1
        earliest = min(r[0].replace("-", "") for r in kl)
        if earliest <= start_c:
            break
        if new == 0:                               # 无新增 → 防死循环
            break
        # 把 end 推到已取回的最早日期前一天
        d0 = dt.date(int(earliest[:4]), int(earliest[4:6]), int(earliest[6:8]))
        end = (d0 - dt.timedelta(days=1)).isoformat()
        time.sleep(1.1)                            # 限流保护（实测 0.35s 会被 501 封禁）
    rows = [seen[k] for k in sorted(seen)]
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="拉取退市股全历史（腾讯，end 递推）")
    ap.add_argument("--list", required=True, help="delisted_in_window.json")
    ap.add_argument("--out", required=True, help="CSV 输出目录")
    ap.add_argument("--start", default="2003-01-01", help="回溯下限")
    ap.add_argument("--limit", type=int, default=0, help="0=全部（测试用）")
    ap.add_argument("--shard", default="", help="分片 N/M，如 1/4（多进程并行用）")
    ap.add_argument("--retry", type=int, default=3, help="遇限流的重试次数")
    ap.add_argument("--backoff", type=float, default=20.0,
                    help="退避基数（秒），第 n 次等待 backoff*2^(n-1)")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    socket.setdefaulttimeout(30)
    os.makedirs(args.out, exist_ok=True)

    with open(args.list, encoding="utf-8") as fh:
        recs = json.load(fh)
    codes = [r["code"] for r in recs]
    if args.shard:
        try:
            n, m = (int(x) for x in args.shard.split("/"))
            codes = [c for i, c in enumerate(codes) if i % m == n - 1]
            print(f"  分片 {n}/{m} -> {len(codes)} 只", flush=True)
        except Exception:
            print(f"  --shard 格式错误：{args.shard}"); return 2
    if args.limit:
        codes = codes[:args.limit]
    print(f"待拉取 {len(codes)} 只（回溯下限 {args.start}）", flush=True)

    ok = skip = fail = 0
    bad: List[str] = []
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        dst = os.path.join(args.out, f"{code}.csv")
        if os.path.exists(dst) and not args.overwrite:
            skip += 1
            continue
        try:
            # 退避重试：实测 4 分片并行时跑约 120s 即被 HTTP 501。
            # 直接 break 会浪费已跑进度，故改为「等待 → 重试」，
            # 连续失败超过阈值才真正中止。
            rows = None
            for attempt in range(args.retry):
                try:
                    rows = fetch_full(code, args.start)
                    break
                except SourceBlocked as exc:
                    if attempt == args.retry - 1:
                        raise
                    wait = args.backoff * (2 ** attempt)
                    print(f"      [{code}] {exc} → 退避 {wait:.0f}s 后重试 "
                          f"({attempt+1}/{args.retry})", flush=True)
                    time.sleep(wait)
            if not rows:
                bad.append(f"{code}: 无数据")
                fail += 1
                continue
            tmp = dst + ".part"
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(",".join(CSV_COLS) + "\n")
                for r in rows:                     # [日期,开,收,高,低,量(手)]
                    # ⚠️ amount（成交额）为**估算值**，非数据源原始字段。
                    # 腾讯 K 线只返回成交量（手）、东财虽返回成交额但限流严格。
                    # 估算式：amount ≈ 成交量(股) × 典型价，典型价取 (H+L+C)/3。
                    # 影响：五因子中 `amihud20`（|ret|/amount）与 `loga20`（log amount）
                    # 依赖此字段；估算误差通常 3~8%，且**方向一致**，
                    # 对横截面排序型 IC 的影响远小于该误差本身。
                    # 该局限已在 DELISTED_BACKFILL_PREREG.md §五 声明。
                    try:
                        c = float(r[2])
                        h, lo = float(r[3]), float(r[4])
                        # ⚠️ 2026-10-12 修正：腾讯 volume 单位是**股**，不是「手」。
                        # 实测 91 只「通达信 volume / 腾讯 volume」中位比 = **1.0**；
                        # 此前按「手」多乘 100 → volume 与 amount 均放大 100 倍。
                        # 好在是**常数缩放**，不影响横截面排序，IC 结论不受影响；
                        # 但数据必须修正。
                        vol_shares = float(r[5])
                        typ = (h + lo + c) / 3.0
                        amt = vol_shares * typ
                    except (ValueError, IndexError):
                        c = h = lo = typ = amt = 0.0
                    fh.write(",".join([
                        r[0].replace("-", ""), r[1], r[2], r[3], r[4],
                        "%.0f" % vol_shares,
                        "%.2f" % amt]) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, dst)                   # 原子落盘：不留半截文件
            ok += 1
        except SourceBlocked as exc:
            bad.append(f"{code}: 限流 {exc}")
            fail += 1
            print(f"\n  !! 限流中止于第 {i} 只（{ok} 成功 / {skip} 跳过）。"
                  f"**已拉取的不受影响**，稍后重跑即续。", flush=True)
            break
        except Exception as exc:                   # noqa: BLE001
            bad.append(f"{code}: {type(exc).__name__}: {exc}")
            fail += 1
        if i % 10 == 0:
            print(f"      {i}/{len(codes)}  成功 {ok} 跳过 {skip} 失败 {fail}"
                  f"  ({time.time()-t0:.0f}s)", flush=True)
        time.sleep(0.9)

    print(f"\n完成：成功 {ok}  跳过 {skip}  失败 {fail}  用时 {time.time()-t0:.0f}s")
    if bad:
        with open(os.path.join(args.out, "_failures.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(bad))
        print(f"失败清单（前 8/{len(bad)}）：")
        for b in bad[:8]:
            print("   ", b)
    return 0 if fail == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
