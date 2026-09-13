# -*- coding: utf-8 -*-
"""SQLite 持久化：连接、建表、写入、查重、列举。

由 tracking.py 拆分而来（对外 API 不变，实现下沉到 track/ 包）。
"""
import sqlite3
from datetime import date, datetime
from .schema import (
    _DB_PATH,
    _SCHEMA,
)



def get_conn(db_path=None):
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn



def init_db(conn):
    conn.executescript(_SCHEMA)
    conn.commit()



def _today():
    return date.today().strftime("%Y-%m-%d")



def add_recommendation(conn, rec):
    """插入一条推荐记录。rec: {code,name,rec_date,horizon,stance,score,logic}"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO recommendations"
        " (code,name,rec_date,horizon,stance,score,logic,created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (rec.get("code", ""), rec.get("name", ""),
         rec.get("rec_date") or _today(), rec.get("horizon", 5),
         rec.get("stance", "中性"), rec.get("score"), rec.get("logic"), now),
    )
    conn.commit()
    return cur.lastrowid



def find_duplicate(conn, code, rec_date, horizon):
    """幂等去重：同一 代码+推荐日期+周期 已存在记录时返回其 id，否则 None。"""
    row = conn.execute(
        "SELECT id FROM recommendations WHERE code=? AND rec_date=? AND horizon=?",
        (code, rec_date, horizon),
    ).fetchone()
    return row["id"] if row else None



def list_rows(conn, backfilled=None):
    """读取记录。backfilled: None=全部，True/False=按状态过滤。"""
    if backfilled is None:
        rows = conn.execute(
            "SELECT * FROM recommendations ORDER BY rec_date, id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM recommendations WHERE backfilled=? ORDER BY rec_date, id",
            (1 if backfilled else 0,)).fetchall()
    return [dict(r) for r in rows]
