# -*- coding: utf-8 -*-
"""迁移 lost 系工作目录的 L3 推荐记录到本项目 tracking.db。

规则：
- 只迁移真实推荐（logic 含「演示」的种子记录排除，避免污染校准统计）；
- 目标库按 (code, rec_date, horizon) 幂等去重；
- rec_price/backfilled 等回填字段**不迁移**（由本项目 L3 用现行成本口径重新回填）。
"""
from __future__ import annotations

import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tracking  # noqa: E402

SOURCES = [
    r"D:\ai-stock-god-clean\tracking.db",
    r"D:\ai-stock-god\ai-stock-god\tracking.db",
]


def main() -> int:
    conn = sqlite3.connect(tracking._DB_PATH)
    conn.row_factory = sqlite3.Row
    tracking.init_db(conn)
    existing = {(r["code"], r["rec_date"], r["horizon"])
                for r in conn.execute("SELECT code, rec_date, horizon FROM recommendations")}
    migrated = skipped_demo = skipped_dup = 0
    for src in SOURCES:
        if not os.path.exists(src):
            print(f"跳过（不存在）: {src}")
            continue
        s = sqlite3.connect(src)
        s.row_factory = sqlite3.Row
        for r in s.execute("SELECT * FROM recommendations"):
            logic = r["logic"] or ""
            if "演示" in logic:
                skipped_demo += 1
                continue
            key = (r["code"], r["rec_date"], r["horizon"])
            if key in existing:
                skipped_dup += 1
                continue
            tracking.add_recommendation(conn, {
                "code": r["code"], "name": r["name"], "rec_date": r["rec_date"],
                "horizon": r["horizon"], "stance": r["stance"], "score": r["score"],
                "logic": f"[迁移自 {src.split(chr(92))[-2]}] {logic}".strip(),
            })
            existing.add(key)
            migrated += 1
        s.close()
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM recommendations WHERE backfilled=0").fetchone()[0]
    conn.close()
    print(f"迁移 {migrated} 条；排除演示 {skipped_demo} 条；重复 {skipped_dup} 条")
    print(f"目标库现有 {total} 条（待回填 {pending} 条）: {tracking._DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
