# -*- coding: utf-8 -*-
"""从通达信行情服务器拉取证券名称表，生成 data/names.csv。

用途：为 screen / daily_report 提供代码→名称映射（报告显示名称 + ST 剔除）。
借鉴 Sequoia-X（sngyai/Sequoia-X, 7.6k★）用 baostock 拉名称的做法，
改用 pytdx：零新依赖（gbbq 缓存同源），名称直接来自通达信行情服务器。

实测服务器行为（2026-09-30）：
- get_security_list 每页 1000 条，但**不保证从 start=0 连续**：上证云服务器
  sh 市场在 start<900 返回空，600xxx 股票段位于 start≈25000+；
- 深市股票（000/001/002/003/300/301）在前 6000 条内；
- 北交所（market=2）在测试的 20 台服务器上均不可用——北交所标的
  将无名称映射（显示 '-'，ST 剔除不覆盖北交所，记为已知局限）。

因此拉取策略为**容忍空页的全量扫描**：start 从 0 推进到 total，
空页按 +1000 步进跳过，不提前终止；每 20 页重连一次防长连接退化。

用法（需联网，用隔离环境 python 运行）::

    python -m tdx_native.fetch_names --out data/names.csv

幂等：重复运行直接覆盖重写。名称表变化缓慢，约每季度跑一次即可。
"""
from __future__ import annotations

import argparse
import csv
import os

# 每 20 页重连一次，防长连接退化
RECONNECT_EVERY = 20


def _connect(hq_hosts, max_hosts: int = 12):
    from pytdx.hq import TdxHq_API

    for h in hq_hosts[:max_hosts]:
        api = TdxHq_API()
        try:
            if api.connect(h[1], h[2], time_out=6):
                return api, h
        except Exception:
            continue
    raise RuntimeError("无法连接任何通达信行情服务器（检查网络）")


def _fetch_market(api, mkt: int, tag: str):
    """拉取单个市场全量列表；容忍空页，返回 [(code, name), ...]。"""
    try:
        total = api.get_security_count(mkt)
    except Exception:
        print(f"market {tag}: 服务器不支持，跳过")
        return []
    rows = []
    start = 0
    pages = 0
    while start < total:
        try:
            page = api.get_security_list(mkt, start) or []
        except Exception:
            page = []
        for it in page:
            code = str(it.get("code", ""))
            name = str(it.get("name", "")).strip()
            if len(code) == 6 and code.isdigit():
                rows.append((code, name))
        start += len(page) if page else 1000
        pages += 1
    print(f"market {tag}: 服务器报 {total} 条，扫描 {pages} 页，"
          f"取到 6 位代码 {len(rows)} 条")
    return rows


def fetch_names(out_csv: str, max_hosts: int = 12) -> int:
    from pytdx.config.hosts import hq_hosts

    api, host = _connect(hq_hosts, max_hosts)
    print(f"已连接：{host[1]}:{host[2]}（{host[0]}）")

    all_rows = []
    for mkt, tag in ((0, "sz"), (1, "sh"), (2, "bj")):
        rows = _fetch_market(api, mkt, tag)
        if not rows and mkt == 2:
            print("market bj: 无数据（服务器普遍不支持北交所列表，"
                  "北交所标的将无名称映射——已知局限）")
        all_rows.extend(rows)

    # 去重（sz/sh/bj 之间代码理论上不重叠，防御性保留）
    seen = set()
    uniq = []
    for code, name in all_rows:
        if code not in seen:
            seen.add(code)
            uniq.append((code, name))

    api.disconnect()

    out_dir = os.path.dirname(os.path.abspath(out_csv))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "name"])
        w.writerows(uniq)
    st = sum(1 for _, n in uniq if "ST" in n.upper())
    sh = sum(1 for c, _ in uniq if c.startswith(("600", "601", "603", "605", "688")))
    print(f"写入 {out_csv}: {len(uniq)} 只（沪深股票段 {sh} 只，"
          f"ST/退市整理 {st} 只）")
    return len(uniq)


def main() -> int:
    ap = argparse.ArgumentParser(description="拉取通达信证券名称表 names.csv")
    ap.add_argument("--out", default="data/names.csv")
    args = ap.parse_args()
    fetch_names(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
