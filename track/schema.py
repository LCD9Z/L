# -*- coding: utf-8 -*-
"""常量与表结构：索引常量、默认库路径、SQLite 建表语句、立场映射。

由 tracking.py 拆分而来（对外 API 不变，实现下沉到 track/ 包）。
"""
import os


_I0, _I1 = 0, 1



_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tracking.db")  # 注：本包在项目根下一层，故再取一层父目录，保持 tracking.db 位于项目根



_SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT,
    rec_date TEXT NOT NULL,
    horizon INTEGER NOT NULL DEFAULT 5,
    stance TEXT NOT NULL,
    score REAL,
    logic TEXT,
    rec_price REAL,
    backfilled INTEGER DEFAULT 0,
    close_n REAL,
    return_pct REAL,
    backfill_date TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending ON recommendations(backfilled, rec_date);
"""



# 交易指令 → 建议档位
STANCE_MAP = {
    "强烈买入": "强烈看多",
    "买入": "看多",
    "持有": "中性",
    "卖出": "看空",
    "强烈卖出": "强烈看空",
}
