# -*- coding: utf-8 -*-
"""每日选股推荐执行脚本（真实选股，非演示）。

1.0 起按职责拆分，本文件保留编排与入口：

    runtime_env.py       路径 / 日志 / 配置加载（无项目内依赖）
    stock_scoring.py     透明规则打分（纯函数，可单独测试）
    pool_manager.py      股票池自动维护（方案A）
    industry_context.py  行业相对强度集成（Phase 8）
    lark_notify.py       飞书写表 + 消息推送
    daily_stock_pick.py  本文件：编排 + 深析 + 落盘 + 入口

流程：
  1. 读取股票池（默认 ~/.ai-stock-god/watchlist.json，可用 AI_STOCK_WATCHLIST_FILE 覆盖）
  2. 对每只股票拉取实时行情 + 近 70 根日K（data_fetcher）
  3. 透明规则打分（涨跌幅/换手/5日趋势/突破/风险/周期阶段）并排序
  4. 对 Top N 调用 run_analysis.py --auto 做 L4 深度分析（可选 --no-deep 关闭）
  5. 汇总写飞书多维表格 + 推送飞书消息

用法：
    python daily_stock_pick.py                 # 选股 + Top3 深析 + 写表格 + 推送
    python daily_stock_pick.py --no-deep       # 仅规则选股，不跑模型深析
    python daily_stock_pick.py --dry-run       # 试运行：只打分并打印，无任何持久化副作用
    python daily_stock_pick.py --no-pool-update # 跳过股票池自动维护

--dry-run 的语义（已由 test_dry_run_safety.py 守卫）：
    不写 tracking.db、不更新股票池、不写飞书表格、不推送；
    仅保留本地日报 JSON（reports/daily/screening_*.json）供人工检查。
"""
import json
import os
import subprocess
import sys
from datetime import datetime

from data_fetcher import fetch_kline
from market_regime import get_market_regime
from risk.a_share_risk import position_plan
import tracking

from runtime.runtime_env import (
    CANDIDATE_FILE,
    CONFIG_FILE,
    LOG_FILE,
    POOL_STATE_FILE,
    REPORT_DIR,
    STATE_DIR,
    WATCHLIST_FILE,
    WORK_DIR,
    load_config,
    load_watchlist,
    log,
)
from stock_scoring import score_stock
from pool_manager import update_watchlist
from industry_context import apply_industry_context, build_industry_context
from notify.lark_notify import add_records_to_base, send_push

__all__ = [
    "CANDIDATE_FILE",
    "CONFIG_FILE",
    "LOG_FILE",
    "POOL_STATE_FILE",
    "REPORT_DIR",
    "STATE_DIR",
    "WATCHLIST_FILE",
    "WORK_DIR",
    "add_records_to_base",
    "apply_industry_context",
    "build_industry_context",
    "load_config",
    "load_watchlist",
    "log",
    "main",
    "run_deep_analysis",
    "save_tracking_records",
    "save_unified_report",
    "score_stock",
    "send_push",
    "update_watchlist",
]


def run_deep_analysis(code):
    """对单股调用 run_analysis.py --auto，返回结果目录与最终决策。"""
    log("对 %s 启动 L4 深度分析..." % code)
    cmd = [sys.executable, os.path.join(WORK_DIR, "run_analysis.py"), code, "--auto"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=WORK_DIR,
            encoding="utf-8", errors="replace", timeout=1800
        )
        out = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return "", "深度分析超时"
    # 从输出中提取结果目录与最终决策
    report_dir = ""
    decision = ""
    for line in out.splitlines():
        if "结果目录" in line and "reports" in line:
            report_dir = line.split("：", 1)[-1].strip()
        if line.startswith("  最终交易指令"):
            decision = line.split(":", 1)[-1].strip()
        if line.startswith("  最终仓位建议"):
            decision += " | 仓位:" + line.split(":", 1)[-1].strip()
    log("深析完成 code=%s dir=%s decision=%s" % (code, report_dir, decision))
    return report_dir, decision


def save_tracking_records(stocks, horizon=5):
    """Phase 10 集成：每日推荐写入 SQLite，后续由回填任务验证真实表现。"""
    conn = tracking.get_conn()
    try:
        tracking.init_db(conn)
        rec_date = datetime.now().strftime("%Y-%m-%d")
        for s in stocks:
            code = s.get("股票代码")
            if not code or tracking.find_duplicate(conn, code, rec_date, horizon):
                continue
            advice = s.get("投资建议", "观望")
            stance = "看多" if advice in ("重点关注", "关注") else "中性"
            tracking.add_recommendation(conn, {"code": code, "name": s.get("股票名称"),
                "rec_date": rec_date, "horizon": horizon, "stance": stance,
                "score": s.get("综合评分"), "logic": s.get("核心逻辑", "")[:1000]})
    finally:
        conn.close()


