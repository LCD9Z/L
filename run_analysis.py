# -*- coding: utf-8 -*-
"""
run_analysis.py - AI股神系统 · 分析入口（L2 落地）

把 L2 的数据管道与提示词引擎串成一条可执行流水线：

  取数（data_fetcher）→ 组装分析包（prompt_engine）→ 输出各阶段提示词
  → （人工/后续 L4 API 可接模型）逐阶段执行 → 结果回填 → 裁决阶段引用前序结果

用法：
    # 1) 一次生成全部 8 阶段提示词（每个阶段一个文件）
    python run_analysis.py 600519

    # 2) 只生成某个阶段的提示词（粘贴给模型执行）
    python run_analysis.py 600519 --stage analyst_fundamental

    # 3) 分阶段执行：先做前几阶段，把结果回填后，再生成裁决阶段（交易员/风控）
    python run_analysis.py 600519 --stage decision_trade --results reports/600519_results.json

    # 4) 只看数据包（不生成提示词）
    python run_analysis.py 600519 --data-only

结果回填文件格式（--results 参数所指的 json）：
    {
      "analyst_fundamental": {"评分": 8, ...},     # 或该阶段模型返回的原始文本
      "analyst_sentiment": "模型返回的文本...",
      "research_bullish": {"强度评分": 7, ...}
    }
    阶段 key 见 prompt_engine.RESULT_FILES。
"""

import os
import sys
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from prompt_engine import STAGES, build_analysis_package, save_package
from data_fetcher import normalize_code
import tracking
from typing import Any, Dict

# 阶段名映射：{stage_key: 中文名}
STAGE_NAMES = {s[0]: s[2] for s in STAGES}


def _stance_of(cmd):
    """把交易指令归一化到建议档位：优先精确匹配，否则按关键词兜底。"""
    if not cmd:
        return "中性"
    m = tracking.STANCE_MAP.get(cmd)
    if m:
        return m
    if any(k in cmd for k in ("买入", "加仓", "建仓", "做多", "追高")):
        return "看多"
    if any(k in cmd for k in ("卖出", "减仓", "止损", "清仓", "做空")):
        return "看空"
    if any(k in cmd for k in ("持有", "观望", "中性")):
        return "中性"
    return "中性"


