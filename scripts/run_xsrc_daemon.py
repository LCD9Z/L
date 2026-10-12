# -*- coding: utf-8 -*-
"""H-XSRC 拉取守护：低频重试直至完成（应对 IP 级限流）。

## 为什么需要它

实测（2026-10-12）：腾讯 K 线端点对**IP 级限流**——
4 分片跑 120s 即 HTTP 501，随后**直接单测也是 501**，且**指数退避 20s/40s 无效**。
同一时段东财亦 `RemoteDisconnected`；新浪可用但**不复权**（会污染 `ret20`），
不适合作跨源验证。

→ 故不是「换个源」能解决的，只能**等限流窗口过去**。
本脚本以**低频**（默认 15 分钟）重试，一旦成功即续拉（底层幂等）。

## 行为

1. 先**探测**：单只请求，成功才开始
2. 逐轮调用 `run_xsrc_fetch.py`（其内部 2 分片 + join）
3. 任一轮**产出增加**即继续；连续 N 轮无进展则延长间隔
4. 达到目标数量或超过总时限则退出

用法::

    python scripts/run_xsrc_daemon.py --target 1000 --rounds 12 --interval 900
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def probe() -> bool:
    """单只探测腾讯是否已解除限流。"""
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           "param=sh600000,day,,,10,qfq")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        kl = ((d.get("data") or {}).get("sh600000") or {}).get("qfqday") or []
        return len(kl) > 0
    except Exception:                                # noqa: BLE001
        return False


def count_csv(out: str) -> int:
    return len(list(Path(out).glob("*.csv")))


def main() -> int:
    ap = argparse.ArgumentParser(description="H-XSRC 拉取守护（低频重试）")
    ap.add_argument("--codes", default="D:/xs_tencent/codes_1000.json")
    ap.add_argument("--out", default="D:/xs_tencent/klines")
    ap.add_argument("--target", type=int, default=1000)
    ap.add_argument("--rounds", type=int, default=12, help="最多轮数")
    ap.add_argument("--interval", type=float, default=900.0,
                    help="轮间隔秒数（默认 15 分钟）")
    args = ap.parse_args()

    print(f"H-XSRC 拉取守护启动：目标 {args.target} 只，"
          f"最多 {args.rounds} 轮，间隔 {args.interval:.0f}s", flush=True)
    best = count_csv(args.out)
    print(f"  初始已有 {best} 个 CSV", flush=True)

    for rd in range(1, args.rounds + 1):
        if best >= args.target:
            break
        # 等限流窗口
        if not probe():
            wait = args.interval
            print(f"[轮 {rd}] 探测：腾讯仍限流 → 等 {wait:.0f}s", flush=True)
            time.sleep(wait)
            continue
        print(f"[轮 {rd}] 探测：腾讯已恢复 → 开始拉取", flush=True)
        cmd = [PY, str(ROOT / "scripts" / "run_xsrc_fetch.py"),
               "--codes", args.codes, "--out", args.out, "--shards", "2",
               "--start", "2003-01-01", "--end", "2026-10-09"]
        try:
            subprocess.run(cmd, timeout=args.interval * 2, check=False)
        except subprocess.TimeoutExpired:
            print(f"[轮 {rd}] 本轮超时（已拉取的会保留，幂等续传）", flush=True)
        now = count_csv(args.out)
        print(f"[轮 {rd}] 结束：{best} → {now}（+{now-best}）", flush=True)
        if now == best:
            # 无进展：可能是限流又来了，等更久
            print(f"[轮 {rd}] 无进展 → 等 {args.interval:.0f}s", flush=True)
            time.sleep(args.interval)
        best = now

    print(f"\n守护结束：最终 {best}/{args.target} 个 CSV", flush=True)
    return 0 if best >= args.target else 3


if __name__ == "__main__":
    sys.exit(main())