def save_unified_report(stocks, market, rankings, out_file):
    """Phase 10 统一日报：市场→行业→个股→风控→跟踪闭环。"""
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "market": market,
        "industry_rankings": rankings,
        "stocks": stocks,
        "disclaimer": "仅供研究和辅助决策，不构成任何投资建议。",
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main():
    dry = "--dry-run" in sys.argv
    deep = "--no-deep" not in sys.argv
    pool_update = "--no-pool-update" not in sys.argv

    log("=" * 60)
    log("每日选股开始（deep=%s, dry=%s）" % (deep, dry))

    cfg = load_watchlist()
    market = get_market_regime()
    log("市场环境：%s | %s" % (market.get("regime"), market.get("note", "")))
    rankings, industry_map = build_industry_context(cfg["watchlist"])
    if rankings:
        log("行业强度Top3：%s" % ", ".join("%s(%s%%)" % (x["industry"], x["percentile"]) for x in rankings[:3]))
    stocks = []
    for item in cfg["watchlist"]:
        try:
            r = score_stock(item, market)
            r = apply_industry_context(r, rankings, industry_map)
            log("打分 %s %s -> %s" % (item["code"], r["股票名称"], r["综合评分"]))
            stocks.append(r)
        except Exception as e:
            log("打分失败 %s: %s" % (item["code"], e))
            stocks.append({
                "股票代码": item["code"], "股票名称": item.get("name", item["code"]),
                "综合评分": 0, "投资建议": "取数失败", "核心逻辑": "行情获取失败，未纳入排序",
                "分析日期": int(datetime.now().timestamp() * 1000), "风险等级": 5,
            })

    stocks.sort(key=lambda x: -(x.get("综合评分") or 0))
    # Phase 7 风控计划真正落地到每日结果
    for s in stocks:
        try:
            rows = fetch_kline(s.get("股票代码"), limit=40, min_quality="medium")
            plan = position_plan(list(rows) if rows else [], market.get("regime", "UNKNOWN"), s.get("风险等级", 5))
            if isinstance(plan, dict):
                s["建议仓位"] = plan.get("position_pct")
                s["ATR"] = plan.get("atr")
                s["ATR波动率%"] = plan.get("atr_pct")
                s["参考止损价"] = plan.get("stop_loss")
                s["风控说明"] = plan.get("reason", "")
        except Exception as exc:
            log("仓位计划跳过 %s: %s" % (s.get("股票代码"), exc))

    # 深度分析 Top N
    top_n = int(cfg.get("top_n_deep", 3))
    if deep and not dry:
        for s in stocks[:top_n]:
            if not s.get("当前价格"):
                continue
            report_dir, decision = run_deep_analysis(s["股票代码"])
            s["报告链接"] = report_dir
            s["深析决策"] = decision
            if report_dir:
                s["核心逻辑"] = (s["核心逻辑"] + "；已深析")[:150]

    # 落盘 JSON（本地诊断产物，dry-run 下保留以便检查）
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = os.path.join(REPORT_DIR, "screening_%s.json" % stamp)
    save_unified_report(stocks, market, rankings, out_file)
    log("Phase10统一日报落盘: %s" % out_file)

    # 跟踪记录写入：dry-run 必须跳过。
    # 否则试运行的推荐会进入 tracking.db，被 backfill 后计入胜率校准样本，
    # 污染真实统计（--dry-run 的语义是"不产生任何持久化副作用"）。
    if dry:
        log("dry-run：跳过 tracking 写入与飞书写表，无持久化副作用")
    else:
        try:
            save_tracking_records(stocks)
        except Exception as exc:
            log("跟踪记录写入失败: %s" % exc)

    # 股票池自动维护（方案A）：dry 时预览，真实运行时实际更新 watchlist.json
    pool_note = ""
    if pool_update:
        try:
            removed, added = update_watchlist(stocks, dry=dry)
            if removed or added:
                pool_note = "淘汰 %s，加入 %s" % (
                    ",".join(c[1] for c in removed), ",".join(a[0] for a in added))
        except Exception as e:
            log("池子维护失败: %s" % e)

    if dry:
        for s in stocks:
            print(" -", s["股票名称"], s["股票代码"], s["综合评分"], s["投资建议"], s["核心逻辑"][:60])
        return

    # 写表格 + 推送
    if cfg.get("push_enabled", True):
        add_records_to_base(stocks)
        send_push(stocks, pool_note)

    log("每日选股完成，共 %d 支" % len(stocks))
    log("=" * 60)


if __name__ == "__main__":
    main()
