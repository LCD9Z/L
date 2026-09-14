# -*- coding: utf-8 -*-
"""枚举 A 股全代码空间，找出**退市股**——即 TDX 数据集缺失的样本。

## 为什么需要

TDX 数据集不含退市股 → 幸存者偏差 → 收益被系统性高估。
这是项目第一优先级的数据缺口。

## 方法（三步，全部实测可行）

1. **枚举代码空间**：用腾讯批量行情 `qt.gtimg.cn/q=` 扫全部可能的 A 股代码，
   有名称的即为"曾存在"的证券。北交所段不可遗漏（否则会把 300+ 只北交所股票
   误判为退市）。
2. **与 TDX 对比**：取差集得到「腾讯有 / TDX 无」的候选。
3. **按 K 线末日判定**：逐个取 K 线，末日落在研究窗口内且早于数据截止日的，
   才是**窗口内退市**的股票。

**不能只看名称含"退"字** —— 实测 `PT金田A`、`邯郸钢铁` 等退市股名称不含"退"。

## 数据源与正确调用格式

腾讯 K 线：`web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq`

- `qfq` 后缀**必需**，缺了返回 `bad params`
- `n` 上限 **640**（约 2.6 年），超了返回 `param error`

用法::

    python scripts/enumerate_delisted_universe.py --out D:/tdx_dataset
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QT_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
KLINE_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}

#: 候选 A 股代码段（含北交所 —— 实测遗漏会把北交所股票误判为退市）
CODE_RANGES: Tuple[Tuple[str, int, int], ...] = (
    ("sh", 600000, 606000),
    ("sh", 688000, 689000),
    ("sz", 1, 4000),
    ("sz", 300000, 302000),
    ("bj", 430000, 430500),
    ("bj", 830000, 840000),
    ("bj", 870000, 880000),
    ("bj", 880000, 880200),
    ("bj", 920000, 921000),
)


def _get(url: str, headers: Dict[str, str], encoding: str = "utf-8",
         retries: int = 3, timeout: int = 20) -> str:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(encoding, "ignore")
        except Exception as exc:
            last = exc
            time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"请求失败: {last}")


def build_code_space() -> List[str]:
    out: List[str] = []
    for market, lo, hi in CODE_RANGES:
        out.extend(f"{market}{c:06d}" for c in range(lo, hi))
    return out


def enumerate_existing(space: List[str], batch: int = 200,
                       rate: float = 8.0) -> Dict[str, str]:
    """批量查询，返回 ``{market+code: 名称}``。"""
    found: Dict[str, str] = {}
    interval = 1.0 / rate if rate > 0 else 0.0
    for i in range(0, len(space), batch):
        chunk = space[i:i + batch]
        try:
            raw = _get("https://qt.gtimg.cn/q=" + ",".join(chunk), QT_HEADERS, "gbk")
        except RuntimeError:
            continue
        for line in raw.split(";"):
            if "=" not in line:
                continue
            code = line.split("=")[0].strip().replace("v_", "")
            parts = line.split("=", 1)[1].strip().strip('"').split("~")
            if len(parts) > 1 and parts[1]:
                found[code] = parts[1]
        if interval:
            time.sleep(interval)
    return found


class SourceBlocked(RuntimeError):
    """数据源拒绝服务（限流/封禁）——**必须与"无数据"区分**。

    实测教训：高频请求后腾讯 K 线端点返回 HTTP 501，若把异常吞掉当成
    "该股无 K 线"，会得出"零退市股"的**假结论**。这正是本项目最警惕的
    静默失效，因此这里显式抛出并在上层中止。
    """


def kline_span(code: str, count: int = 640) -> Tuple[Optional[str], Optional[str]]:
    """返回 ``(首个交易日, 最后交易日)``；**数据源拒绝时抛 SourceBlocked**。

    "无数据"（该代码从未上市）与"请求失败"必须区分：前者返回 ``(None, None)``，
    后者抛异常。
    """
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={code},day,,,{count},qfq")
    try:
        req = urllib.request.Request(url, headers=KLINE_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        raise SourceBlocked(
            f"K 线端点拒绝服务 HTTP {exc.code}（疑似限流）。"
            f"请降低 --workers 并稍后重试；不要据此判定'无退市股'。") from exc
    except Exception as exc:
        raise SourceBlocked(f"K 线请求异常: {type(exc).__name__}") from exc

    data = json.loads(body)
    inner = (data.get("data") or {}).get(code) or {}
    kl = inner.get("qfqday") or inner.get("day") or []
    if not kl:
        return None, None
    return kl[0][0], kl[-1][0]


def main() -> int:
    ap = argparse.ArgumentParser(description="枚举 A 股全代码空间并识别退市股")
    ap.add_argument("--out", default="D:/tdx_dataset")
    ap.add_argument("--tdx-codes", default="",
                    help="TDX 全集 JSON（默认 {out}/tdx_all_codes.json）")
    ap.add_argument("--window-start", default="2021-08-01")
    ap.add_argument("--data-end", default="2026-09-10")
    ap.add_argument("--workers", type=int, default=2,
                    help="K 线并发数。**端点限速严格**：实测并发 6 会被 HTTP 501 封禁")
    ap.add_argument("--skip-kline", action="store_true",
                    help="只做枚举与差集，不逐个取 K 线")
    args = ap.parse_args()

    socket.setdefaulttimeout(25)
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()

    print("=" * 88)
    print("A 股全代码空间枚举 · 识别 TDX 缺失的退市股")
    print("=" * 88)

    print("\n[1/3] 枚举代码空间 ...")
    space = build_code_space()
    print(f"      候选代码 {len(space):,} 个")
    existing = enumerate_existing(space)
    print(f"      有名称的证券 {len(existing):,} 个  ({time.time()-t0:.0f}s)")
    with open(os.path.join(out_dir, "tencent_universe.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(existing, f, ensure_ascii=False, indent=0)

    print("\n[2/3] 与 TDX 对比 ...")
    tdx_path = args.tdx_codes or os.path.join(out_dir, "tdx_all_codes.json")
    if not os.path.exists(tdx_path):
        print(f"      !! 缺少 {tdx_path}；请先从 TDX 源导出代码全集")
        return 2
    from tdx.tdx_csv_adapter import is_a_share_stock
    tdx_stock: Set[str] = set()
    with open(tdx_path, encoding="utf-8") as f:
        for k in json.load(f):
            if is_a_share_stock(k[2:], k[:2]):
                tdx_stock.add(k)
    tx = set(existing)
    only_tx = sorted(tx - tdx_stock)
    only_tdx = sorted(tdx_stock - tx)
    print(f"      TDX A 股股票      : {len(tdx_stock):,}")
    print(f"      腾讯枚举          : {len(tx):,}")
    print(f"      【腾讯有/TDX 无】 : {len(only_tx):,}  <- 候选")
    print(f"      【TDX 有/腾讯无】 : {len(only_tdx):,}")

    if args.skip_kline:
        with open(os.path.join(out_dir, "universe_diff.json"), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump({"only_tencent": {c: existing[c] for c in only_tx},
                       "only_tdx": only_tdx}, f, ensure_ascii=False, indent=1)
        print(f"\n已保存 {out_dir}/universe_diff.json（跳过 K 线判定）")
        return 0

    print("\n[3/3] 按 K 线末日判定是否在窗口内退市 ...")
    print(f"      候选 {len(only_tx)} 个，并发 {args.workers}")
    delisted: List[Dict[str, str]] = []
    done = 0
    t0k = time.time()

    def _probe(code: str) -> Optional[Dict[str, str]]:
        first, last = kline_span(code)
        if last and last < args.data_end and last >= args.window_start:
            return {"code": code, "name": existing[code],
                    "first": first or "", "last": last}
        return None

    # 端点限速严格：实测并发 6 时被 HTTP 501 封禁。默认并发 2。
    # 一旦 SourceBlocked **立即中止** —— 继续跑会得出"零退市股"的假结论。
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            for res in pool.map(_probe, only_tx):
                done += 1
                if res is not None:
                    delisted.append(res)
                if done % 50 == 0:
                    print(f"      {done}/{len(only_tx)}  命中 {len(delisted)}  "
                          f"({time.time()-t0k:.0f}s)", flush=True)
    except SourceBlocked as exc:
        print(f"\n      !! 中止：{exc}")
        print(f"      已完成 {done}/{len(only_tx)}；结果不完整，**不写入文件**。")
        return 3
    delisted.sort(key=lambda d: d["code"])

    print(f"\n      【窗口内退市】{len(delisted):,} 只")
    with open(os.path.join(out_dir, "universe_diff.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump({"only_tencent": {c: existing[c] for c in only_tx},
                   "only_tdx": only_tdx}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "delisted_in_window.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(delisted, f, ensure_ascii=False, indent=1)

    print("\n      样例：")
    for d in delisted[:15]:
        print(f"        {d['code']}  {d['name']:14s} {d['first']} ~ {d['last']}")
    print(f"\n结果已写入 {out_dir}/delisted_in_window.json")
    print(f"总耗时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
