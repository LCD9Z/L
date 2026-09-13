# -*- coding: utf-8 -*-
"""tracking.py - L3 回测闭环 · 推荐记录存储与校准统计（SQLite，零依赖）

表结构：
    recommendations：每次模型推荐一条记录；N 个交易日后用真实收盘价回填，计算收益率。
    通过 run_tracking.py 调用（log / backfill / stats / report）。

胜率口径：
    - 看多（含强烈看多）：N 日收益率 > 0 记为命中
    - 看空（含强烈看空）：N 日收益率 < 0 记为命中
    - 中性：不参与胜率，仅参与平均收益统计
"""
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict

_I0, _I1 = 0, 1

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracking.db")


@dataclass
class TrackingCosts:
    """回测交易成本参数，与 backtest_engine.Costs 口径一致。

    **计费基数**：backtest_engine / walk_forward / portfolio_backtest 均以
    「股数 × 价格」（100 股整手）作为名义金额计费。tracking 只记录单只推荐的
    收益率、没有组合资金概念，因此以 position_notional 作为基准仓位换算成本占比。

    这一点很关键：若直接用「每股价格」当名义金额，5 元最低佣金在高价股上会被
    放大到 0.33%（贵州茅台 1500 元时），而正确值约 0.03% —— 每笔收益率偏差
    可达 0.6 个百分点，足以让任何策略在统计上"看起来不赚钱"。
    """
    commission_rate: float = 0.0003   # 双边佣金费率
    min_commission: float = 5.0       # 单笔最低佣金（元）
    stamp_duty_sell: float = 0.0005   # 卖出印花税
    slippage_rate: float = 0.0005     # 滑点
    position_notional: float = 100_000.0   # 基准仓位（元），与 backtest_engine 默认初始资金一致

    def buy_cost(self, notional):
        """买入总成本 = 名义金额 + 佣金"""
        return notional + max(self.min_commission, notional * self.commission_rate)

    def sell_proceeds(self, notional):
        """卖出净收入 = 名义金额 - 佣金 - 印花税"""
        return notional - max(self.min_commission, notional * self.commission_rate) - notional * self.stamp_duty_sell

    def round_trip_cost_pct(self) -> float:
        """一次完整买卖的成本占基准仓位的比例（小数，如 0.0011 表示 0.11%）。"""
        n = self.position_notional
        if n <= 0:
            return 0.0
        buy_comm = max(self.min_commission, n * self.commission_rate)
        sell_comm = max(self.min_commission, n * self.commission_rate)
        stamp = n * self.stamp_duty_sell
        return (buy_comm + sell_comm + stamp) / n


def net_return_pct(rec_price, close_n, costs=None):
    """计算 N 日收益率（%）。

    costs=None  → **毛收益**：仅按收盘价计算，不含滑点与费用。
    costs=实例  → **净收益**：买入价加滑点、卖出价减滑点，再扣佣金与印花税。

    返回 None 表示数据不足，不参与统计。
    """
    if not rec_price or close_n is None:
        return None
    if costs is None:
        return round((close_n / rec_price - 1) * 100, 2)
    buy_px = rec_price * (1 + costs.slippage_rate)
    sell_px = close_n * (1 - costs.slippage_rate)
    if not buy_px:
        return None
    gross = (sell_px - buy_px) / buy_px
    return round((gross - costs.round_trip_cost_pct()) * 100, 2)

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


def stance_bucket(stance):
    if stance in ("强烈看多", "看多"):
        return "看多"
    if stance in ("强烈看空", "看空"):
        return "看空"
    return "中性"


def is_hit(return_pct, bucket):
    """看多：收益>0 命中；看空：收益<0 命中；中性返回 None。"""
    if return_pct is None:
        return None
    if bucket == "看多":
        return 1.0 if return_pct > 0 else 0.0
    if bucket == "看空":
        return 1.0 if return_pct < 0 else 0.0
    return None


def _norm_date(s):
    """统一日期为 YYYYMMDD（去连字符），便于字符串比较。None 原样返回。"""
    if not s:
        return s
    return str(s).replace("-", "")


def find_base_and_close(klines, rec_date, horizon):
    """在正序 K 线中定位基准根（>= rec_date 的第一根）与 N 交易日后收盘。

    返回 (rec_price, close_n)；close_n 为 None 表示未满 N 根（仍待回填）。
    日期比较统一去连字符，兼容东财(YYYY-MM-DD)与本地兜底(YYYYMMDD)两种格式。
    """
    target = _norm_date(rec_date)
    i_base = -1
    for idx, r in enumerate(klines):
        if _norm_date(r["date"]) >= target:
            i_base = idx
            break
    if i_base < 0:
        return None, None
    rec_price = klines[i_base]["close"]
    j = i_base + horizon
    if j >= len(klines):
        return rec_price, None
    return rec_price, klines[j]["close"]


