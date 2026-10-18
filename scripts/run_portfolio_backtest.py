# -*- coding: utf-8 -*-
r"""多股组合回测 CLI（Phase 5，L1/L2 遗留）：读 universe JSON，逐股取数后跑组合回测。

依赖 `data_fetcher` / `historical_universe` / `portfolio_backtest`（均为根目录 L1 模块），
需网络（腾讯源）。**与 `tdx_native` 生产链无关**，保留为历史凭据。

⚠️ 本文件原本**无 `__main__` 守卫**（import 即执行 argparse）。
2026-10-18 补守卫 —— 与 `scripts/REGISTRY.md` 的「导入」列对应。
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, json


def main():
    from data_fetcher import fetch_kline
    from historical_universe import load_codes
    from portfolio_backtest import portfolio_backtest
    from regime.regime_backtest_report import evaluate_backtest
    p = argparse.ArgumentParser()
    p.add_argument('universe_json')
    p.add_argument('--limit', type=int, default=500)
    p.add_argument('--top-n', type=int, default=5)
    p.add_argument('--threshold', type=float, default=70)
    p.add_argument('--horizon', type=int, default=5)
    p.add_argument('--out')
    a = p.parse_args()
    data = {}
    for c in load_codes(a.universe_json):
        bars = fetch_kline(c, limit=a.limit, min_quality='medium')
        if bars:
            data[c] = bars
    r = portfolio_backtest(data, threshold=a.threshold, top_n=a.top_n, horizon=a.horizon)
    r['phase9_diagnostics'] = evaluate_backtest(r)
    print(json.dumps({k: v for k, v in r.items() if k not in ('trade_log', 'equity_curve')},
                     ensure_ascii=False, indent=2))
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
