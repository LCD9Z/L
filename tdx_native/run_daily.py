# -*- coding: utf-8 -*-
"""每日一键运行：推荐生成 → 自选股导出 → 到期回填 →（可选）飞书推送。

借鉴来源（2026-09-30 GitHub 调研，详见 GITHUB_ASHARE_QUANT_SURVEY.md 续篇）：
- sngyai/Sequoia-X（7.6k★）：收盘后一键 `python main.py` 的日常模式 +
  飞书 Webhook 卡片推送 + 雪球个股链接
- oficcejo/tdx-local2：通达信自选股文件导出（客户端 Ctrl+D 批量导入）

固定执行配置（与 STEP1_3_EXECUTION_REPORT.md 收口结论一致）：
  C20 分散 + V1 尾部剔除（ret20 最高 20%）+ V2 跳空过滤 + 前复权 + ST 剔除。

用法（建议每个交易日收盘后 15:30 运行）::

    python -m tdx_native.run_daily                        # 本地报告
    python -m tdx_native.run_daily --feishu-webhook URL   # 附加飞书推送

未收盘保护：若 .day 已含今日 bar 而当前时间未到 15:05，拒绝运行，
避免把半日数据写入 tracking.csv 污染样本（口径纪律）。
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import time
import urllib.request
from typing import Any, Dict, List

from . import backfill as backfill_mod
from . import daily_report
from . import day_reader
from . import screen


def _market_prefix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith(("4", "8")):
        return "bj"
    return "sz"


def _xueqiu_code(code: str) -> str:
    p = _market_prefix(code)
    return {"sh": "SH", "bj": "BJ", "sz": "SZ"}[p] + code


def guard_unfinished_session(vipdoc: str) -> None:
    """未收盘保护：今日 bar 已存在且时间 < 15:05 → 拒绝运行。"""
    idx_path = os.path.join(vipdoc, "sh", "lday", "sh000001.day")
    last = day_reader.read_day_tail(idx_path, 1)
    if not last:
        return
    today = time.strftime("%Y%m%d")
    now = _dt.datetime.now()
    if last[-1]["date"] == today and (now.hour, now.minute) < (15, 5):
        raise SystemExit(
            f"[拒绝] 检测到今日({today})bar 已存在但尚未收盘（{now:%H:%M}）。\n"
            "盘中数据会污染因子口径，请在 15:05 之后运行。")


def _due_exits(filled_csv: str, today: str,
               tolerance_days: int = 15) -> List[Dict[str, Any]]:
    """返回**已到期应卖出**的持仓（按逾期天数升序）。

    为什么不能只匹配"今天到期"：到期日那天任务可能没跑——数据未更新被跳过、
    电脑关机、或恰好是节假日。只匹配当天会让这些持仓**永远不会被提示**，
    用户就白白错过离场时点。因此覆盖 ``today`` 之前 ``tolerance_days``
    个自然日内到期的全部记录，并标注逾期天数。

    为什么需要卖出提示：系统此前只回答"买什么"，但持有期是 20 个交易日，
    到期后必须卖出。没有这一步，实际使用闭环就缺了一半。

    每条记录附带 ``_overdue_days``（0 = 今日到期）。
    """
    if not os.path.exists(filled_csv):
        return []
    try:
        t0 = _dt.datetime.strptime(today, "%Y%m%d").date()
    except ValueError:
        return []
    out: List[Dict[str, Any]] = []
    with open(filled_csv, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            d = (r.get("t20_date") or "").strip()
            if len(d) != 8 or not d.isdigit():
                continue
            try:
                due = _dt.datetime.strptime(d, "%Y%m%d").date()
            except ValueError:
                continue
            delta = (t0 - due).days
            if 0 <= delta <= tolerance_days:
                out.append({**r, "_overdue_days": delta})
    out.sort(key=lambda r: (r["_overdue_days"], r.get("code", "")))
    return out


def export_exits(rows: List[Dict[str, Any]], out_dir: str, today: str) -> str:
    """把到期卖出清单写成 markdown。"""
    path = os.path.join(out_dir, f"exits_{today}.md")
    overdue = [r for r in rows if int(r.get("_overdue_days") or 0) > 0]
    lines = [
        f"# 到期卖出清单 · {today}",
        "",
        "> 以下持仓按「持有 20 个交易日」规则已到期。本清单仅为执行提醒，",
        "> 不构成投资建议，也不含任何择时判断。",
        "",
    ]
    if overdue:
        lines += [
            f"> ⚠️ 其中 {len(overdue)} 条**已逾期**——通常是到期日当天任务没跑"
            "（数据未更新 / 关机 / 节假日）。补跑会自动把它们捞回来。",
            "",
        ]
    if not rows:
        lines.append("今日无到期持仓。")
    else:
        lines += ["| 代码 | 名称 | 买入日 | 买入价 | 到期日 | 状态 | 收益 |",
                  "|------|------|--------|--------|--------|------|------|"]
        for r in rows:
            od = int(r.get("_overdue_days") or 0)
            state = "今日到期" if od == 0 else f"⚠️ 逾期 {od} 天"
            ret = f"{float(r['t20_ret']):+.2%}" if r.get("t20_ret") else "n/a"
            lines.append(
                f"| {r.get('code', '')} | {r.get('name') or '-'} | "
                f"{r.get('t1_date', '')} | {r.get('t1_open', '')} | "
                f"{r.get('t20_date', '')} | {state} | {ret} |")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return path


def feishu_push(webhook: str, payload: dict) -> bool:
    """飞书 Webhook 卡片推送（借鉴 Sequoia-X 的 interactive card 格式）。

    仅在显式提供 webhook 时调用；失败不阻断本地流程。
    """
    as_of = payload["as_of"]
    top = payload.get("top", [])
    lines = []
    for i, t in enumerate(top[:10], 1):
        name = t.get("name") or t["code"]
        lines.append(
            f"{i}. [{name}](https://xueqiu.com/S/{_xueqiu_code(t['code'])})"
            f"（得分 {t['score']:.3f}）")
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text",
                          "content": f"📊 五因子候选清单 · {as_of}"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"**日期：** {as_of}\n**候选数：** {len(top)}"
                    f"（完整明细见本地报告）"}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    "\n".join(lines) or "（无候选）"}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    "**不构成投资建议。** 五因子为统计特征，本项目已验证其"
                    "无法产生可实现的超额收益；本清单仅作候选与跟踪校准用途。"}},
                {"tag": "note", "elements": [{"tag": "plain_text",
                    "content": "tdx_native · 通达信原生数据 · 每日收盘后自动生成"}]},
            ],
        },
    }
    try:
        req = urllib.request.Request(
            webhook, data=json.dumps(card).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        ok = body.get("code") == 0
        print(f"飞书推送：{'成功' if ok else body}")
        return ok
    except Exception as e:
        print(f"飞书推送失败（不阻断本地流程）：{type(e).__name__}: {e}")
        return False


def _data_as_of(vipdoc: str) -> str:
    """全池最新交易日（用上证指数日历近似）。"""
    idx = os.path.join(vipdoc, "sh", "lday", "sh000001.day")
    last = day_reader.read_day_tail(idx, 1)
    return last[-1]["date"] if last else ""


def _last_tracked_as_of(track_path: str) -> str:
    """tracking.csv 中已登记的最大 as_of。"""
    if not os.path.exists(track_path):
        return ""
    latest = ""
    with open(track_path, encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if row and str(row[0]).isdigit():
                latest = max(latest, str(row[0]))
    return latest


def run(vipdoc: str, top_n: int = 20, out_dir: str = "reports/daily",
        names_csv: str = "data/names.csv", events_cache: str = "data/gbbq_events.csv",
        feishu_webhook: str = "", force: bool = False) -> int:
    guard_unfinished_session(vipdoc)

    # 数据未更新保护：避免节假日/未开通达信时重复产出同一份报告
    track_path = os.path.join(out_dir, "tracking.csv")
    cur = _data_as_of(vipdoc)
    prev = _last_tracked_as_of(track_path)
    if not force and cur and prev and cur == prev:
        print(f"[跳过] 数据未更新（最新交易日仍为 {cur}，已登记过）。"
              "节假日或未更新通达信数据时属正常；如需强制重跑加 --force")
        return 0

    if names_csv and not os.path.exists(names_csv):
        print(f"[提示] {names_csv} 不存在：将无名称显示、不做 ST 剔除。"
              "建议先运行 python -m tdx_native.fetch_names")

    # 数据完整性预检：残缺池会产出"看起来完全正常"的报告与跟踪记录，
    # 属于本项目最警惕的静默失效。宁可拒绝产出，也不写脏数据。
    pf = screen.preflight(vipdoc)
    if pf["problems"]:
        msg = "；".join(pf["problems"])
        if not force:
            raise SystemExit(
                f"[拒绝] 数据完整性预检未通过：{msg}\n"
                "通达信 .day 可能未下载完整——请打开客户端重新下载后再跑。\n"
                "（确认数据无误可加 --force 强制继续）")
        print(f"[警告] 数据完整性预检未通过：{msg}（--force 已强制继续）")
    else:
        print(f"预检通过：{pf['stocks_found']} 只，"
              f"{pf['fresh_ratio']:.0%} 更新至 {pf['as_of']}")

    print("=" * 60)
    print("[1/4] 生成每日推荐（C20+V1+V2+前复权+ST 剔除）")
    payload = daily_report.build_report(
        vipdoc, events_cache=events_cache, names_csv=names_csv,
        top_n=top_n, exclude_ret20_top=0.20, jump_filter=True,
        out_dir=out_dir)
    as_of = payload["as_of"]

    # 通达信自选股导出（借鉴 tdx-local2）
    wl_path = os.path.join(out_dir, f"selected_stocks_{as_of}.txt")
    with open(wl_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(_market_prefix(t["code"]) + t["code"]
                          for t in payload["top"]) + "\n")
    print(f"[2/4] 通达信自选股已导出：{wl_path}"
          "（客户端 Ctrl+D → 批量导入）")

    print("[3/4] 回填到期跟踪样本")
    filled_csv = os.path.join(out_dir, "tracking_filled.csv")
    backfill_mod.run(vipdoc, track_path, filled_csv)

    # 到期卖出提示：补上"何时离场"这一半闭环
    today = time.strftime("%Y%m%d")
    exits = _due_exits(filled_csv, today)
    ex_path = export_exits(exits, out_dir, today)
    if exits:
        print(f"[4/4] 到期卖出提醒：{len(exits)} 只 → {ex_path}")
        for r in exits:
            ret = f"{float(r['t20_ret']):+.2%}" if r.get("t20_ret") else "n/a"
            od = int(r.get("_overdue_days") or 0)
            tag = "今日" if od == 0 else f"逾期{od}天"
            print(f"      [{tag}] {r['code']} {r.get('name') or '':<8}"
                  f" 买入 {r.get('t1_date', '')} @{r.get('t1_open', '')}"
                  f" 收益 {ret}")
    else:
        print(f"[4/4] 今日无到期持仓（{ex_path}）")

    if feishu_webhook:
        print("推送飞书卡片 …")
        feishu_push(feishu_webhook, payload)

    print("\n完成。报告："
          f"{os.path.join(out_dir, f'recommend_{as_of}.md')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="每日一键：推荐+导出+回填(+推送)")
    ap.add_argument("--vipdoc", default="D:/new_tdx/vipdoc")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--out-dir", default="reports/daily")
    ap.add_argument("--names", default="data/names.csv")
    ap.add_argument("--events-cache", default="data/gbbq_events.csv")
    ap.add_argument("--feishu-webhook", default="",
                    help="可选：飞书群机器人 Webhook URL")
    ap.add_argument("--force", action="store_true",
                    help="即使数据未更新（as_of 与上次相同）也强制重跑")
    args = ap.parse_args()
    return run(args.vipdoc, top_n=args.top, out_dir=args.out_dir,
               names_csv=args.names, events_cache=args.events_cache,
               feishu_webhook=args.feishu_webhook, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
