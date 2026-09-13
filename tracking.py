# -*- coding: utf-8 -*-
"""tracking.py - L3 回测闭环 · 推荐记录存储与校准统计（SQLite，零依赖） · 门面模块。

历史上全部逻辑集中在本文件（308 行）。现按职责拆分到 `track/` 包：

    track/costs.py   交易成本模型（TrackingCosts）与净收益率换算
    track/schema.py  常量与表结构（默认库路径、建表语句、立场映射）
    track/store.py   SQLite 持久化（连接 / 建表 / 写入 / 查重 / 列举）
    track/stats.py   校准统计（命中判定 / 回填 / 胜率与平均收益）

本模块重新导出全部既有符号，**`import tracking` + `tracking.X(...)`
以及 `from tracking import X` 的用法完全不变**。

表结构：
    recommendations：每次模型推荐一条记录；N 个交易日后用真实收盘价回填，计算收益率。
    通过 run_tracking.py 调用（log / backfill / stats / report）。

胜率口径：
    - 看多（含强烈看多）：N 日收益率 > 0 记为命中
    - 看空（含强烈看空）：N 日收益率 < 0 记为命中
    - 中性：不参与胜率，仅参与平均收益统计
"""

from track.costs import (
    TrackingCosts,
    net_return_pct,
)
from track.schema import (
    STANCE_MAP,
    _DB_PATH,
    _SCHEMA,
)
from track.stats import (
    _norm_date,
    backfill_pending,
    compute_stats,
    find_base_and_close,
    is_hit,
    stance_bucket,
)
from track.store import (
    _today,
    add_recommendation,
    find_duplicate,
    get_conn,
    init_db,
    list_rows,
)

__all__ = [
    "STANCE_MAP",
    "_DB_PATH",
    "_SCHEMA",
    "TrackingCosts",
    "_norm_date",
    "_today",
    "add_recommendation",
    "backfill_pending",
    "compute_stats",
    "find_base_and_close",
    "find_duplicate",
    "get_conn",
    "init_db",
    "is_hit",
    "list_rows",
    "net_return_pct",
    "stance_bucket",
]


if __name__ == "__main__":
    conn = get_conn()
    init_db(conn)
    print("tracking.db 已初始化")
