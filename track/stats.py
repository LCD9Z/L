# -*- coding: utf-8 -*-
"""校准统计：立场/命中判定、基准与收盘价回填、胜率与平均收益汇总。

由 tracking.py 拆分而来（对外 API 不变，实现下沉到 track/ 包）。
"""
from typing import Any, Dict
from .costs import (
    TrackingCosts,
    net_return_pct,
)
from .store import (
    _today,
    list_rows,
)



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
            ret = net_return_pct(rec_price, close_n, eff_costs, as_of=r["rec_date"])
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
