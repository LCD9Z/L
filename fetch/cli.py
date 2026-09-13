# -*- coding: utf-8 -*-
"""命令行入口（`python data_fetcher.py <code> --news N [--json]`）。

由 data_fetcher.py 拆分而来（对外 API 不变，实现下沉到 fetch/ 包）。

无位置参数时 `main()` 会打印本 docstring，故此处保留与拆分前等价的用法说明：

    python data_fetcher.py 600519 --news 5     # 打印事实数据包
    python data_fetcher.py sh600519 --json     # 输出 JSON 结构
"""
import json
import sys
from .common import (
    _I0,
    _I1,
)
from .news import (
    build_fact_sheet,
    fact_sheet_to_text,
)



def main():
    args = [a for a in sys.argv[_I1:] if not a.startswith("--")]
    news_limit = 5
    if "--news" in sys.argv:
        idx = sys.argv.index("--news")
        try:
            news_limit = int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            news_limit = 5
    if not args:
        print(__doc__)
        return
    code = args[_I0]
    sheet = build_fact_sheet(code, news_limit=news_limit)
    if "--json" in sys.argv:
        print(json.dumps(sheet, ensure_ascii=False, indent=2))
    else:
        print(fact_sheet_to_text(sheet))
