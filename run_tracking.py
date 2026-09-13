# -*- coding: utf-8 -*-
"""run_tracking.py - L3 回测闭环 CLI

用法：
    # 记录一条推荐（手动填字段）
    python run_tracking.py log --code 600519 --name 贵州茅台 --date 2026-08-25 \
        --horizon 5 --stance 看多 --score 7 --logic "多空独立论证后看多"

    # 从风控/交易决策 JSON 自动提取（08_risk.json 或 07_trade.json）
    python run_tracking.py log --json reports/xxx/08_risk.json --horizon 5

    # 回填：拉取推荐日后 N 个交易日的真实收盘价并计算收益率
    python run_tracking.py backfill

    # 统计：按周期×档位、按评分档 汇总胜率与平均收益
    python run_tracking.py stats

    # 输出校准报告数据（JSON，供可视化与存档）
    python run_tracking.py report --out reports/tracking_report.json
"""
import argparse
import json
import os
from datetime import datetime

import tracking
from tracking import STANCE_MAP

_I0, _I1, _I4 = 0, 1, 4


def _extract_from_result(path):
    """从 07_trade / 08_risk 决策结果 JSON 提取推荐字段。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read().strip()
    # 兼容模型输出的 ```json ... ``` 围栏
    if raw.startswith("```"):
        inner = raw.split("```")[_I1]
        if inner.startswith("json"):
            inner = inner[_I4:]
        raw = inner.strip()
    d = json.loads(raw)
    code = d.get("股票代码") or d.get("code") or ""
    cmd = (d.get("最终交易指令") or d.get("交易指令")
           or d.get("final_action") or "")
    stance = STANCE_MAP.get(cmd, cmd or "中性")
    score = d.get("风险等级") or d.get("信心评分") or d.get("score")
    logic = d.get("一票否决理由") or d.get("关键执行条件") or ""
    if isinstance(logic, list):
        logic = "；".join(str(x) for x in logic)
    return {
        "code": code,
        "stance": stance,
        "score": score,
        "logic": str(logic),
        "raw": json.dumps(d, ensure_ascii=False),
    }


def cmd_log(args):
    conn = tracking.get_conn(args.db)
    tracking.init_db(conn)
    if args.json:
        rec = _extract_from_result(args.json)
        if args.code:
            rec["code"] = args.code
        if args.name:
            rec["name"] = args.name
        if args.horizon:
            rec["horizon"] = args.horizon
        if args.date:
            rec["rec_date"] = args.date
        if args.stance:
            rec["stance"] = args.stance
        if args.score is not None:
            rec["score"] = args.score
    else:
        rec = {
            "code": args.code or "",
            "name": args.name,
            "rec_date": args.date or tracking._today(),
            "horizon": args.horizon or 5,
            "stance": args.stance or "中性",
            "score": args.score,
            "logic": args.logic,
        }
    rid = tracking.add_recommendation(conn, rec)
    print(f"已记录推荐 #{rid}：{rec.get('code')} {rec.get('stance')} "
          f"周期{rec.get('horizon')}日 评分{rec.get('score')}")


def cmd_backfill(args):
    conn = tracking.get_conn(args.db)
    tracking.init_db(conn)
    # 用 apply_costs 显式表达口径：此前传 costs=None 会被 backfill_pending
    # 内部 `costs or TrackingCosts()` 覆盖，导致 --gross 实际未生效。
    done, still = tracking.backfill_pending(
        conn, today=args.today, horizon_override=args.horizon,
        apply_costs=not args.gross)
    basis = "毛收益(不含成本)" if args.gross else "净收益(含佣金/印花税/滑点)"
    print(f"回填完成：{done} 条已完成；{still} 条仍待回填"
          f"（未满 {args.horizon or '默认'} 个交易日）；口径={basis}")


def cmd_stats(args):
    conn = tracking.get_conn(args.db)
    tracking.init_db(conn)
    rows = tracking.list_rows(conn)
    done_rows = [r for r in rows if r["backfilled"]]
    print(f"推荐记录：{len(rows)} 条（已回填 {len(done_rows)} 条）")
    stats = tracking.compute_stats(conn)
    if not stats:
        print("暂无已回填样本，先执行 log + backfill。")
        return
    print("\n按周期×档位：")
    for k, v in sorted(stats.items()):
        if k.startswith("评分:"):
            continue
        print(f"  {k}: {v}")
    print("\n按评分档：")
    for k, v in sorted(stats.items()):
        if k.startswith("评分:"):
            print(f"  {k}: {v}")


def cmd_report(args):
    conn = tracking.get_conn(args.db)
    tracking.init_db(conn)
    stats = tracking.compute_stats(conn)
    rows = tracking.list_rows(conn)
    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(rows),
        "backfilled": len([r for r in rows if r["backfilled"]]),
        "stats": stats,
        "records": rows,
    }
    out = args.out or "reports/tracking_report.json"
    d = os.path.dirname(out) or "."
    os.makedirs(d, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"校准报告已生成：{out}")
    print(f"  样本 {data['total']} 条，已回填 {data['backfilled']} 条")


def main():
    parser = argparse.ArgumentParser(description="AI股神 · L3 回测闭环")
    sub = parser.add_subparsers(dest="cmd")

    p_log = sub.add_parser("log", help="记录推荐")
    p_log.add_argument("--code")
    p_log.add_argument("--name")
    p_log.add_argument("--date")
    p_log.add_argument("--horizon", type=int)
    p_log.add_argument("--stance",
                      choices=["强烈看多", "看多", "中性", "看空", "强烈看空"])
    p_log.add_argument("--score", type=float)
    p_log.add_argument("--logic")
    p_log.add_argument("--json", help="从 07/08 决策结果 JSON 提取")
    p_log.add_argument("--db", default=None)
    p_log.set_defaults(func=cmd_log)

    p_bf = sub.add_parser("backfill", help="回填真实收盘价")
    p_bf.add_argument("--today")
    p_bf.add_argument("--horizon", type=int)
    p_bf.add_argument("--gross", action="store_true",
                      help="按毛收益回填（不含佣金/印花税/滑点），默认按净收益口径")
    p_bf.add_argument("--db", default=None)
    p_bf.set_defaults(func=cmd_backfill)

    p_st = sub.add_parser("stats", help="统计胜率/平均收益")
    p_st.add_argument("--db", default=None)
    p_st.set_defaults(func=cmd_stats)

    p_rp = sub.add_parser("report", help="输出校准报告 JSON")
    p_rp.add_argument("--out")
    p_rp.add_argument("--db", default=None)
    p_rp.set_defaults(func=cmd_report)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
