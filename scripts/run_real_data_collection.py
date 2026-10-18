# -*- coding: utf-8 -*-
r"""真实行情采集 CLI（L1 遗留）：按 `--symbols` 列表取材并落盘到 `real_data/`。

依赖根目录 L1 模块 `real_data_collector.acquire_universe`，**与 `tdx_native` 生产链无关**。
保留为历史凭据；生产取数走 `scripts/fetch_delisted_full.py` / `scripts/fetch_baostock_xsrc.py`。

⚠️ 本文件原本**无 `__main__` 守卫**（import 即执行）。2026-10-18 补守卫。
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, json


def main():
    from real_data_collector import acquire_universe
    p = argparse.ArgumentParser()
    p.add_argument('--symbols', required=True, help='comma-separated A-share codes')
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    p.add_argument('--out', default='real_data')
    a = p.parse_args()
    result = acquire_universe([x.strip() for x in a.symbols.split(',') if x.strip()],
                              a.start, a.end, a.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
