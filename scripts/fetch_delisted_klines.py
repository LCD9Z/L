# -*- coding: utf-8 -*-
"""抓取窗口内退市股票的日线，用于量化幸存者偏差。

## 为什么

`enumerate_delisted_universe.py` 已识别出 **180 只** 在研究窗口
（2021-08 ~ 2026-09）内退市、且 TDX 数据集完全缺失的股票。
本脚本抓取它们的日线，以便：

1. 量化这批股票的实际损失幅度（退市 = 接近归零）
2. 评估它们对因子研究的影响

## 数据源

主源**腾讯**，备用**新浪**。实测两者都能取到退市股历史。

| 源 | 端点 |
|----|------|
| 腾讯 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq` |
| 新浪 | `money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={n}` |

**限流教训**：腾讯端点在并发 6 时会返回 HTTP 501 封禁。
本脚本默认并发 **1**、请求间加延时，并在连续失败时**中止**而非产出空结果。

用法::

    python scripts/fetch_delisted_klines.py --out D:/tdx_dataset --source sina
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
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
           "Referer": "https://gu.qq.com/"}
SINA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://finance.sina.com.cn/"}


class SourceBlocked(RuntimeError):
    """数据源拒绝服务（限流/封禁）——必须与"无数据"区分。"""


def _fetch_tencent(code: str, count: int) -> List[List[Any]]:
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={code},day,,,{count},qfq")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        raise SourceBlocked(f"腾讯 K 线 HTTP {exc.code}") from exc
    except Exception as exc:
        raise SourceBlocked(f"腾讯 K 线异常 {type(exc).__name__}") from exc
    inner = (json.loads(body).get("data") or {}).get(code) or {}
    return inner.get("qfqday") or inner.get("day") or []


def _fetch_sina(code: str, count: int) -> List[List[Any]]:
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={count}")
    try:
        req = urllib.request.Request(url, headers=SINA_HEADERS)
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        raise SourceBlocked(f"新浪 K 线 HTTP {exc.code}") from exc
    except Exception as exc:
        raise SourceBlocked(f"新浪 K 线异常 {type(exc).__name__}") from exc
    if not body.strip() or body.strip() in ("null", "[]"):
        return []
    rows = json.loads(body)
    # 新浪格式：[{day,open,high,low,close,volume}, ...] -> 归一到腾讯的列表格式
    return [[r["day"], r["open"], r["close"], r["high"], r["low"], r["volume"]]
            for r in rows if isinstance(r, dict) and r.get("day")]


SOURCES = {"tencent": _fetch_tencent, "sina": _fetch_sina}


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取窗口内退市股日线")
    ap.add_argument("--out", default="D:/tdx_dataset")
    ap.add_argument("--source", choices=sorted(SOURCES), default="sina")
    ap.add_argument("--count", type=int, default=640)
    ap.add_argument("--delay", type=float, default=0.6, help="请求间隔（秒）")
    ap.add_argument("--max-consecutive-failures", type=int, default=8)
    args = ap.parse_args()

    socket.setdefaulttimeout(30)
    fetch = SOURCES[args.source]
    src = os.path.join(args.out, "delisted_in_window.json")
    dst = os.path.join(args.out, "delisted_klines.json")

    with open(src, encoding="utf-8") as f:
        targets: List[Dict[str, str]] = json.load(f)

    print("=" * 84)
    print(f"抓取窗口内退市股日线 · 源={args.source} · {len(targets)} 只")
    print("=" * 84)

    out: Dict[str, List[List[Any]]] = {}
    if os.path.exists(dst):
        with open(dst, encoding="utf-8") as f:
            out = json.load(f)
        print(f"  已有 {len(out)} 只，续跑")

    consecutive = 0
    t0 = time.time()
    for i, item in enumerate(targets):
        code = item["code"]
        if out.get(code):
            continue
        try:
            rows = fetch(code, args.count)
            consecutive = 0
            out[code] = rows
        except SourceBlocked as exc:
            consecutive += 1
            print(f"  [{i+1}] {code} 源拒绝: {exc}（连续 {consecutive}）", flush=True)
            if consecutive >= args.max_consecutive_failures:
                print(f"\n  !! 连续 {consecutive} 次失败，中止（避免产出不完整结果）")
                break
            time.sleep(5.0)
            continue
        time.sleep(args.delay)
        if (i + 1) % 25 == 0:
            got = sum(1 for v in out.values() if v)
            print(f"  {i+1}/{len(targets)}  有数据 {got}  ({time.time()-t0:.0f}s)",
                  flush=True)

    got = sum(1 for v in out.values() if v)
    print(f"\n  完成: {got}/{len(targets)} 只有日线  ({time.time()-t0:.0f}s)")
    if got < len(targets) * 0.8:
        print("  !! 覆盖率不足 80%，可能被限流；结果**仍写入**但请复核")
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"  已保存 {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
