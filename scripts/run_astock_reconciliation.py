# -*- coding: utf-8 -*-
"""抽样对账：`a-stock-data` 的行情层 vs 我方通达信原生 `.day`。

## 为什么做这个

`ASTOCK_DATA_ASSESSMENT.md` §六 P0 要求：**引用前必须先对账**。
理由是该工具自己出过长期错误（V3.10.1 更正「科创板成交量单位是**股**而非**手**，
此前文档全写错，照旧换算会**大 100 倍**」）—— **它的文档不可全信，数据必须自证**。

## 对账口径（严格照它的契约）

- 端点：`/appstock/app/fqkline/get`，param = `<symbol>,day,,,<count>,<adjust>`
- **`adjust=''`（不复权）** —— 因为通达信原生 `.day` 是不复权价，前复权（qfq）不可直接比
- 成交量单位：**科创板（688/689）是「股」，其余是「手」** → 与通达信（股）比对时其余板块需 ×100
- 它**没有成交额**（其文档自述），故本次**只对账 OHLC 与成交量，不对账成交额**

## 判定（事前固定）

| 结论 | 条件 |
|------|------|
| **一致** | 日期序列完全相同，且 OHLC 最大绝对差 ≤ 0.01 元、成交量相对差 ≤ 0.1% |
| **基本一致** | 日期序列相同，OHLC 差 ≤ 0.05 元、量差 ≤ 1% |
| **不一致** | 超出上述任一 |

用法：
    python scripts/run_astock_reconciliation.py --count 120
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tdx_native.day_reader import read_day_tail  # noqa: E402

HOSTS = ("https://web.ifzq.gtimg.cn",
         "https://proxy.finance.qq.com/ifzqgtimg",
         "https://ifzq.gtimg.cn")
PATH = "/appstock/app/fqkline/get"

#: 覆盖各板块与「除权多/少」两类
SAMPLES: Tuple[Tuple[str, str, str], ...] = (
    ("sh600519", "沪主板 · 贵州茅台 · 高分红（除权多）", "sh"),
    ("sz000001", "深主板 · 平安银行", "sz"),
    ("sz300750", "创业板 · 宁德时代", "sz"),
    ("sh688981", "科创板 · 中芯国际 · **量单位是股**", "sh"),
    ("sz002594", "深主板 · 比亚迪", "sz"),
)


def _fetch(symbol: str, count: int, timeout: int = 25) -> Optional[dict]:
    """按 a-stock-data 的契约取不复权日线；三个入口依次尝试。"""
    param = f"{symbol},day,,,{count},"          # 末位空 = 不复权
    errs = []
    for host in HOSTS:
        url = f"{host}{PATH}?param={param}"
        req = urllib.request.Request(url, headers={
            "Referer": "https://gu.qq.com/",
            "User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", errors="replace")
            d = json.loads(body)
            node = (d.get("data") or {}).get(symbol)
            if isinstance(node, dict) and isinstance(node.get("day"), list) and node["day"]:
                return {"rows": node["day"], "host": host}
            errs.append(f"{host}: 无 day 数据")
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
            errs.append(f"{host}: {type(e).__name__}")
        time.sleep(0.4)
    print(f"    ⚠️ 取数失败 —— {'; '.join(errs)}")
    return None


def _norm_vol(symbol: str, raw: float) -> float:
    """腾讯量 → 股。科创板（688/689）本来就是股，其余是手。"""
    code = symbol[2:]
    return float(raw) if code.startswith(("688", "689")) else float(raw) * 100.0


def reconcile_one(symbol: str, label: str, market: str, count: int) -> Dict[str, Any]:
    print(f"\n── {symbol}  {label}")
    got = _fetch(symbol, count)
    if got is None:
        return {"symbol": symbol, "status": "FETCH_FAILED"}

    tencent: Dict[str, List[float]] = {}
    for row in got["rows"]:
        # 腾讯行序：[date, open, close, high, low, volume, ...]
        tencent[str(row[0])] = [float(row[1]), float(row[3]), float(row[4]),
                                float(row[2]), float(row[5])]  # o,h,l,c,v

    day_path = os.path.join("D:/new_tdx/vipdoc", market, "lday", f"{symbol}.day")
    if not os.path.exists(day_path):
        print(f"    ⚠️ 本机无原生文件：{day_path}")
        return {"symbol": symbol, "status": "NO_LOCAL"}
    local_bars = read_day_tail(day_path, n=count + 40)

    local: Dict[str, List[float]] = {}
    for b in local_bars:
        d = str(b["date"])
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        local[ds] = [float(b["open"]), float(b["high"]), float(b["low"]),
                     float(b["close"]), float(b["volume"])]

    t_dates = sorted(tencent)
    l_dates = sorted(local)
    common = sorted(set(t_dates) & set(l_dates))
    print(f"    腾讯 {len(t_dates)} 根（{t_dates[0]}~{t_dates[-1]}，入口 {got['host']}）")
    print(f"    本地 {len(l_dates)} 根（{l_dates[0]}~{l_dates[-1]}）")
    print(f"    日期交集 {len(common)} 根")

    if len(common) < 20:
        return {"symbol": symbol, "status": "TOO_FEW_COMMON", "n_common": len(common)}

    # ① 日期序列：**只在共同区间内**比对。
    # ⚠️ 首版 bug：腾讯的日线比本机盘后包**更新**（实测腾讯到 2026-10-09，本地只到 2026-09-30），
    # 尾部会多出本地没有的交易日 → 直接比较两条完整序列会**误判为「不一致」**。
    # 修正：截到 `[common[0], common[-1]]` 再比，并把腾讯多出的日期单独报出来（那是它的优点，不是缺陷）。
    lo, hi = common[0], common[-1]
    tail_t = [d for d in t_dates if lo <= d <= hi]
    tail_l = [d for d in l_dates if lo <= d <= hi]
    dates_equal = tail_t == tail_l
    extra_t = [d for d in t_dates if d > hi]
    extra_l = [d for d in l_dates if d > hi]

    # ② OHLC 绝对差
    max_px = 0.0
    px_date = ""
    # ③ 成交量相对差
    max_vr = 0.0
    vr_date = ""
    for d in common:
        t, l = tencent[d], local[d]
        for k in range(4):
            diff = abs(t[k] - l[k])
            if diff > max_px:
                max_px, px_date = diff, d
        tv = _norm_vol(symbol, t[4])
        if l[4] > 0:
            vr = abs(tv - l[4]) / l[4]
            if vr > max_vr:
                max_vr, vr_date = vr, d

    verdict = ("一致" if (dates_equal and max_px <= 0.01 and max_vr <= 0.001)
               else "基本一致" if (dates_equal and max_px <= 0.05 and max_vr <= 0.01)
               else "不一致")
    print(f"    日期序列（共同区间内）: {'相同 ✓' if dates_equal else '不同 ✗'}")
    if extra_t:
        print(f"    ⓘ 腾讯多出 {len(extra_t)} 个交易日（本地盘后包未更新）: "
              f"{extra_t[0]} ~ {extra_t[-1]}")
    if extra_l:
        print(f"    ⓘ 本地多出 {len(extra_l)} 个交易日: {extra_l[0]} ~ {extra_l[-1]}")
    print(f"    OHLC 最大绝对差  : {max_px:.4f} 元 @ {px_date or '—'}")
    print(f"    成交量最大相对差 : {max_vr:.4%} @ {vr_date or '—'}")
    print(f"    → 判定: {verdict}")

    return {"symbol": symbol, "status": "OK", "verdict": verdict,
            "n_common": len(common), "dates_equal": dates_equal,
            "n_extra_tencent": len(extra_t),
            "extra_tencent_range": ([extra_t[0], extra_t[-1]] if extra_t else None),
            "max_px_diff": round(max_px, 6), "px_date": px_date,
            "max_vol_rel": round(max_vr, 8), "vol_date": vr_date,
            "host": got["host"]}


def main() -> int:
    ap = argparse.ArgumentParser(description="a-stock-data 行情层 vs 通达信原生 抽样对账")
    ap.add_argument("--count", type=int, default=120)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    print("=" * 74)
    print("a-stock-data 行情层 vs 通达信原生 .day —— 抽样对账")
    print("口径：adjust='' 不复权 · 科创板量单位=股、其余=手 · 不对账成交额（它无此字段）")
    print("=" * 74)

    results = [reconcile_one(s, lbl, mkt, args.count) for s, lbl, mkt in SAMPLES]

    print("\n" + "=" * 74)
    print("汇总")
    print("=" * 74)
    print(f"{'代码':<12}{'判定':<12}{'交集':>6}{'日期序列':>10}{'OHLC最大差':>12}{'量最大相对差':>14}")
    for r in results:
        if r.get("status") != "OK":
            print(f"{r['symbol']:<12}{r['status']:<12}")
            continue
        print(f"{r['symbol']:<12}{r['verdict']:<12}{r['n_common']:>6}"
              f"{('相同' if r['dates_equal'] else '不同'):>10}"
              f"{r['max_px_diff']:>12.4f}{r['max_vol_rel']:>13.4%}")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"count": args.count, "results": results},
                      fh, ensure_ascii=False, indent=1)
        print(f"\n已写入: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
