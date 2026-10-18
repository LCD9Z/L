# -*- coding: utf-8 -*-
r"""单股 walk-forward 对比 CLI（L1 遗留）：`walk_forward.compare` 的前后段对照。

依赖 `data_fetcher.fetch_kline`（腾讯源，需网络），**与 `tdx_native` 生产链无关**。
保留为历史凭据；多窗口样本外检验走 `scripts/run_tdx_rolling_eval.py`。

⚠️ 本文件原本**无 `__main__` 守卫**（import 即执行）。2026-10-18 补守卫。
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, json


def main():
    from data_fetcher import fetch_kline
    from walk_forward import compare
    p = argparse.ArgumentParser()
    p.add_argument('code')
    p.add_argument('--limit', type=int, default=500)
    p.add_argument('--threshold', type=float, default=70)
    p.add_argument('--horizon', type=int, default=5)
    p.add_argument('--out')
    a = p.parse_args()
    bars = fetch_kline(a.code, limit=a.limit, min_quality='medium')
    if not bars:
        raise SystemExit('无法获取足够的高质量历史数据')
    r = compare(a.code, bars, threshold=a.threshold, horizon=a.horizon)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