def backfill_pending(conn, today=None, horizon_override=None, costs=None,
                     apply_costs=True):
    """回填所有待回填记录：拉取推荐日至今的日K，计算 N 日收益率。

    收益率口径：
        apply_costs=True （默认）→ 净收益：含滑点、佣金与印花税
        apply_costs=False        → 毛收益：仅按收盘价计算，不含任何成本

    costs=None 时使用 TrackingCosts 默认参数；如需自定义费率，
    传入对应的 TrackingCosts 实例。

    返回 (已完成条数, 仍待回填条数)。
    """
    import data_fetcher as df
    # 注意：不能用 `costs = costs or TrackingCosts()` —— 那样 apply_costs=False
    # 时仍会被赋回默认成本，导致"毛收益"开关失效。
    eff_costs = (costs or TrackingCosts()) if apply_costs else None
    today = today or _today()
    pending = list_rows(conn, backfilled=False)
    done = 0
    still = 0
    for r in pending:
        hz = horizon_override or r.get("horizon") or 5
        beg = r["rec_date"].replace("-", "")
        end = today.replace("-", "")
        klines = df.fetch_kline(r["code"], beg=beg, end=end)
        rec_price, close_n = find_base_and_close(klines, r["rec_date"], hz)
        if rec_price is None:
            still += 1
            continue
        if close_n is None:
            conn.execute(
                "UPDATE recommendations SET rec_price=?, backfill_date=? WHERE id=?",
                (rec_price, today, r["id"]),
            )
            still += 1
        else:
            ret = net_return_pct(rec_price, close_n, eff_costs)
            conn.execute(
                "UPDATE recommendations SET backfilled=1, rec_price=?, close_n=?,"
                " return_pct=?, backfill_date=? WHERE id=?",
                (rec_price, close_n, ret, today, r["id"]),
            )
            done += 1
    conn.commit()
    return done, still


def compute_stats(conn):
    """校准统计：按（周期×档位）聚合胜率/平均收益；按评分档聚合平均收益。

    返回 dict：{"5日-看多": {"样本数":..,"胜率%":..,"平均收益%":..}, ...}
    """
    rows = list_rows(conn, backfilled=True)
    # 每个 cell 形如 {"n": int, "hit": int, "rets": list[float]}；by_score 无 "hit"
    by_bucket: Dict[str, Dict[str, Any]] = {}
    by_score: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        hz = r.get("horizon") or 5
        b = stance_bucket(r.get("stance", ""))
        key = f"{hz}日-{b}"
        cell = by_bucket.setdefault(key, {"n": 0, "hit": 0, "rets": []})
        cell["n"] += 1
        h = is_hit(r.get("return_pct"), b)
        if h is not None:
            cell["hit"] += h
            if r.get("return_pct") is not None:
                cell["rets"].append(r["return_pct"])
        sc = r.get("score")
        if sc is not None:
            if sc >= 7.5:
                sb = "高分(≥7.5)"
            elif sc >= 4:
                sb = "中分(4-7.5)"
            else:
                sb = "低分(<4)"
            scell = by_score.setdefault(sb, {"n": 0, "rets": []})
            scell["n"] += 1
            if r.get("return_pct") is not None:
                scell["rets"].append(r["return_pct"])
    out: Dict[str, Dict[str, Any]] = {}
    for k, c in by_bucket.items():
        win = round(c["hit"] / c["n"] * 100, 1) if c["n"] else None
        avg = round(sum(c["rets"]) / len(c["rets"]), 2) if c["rets"] else None
        # 看空档位：收益取负号展示为"方向收益%"，方向一致才为正
        # （看空命中=股票下跌=原收益<0，取负后为正，与胜率语义一致）
        if k.endswith("-看空") and avg is not None:
            out[k] = {"样本数": c["n"], "胜率%": win, "方向收益%": round(-avg, 2)}
        else:
            out[k] = {"样本数": c["n"], "胜率%": win, "平均收益%": avg}
    for k, c in by_score.items():
        avg = round(sum(c["rets"]) / len(c["rets"]), 2) if c["rets"] else None
        out["评分:" + k] = {"样本数": c["n"], "平均收益%": avg, "胜率%": None}
    return out


if __name__ == "__main__":
    conn = get_conn()
    init_db(conn)
    print("tracking.db 已初始化")