def track_from_results(code, results, horizon=5, dedup=True):
    """把 decision_risk/decision_trade 决策结果提取为推荐记录并写入 tracking 库。

    合并两阶段取值：指令/风险等级从 decision_risk，信心评分优先 decision_trade。
    返回记录 id；无可记录内容或重复记录（幂等）时返回 None。
    """
    risk = results.get("decision_risk")
    trade = results.get("decision_trade")
    if not risk and not trade:
        print("❌ 未找到 decision_risk/decision_trade 结果，跳过记录")
        return None

    def _as_dict(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return {}
        return v if isinstance(v, dict) else {}

    risk_d = _as_dict(risk)
    trade_d = _as_dict(trade)
    if not risk_d and not trade_d:
        print("❌ 决策结果格式无法解析，跳过记录")
        return None

    cmd = risk_d.get("最终交易指令") or trade_d.get("交易指令") or ""
    stance = _stance_of(cmd)
    std, _, _ = normalize_code(code)
    # 评分必须是数值（用于 L3 分档校准）；优先信心评分，风险等级若为数值才兜底
    score = trade_d.get("信心评分")
    if score is None:
        lvl = risk_d.get("风险等级")
        if isinstance(lvl, (int, float)):
            score = lvl
    rec_date = (risk_d.get("推荐日期") or risk_d.get("日期")
                or trade_d.get("推荐日期") or trade_d.get("日期") or None)
    conn = tracking.get_conn()
    tracking.init_db(conn)
    if dedup:
        dup = tracking.find_duplicate(conn, std, rec_date or tracking._today(), horizon)
        if dup:
            print(f"⚠️ 幂等去重：code+日期+周期 已存在记录 #{dup}，跳过落库")
            return None
    rid = tracking.add_recommendation(conn, {
        "code": std,
        "name": None,
        "rec_date": rec_date,  # 默认今天
        "horizon": horizon,
        "stance": stance,
        "score": score,
        "logic": json.dumps({**risk_d, **trade_d}, ensure_ascii=False),
    })
    return rid


def load_results(path: str) -> dict:
    """加载已有阶段结果（--results）。兼容文本/JSON 两种文件。

    - path 指向 JSON：直接解析为 {stage: result}。
    - path 指向单个 txt（非 JSON）：读取其所在目录下所有同名前缀的阶段文件，
      按 RESULT_FILES 命名规则（01_fundamental.txt 等）一对一映射，避免误塞。
    """
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = f.read().strip()
        if raw.startswith("{"):
            return json.loads(raw)
        # 非 JSON：按目录内阶段文件命名规则一对一映射
        from prompt_engine import RESULT_FILES
        results: Dict[str, Any] = {}
        d = os.path.dirname(path) or "."
        for stage, fname in RESULT_FILES.items():
            fpath = os.path.join(d, fname.replace(".json", ".txt"))
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8-sig") as f2:
                    results[stage] = f2.read().strip()
        return results
    except Exception as e:
        print(f"⚠️ 读取结果文件失败：{e}")
        return {}


_SYS_PROMPT = (
    "你是AI股神团队的资深A股分析师，按角色要求对给定【数据包】做专业分析。"
    "铁律：只基于数据包与用户提供的资料判断，禁止编造不存在的价格/财报/消息；"
    "引用数据时标注依据；输出必须为合法 JSON。"
)


def run_auto(code, company="", news_limit=5, horizon=5, track=True,
             model=None, temperature=0.3, cutoff_time=None, use_crawl4ai=None,
             profile=None):
    """L4 全自动：取数 → 逐阶段调大模型 → 汇总落盘 → 决策落库。

    返回 {stage: 结果} 字典。
    """
    import time as _time
    from llm_client import chat, extract_json
    from data_fetcher import build_fact_sheet, fact_sheet_to_text
    from prompt_engine import STAGES, RESULT_FILES, get_stage_prompt
    from runtime_profile import get_profile

    rp = get_profile(profile)
    news_limit = min(news_limit, rp.news_limit) if news_limit is not None else rp.news_limit
    fact_sheet = build_fact_sheet(code, news_limit=news_limit, cutoff_time=cutoff_time, use_crawl4ai=use_crawl4ai, factor_window=rp.factor_window)
    company = company or fact_sheet.get("quote", {}).get("name") or code
    print(f"📥 数据包就绪：{company} ({code})，来源 "
          f"{fact_sheet.get('meta', {}).get('data_source')}")

    results: Dict[str, Any] = {}

    def _txt(stage):
        v = results.get(stage)
        if not v:
            return ""
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "reports", f"{code}_auto_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "00_数据包.txt"), "w", encoding="utf-8") as f:
        f.write(fact_sheet_to_text(fact_sheet))

    # First six stages are mutually independent. Running them in a bounded
    # thread pool cuts wall-clock time while keeping memory pressure low.
    independent = {
        "analyst_fundamental", "analyst_sentiment", "analyst_news",
        "analyst_technical", "research_bullish", "research_bearish",
    }
    stage_map = {s[0]: s for s in STAGES}

    def _save(stage):
        with open(os.path.join(out_dir, RESULT_FILES[stage]), "w", encoding="utf-8") as f:
            json.dump(results[stage], f, ensure_ascii=False, indent=2)

    def _call(stage, prompt, max_tokens):
        t0 = _time.time()
        try:
            text = chat(
                [{"role": "system", "content": _SYS_PROMPT},
                 {"role": "user", "content": prompt}],
                model=model, temperature=temperature, max_tokens=max_tokens)
            obj = extract_json(text)
            return stage, obj if obj is not None else {"raw": text}, _time.time() - t0, None
        except Exception as e:
            return stage, {"错误": str(e)}, _time.time() - t0, e

    def _token_budget(stage):
        if stage.startswith("analyst_"):
            return rp.analyst_tokens
        if stage.startswith("research_"):
            return rp.research_tokens
        if stage == "review_committee":
            return rp.committee_tokens
        return rp.decision_tokens

    print(f"⚙️ 运行配置：{rp.name} | 并发 {rp.max_workers} | 因子窗口 {rp.factor_window} | "
          f"分析师输出上限 {rp.analyst_tokens} tokens")

    def _prompt_for(stage):
        analyst_reports = [_txt(s) for s in (
            "analyst_fundamental", "analyst_sentiment",
            "analyst_news", "analyst_technical") if _txt(s)]
        return get_stage_prompt(
            stage, fact_sheet, code, company,
            analyst_reports=analyst_reports,
            bullish_report=_txt("research_bullish"),
            bearish_report=_txt("research_bearish"),
            trade_proposal=_txt("decision_trade"),
            committee_report=_txt("review_committee"),
        )

    pending = []
    with ThreadPoolExecutor(max_workers=rp.max_workers) as pool:
        for stage in (s[0] for s in STAGES if s[0] in independent):
            name = stage_map[stage][2]
            print(f"🧠 [{stage}] {name}（并行）...")
            pending.append(pool.submit(_call, stage, _prompt_for(stage), _token_budget(stage)))
        for fut in as_completed(pending):
            stage, value, elapsed, err = fut.result()
            results[stage] = value
            print(f"   {'❌' if err else '✅'} [{stage}] {elapsed:.1f}s")
            _save(stage)

        # Dependency chain: committee -> trader -> risk. Keep these serial so
        # each stage sees the completed outputs from the previous stage.
        for stage in ("review_committee", "decision_trade", "decision_risk"):
            name = stage_map[stage][2]
            print(f"\n🧠 [{stage}] {name} ...")
            _, value, elapsed, err = _call(stage, _prompt_for(stage), _token_budget(stage))
            results[stage] = value
            print(f"   {'❌' if err else '✅'} 完成（{elapsed:.1f}s）")
            _save(stage)

    summary_path = os.path.join(out_dir, "results.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 全自动分析完成，结果目录：{out_dir}")

    risk = results.get("decision_risk")
    if isinstance(risk, dict) and not risk.get("raw"):
        print("\n===== 最终决策 =====")
        for k in ("最终交易指令", "最终仓位建议%", "风险等级", "信心评分", "一票否决理由"):
            if risk.get(k):
                print(f"  {k}: {risk.get(k)}")
    elif isinstance(risk, dict) and risk.get("raw"):
        print("\n⚠️ 决策结果未解析为 JSON，请查看 results.json 原文。")

    if track:
        rid = track_from_results(code, results, horizon, dedup=True)
        if rid:
            print(f"✅ 已记录推荐 #{rid} 到 tracking.db（L3 回测闭环）")
        else:
            print("ℹ️ 未新增记录（无可记录决策，或已存在重复）")

    return results


def main():
    parser = argparse.ArgumentParser(description="AI股神系统 · 分析入口（L2）")
    parser.add_argument("code", help="股票代码，如 600519 / sz000017")
    parser.add_argument("--stage", help="只生成指定阶段提示词，见 STAGES")
    parser.add_argument("--results", help="已有阶段结果的 json 路径（用于裁决阶段）")
    parser.add_argument("--output", help="分析包输出目录")
    parser.add_argument("--news", type=int, default=5, help="新闻条数上限，默认 5")
    parser.add_argument("--data-only", action="store_true", help="只输出数据包")
    parser.add_argument("--track", action="store_true",
                        help="分析后把决策结果记录到回测库（需 --results 含 decision_risk/trade）")
    parser.add_argument("--horizon", type=int, default=5,
                        help="回测周期（交易日），默认 5")
    parser.add_argument("--auto", action="store_true",
                        help="L4 全自动：取数→逐阶段调大模型→汇总落盘→决策落库")
    parser.add_argument("--codes", help="全自动模式多股票：逗号分隔，如 600519,000017")
    parser.add_argument("--model", help="覆盖默认模型（llm_config.json 中的 model）")
    parser.add_argument("--temp", type=float, default=0.3,
                        help="模型温度，默认 0.3")
    parser.add_argument("--cutoff-time", help="历史研究时点，例如 2026-09-05T15:00:00+08:00")
    parser.add_argument("--crawl4ai", action="store_true", help="启用 Crawl4AI 抓取搜索结果正文；未安装时自动降级")
    parser.add_argument("--no-crawl4ai", action="store_true", help="强制关闭 Crawl4AI")
    parser.add_argument("--no-track", action="store_true",
                        help="全自动模式不落库（默认自动落库到 tracking.db）")
    parser.add_argument("--profile", choices=("lite", "balanced", "full"), default=None,
                        help="运行资源档位；8GB电脑默认 balanced，可用 lite 降低耗时/内存")
    args = parser.parse_args()

    # L4 全自动分支
    if args.auto:
        codes = [c.strip() for c in args.codes.split(",")] if args.codes else [args.code]
        for c in codes:
            if not c:
                continue
            print(f"\n========== 全自动分析：{c} ==========")
            run_auto(c, news_limit=args.news, horizon=args.horizon,
                     track=not args.no_track, model=args.model,
                     temperature=args.temp, cutoff_time=args.cutoff_time,
                     use_crawl4ai=False if args.no_crawl4ai else (True if args.crawl4ai else None),
                     profile=args.profile)
        return

    # 读取已有结果
    results = load_results(args.results)

    # 组装分析包
    pkg = build_analysis_package(args.code, news_limit=args.news,
                                 existing_results=results)

    if args.data_only:
        print(pkg["data_package"])
        return

    # 只输出单个阶段
    if args.stage:
        if args.stage not in STAGE_NAMES:
            print(f"❌ 未知阶段：{args.stage}，可选：{[s[0] for s in STAGES]}")
            sys.exit(1)
        prompt = pkg["prompts"][args.stage]
        out_path = None
        if args.output:
            os.makedirs(args.output, exist_ok=True)
            out_path = os.path.join(args.output, f"{args.stage}_prompt.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(prompt)
        print(f"========== 阶段：{STAGE_NAMES[args.stage]} ==========")
        print(prompt)
        if out_path:
            print(f"\n✅ 已保存到：{out_path}")
        return

    # 生成全部阶段并落盘
    out = save_package(pkg, args.output)
    print(f"✅ 分析包已生成：{out}")
    print(f"   股票：{pkg['company']} ({pkg['code']})")
    print(f"   数据来源：{pkg['fact_sheet'].get('meta', {}).get('data_source')}")
    print()
    print("执行方式（二选一）：")
    print("  A. 将 reports/{code}_prompts_xxx/ 目录下 01~08 文件逐个粘贴给模型，")
    print("     把每个阶段的 JSON 结果依次保存为对应 .json（01_fundamental.json 等）。")
    print("  B. 或用 --stage 分阶段执行：先做 01-04 分析师，再 05/06 多空，")
    print("     把结果合并成一个 json 后，用 --results 生成 07 交易员、08 风控的提示词。")
    print()
    print("下一步提示：执行完 01-08 后，可把 8 个结果 JSON 合并汇总成最终报告。")

    # L3：把决策结果记录到回测库（--track --results xxx）
    if args.track:
        rid = track_from_results(args.code, results, args.horizon)
        if rid:
            print(f"✅ 已记录推荐 #{rid} 到 tracking.db（L3 回测闭环）")
            print("   后续用 run_tracking.py backfill 回填真实涨跌，再 stats/report 出校准报告。")


if __name__ == "__main__":
    main()
