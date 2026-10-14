# -*- coding: utf-8 -*-
"""H-XSRC 拉取协调器：并行启动 N 个分片并等待全部结束。

## 为什么需要它

本机后台任务有已知约束：**单个后台任务约 25-40 分钟静默死亡**。
实测踩过：用 `nohup ... &` 起分片，父 shell 一退出**所有子进程被清理**
（4 个分片各跑了几只就全死，产出停在启动时刻）。

→ 对策：**由本脚本在一个前台进程内起分片子进程并 join 等待**，
再由上层用「后台任务」机制跑本脚本（而非 `nohup &`）。
这样：子进程生命周期 = 本进程生命周期，不会因父 shell 退出而孤儿化。

## 抗死机

- 分片脚本自身**逐只落盘 + 幂等续传** → 本脚本即使中途被杀，重跑即续
- 每个分片独立日志，便于定位

用法::

    python scripts/run_xsrc_fetch.py --codes D:/xs_tencent/codes_1000.json \\
        --out D:/xs_tencent/klines --shards 4
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def main() -> int:
    ap = argparse.ArgumentParser(description="H-XSRC 拉取协调器")
    ap.add_argument("--codes", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--start", default="2003-01-01")
    ap.add_argument("--end", default="2026-10-09")
    ap.add_argument("--logdir", default="")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    # ⚠️ Windows：默认 "/tmp" 会被当成相对路径（"/tmp\xsx_1.log" 不存在）
    #    → 日志目录默认建在 out 之下
    logdir = args.logdir or os.path.join(args.out, "_logs")
    os.makedirs(logdir, exist_ok=True)
    args.logdir = logdir
    fetcher = ROOT / "scripts" / "fetch_delisted_full.py"

    procs = []
    for i in range(1, args.shards + 1):
        # 日志句柄须跨 Popen 生命周期持有，故不用 with（noqa: SIM115）
        log = open(  # noqa: SIM115 —— 句柄须跨 Popen 生命周期持有，不能用 with
            os.path.join(args.logdir, f"xsx_{i}.log"), "w", encoding="utf-8")
        cmd = [PY, str(fetcher), "--list", args.codes, "--out", args.out,
               "--start", args.start, "--shard", f"{i}/{args.shards}"]
        print(f"  启动分片 {i}/{args.shards}", flush=True)
        procs.append((i, subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT),
                      log))
        time.sleep(1.5)                    # 错开启动，避免同时打服务器

    print(f"\n等待 {len(procs)} 个分片结束...", flush=True)
    t0 = time.time()
    rc_all = 0
    while True:
        alive = [p for _i, p, _l in procs if p.poll() is None]
        done = len(procs) - len(alive)
        n_csv = len(list(Path(args.out).glob("*.csv")))
        print(f"  [{time.time()-t0:6.0f}s] 完成 {done}/{len(procs)} 分片，"
              f"已产出 {n_csv} 个 CSV", flush=True)
        if not alive:
            break
        time.sleep(60)

    for i, p, log in procs:
        log.close()
        if p.returncode not in (0, None):
            rc_all = 1
            print(f"  ⚠️ 分片 {i} 退出码 {p.returncode}", flush=True)

    n_csv = len(list(Path(args.out).glob("*.csv")))
    print(f"\n全部分片结束：产出 {n_csv} 个 CSV，用时 {time.time()-t0:.0f}s",
          flush=True)
    print("⚠️ 若有分片失败，重跑本命令即可续（幂等）。", flush=True)
    return rc_all


if __name__ == "__main__":
    sys.exit(main())
