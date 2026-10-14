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


def feishu_alert(webhook: str, title: str, lines: List[str],
                 level: str = "warning") -> bool:
    """飞书**异常告警**推送（2026-10-04）。

    与 ``feishu_push`` 的分工：那个推每日候选清单，这个只在**异常时**响。

    为什么单独一条通道：静默失效是本项目最警惕的故障。数据陈旧、
    预检未过、推送失败——这些若只写进 run.log，等于没发生。
    """
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"⚠️ {title}"},
                "template": "red" if level == "error" else "orange",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md",
                                        "content": "\n".join(lines)}},
                {"tag": "note", "elements": [{"tag": "plain_text",
                    "content": f"tdx_native · {time.strftime('%Y-%m-%d %H:%M')}"
                               "· 每日收盘后自动监控"}]},
            ],
        },
    }
    return _feishu_post(webhook, card)


def _feishu_post(webhook: str, card: dict) -> bool:
    try:
        req = urllib.request.Request(
            webhook, data=json.dumps(card).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        ok = body.get("code") == 0
        if not ok:
            print(f"飞书返回错误：{body}")
        return bool(ok)
    except Exception as e:
        print(f"飞书推送失败（不阻断本地流程）：{type(e).__name__}: {e}")
        return False


def feishu_push(webhook: str, payload: dict) -> bool:
    """飞书 Webhook 卡片推送（借鉴 Sequoia-X 的 interactive card 格式）。

    仅在显式提供 webhook 时调用；失败不阻断本地流程。

    2026-10-04 改造：
    - **静默默认**：正常产出不发消息，只推异常（用户要求"有异常才推"）
    - 加「到期待卖出」段——昨天补的闭环，此前从未接进推送
    - 候选清单默认只列前 5（20 行在手机上刷屏），可用 ``--feishu-top`` 调
    """
    quiet = payload.get("feishu_quiet", True)
    exits = payload.get("exits") or []
    as_of = payload["as_of"]
    top = payload.get("top", [])
    n_show = int(payload.get("feishu_top", 5))
    uni = payload.get("universe", {})

    # 正常且无到期待卖 → 静默，不打扰
    if quiet and not exits:
        print("飞书推送：正常产出且无到期待卖，按「有异常才推」策略静默")
        return True

    elements: List[dict] = []
    if exits:
        el = [f"**{i}. {r.get('name') or r.get('code')}** "
              f"（{r.get('code')}）到期 {r.get('t20_date')}"
              + (f"｜**已逾期 {r['_overdue_days']} 天**"
                 if r.get("_overdue_days") else "｜今日到期")
              + f"\n　持有期收益 {(float(r.get('t20_ret') or 0)):+.2%}"
              for i, r in enumerate(exits, 1)]
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": "**🔴 到期待卖出**（持有 20 个交易日）\n" + "\n".join(el)}})
        elements.append({"tag": "hr"})

    if not quiet and top:
        lines = [
            f"{i}. [{t.get('name') or t['code']}]"
            f"（{t['code']}）得分 {t['score']:.3f}"
            f"｜ret20 {t['ret20']:+.1%}"
            for i, t in enumerate(top[:n_show], 1)]
        more = (f"\n…共 {len(top)} 只，完整清单见本地报告"
                if len(top) > n_show else "")
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": f"**候选前 {min(n_show, len(top))}**\n"
                       + "\n".join(lines) + more}})

    elements += [
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content":
            f"数据截止 {as_of}｜池 {uni.get('stocks_found', '?')} 只"
            f"｜打分 {uni.get('scored', '?')} 只"}},
        {"tag": "div", "text": {"tag": "lark_md", "content":
            "**不构成投资建议。** 五因子为统计特征，本项目已验证其无法产生"
            "可实现的超额收益；本清单仅作候选与跟踪校准用途。"}},
        {"tag": "note", "elements": [{"tag": "plain_text",
            "content": "tdx_native · 通达信原生数据 · 每日收盘后自动生成"}]},
    ]

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text",
                          "content": f"📊 五因子候选清单 · {as_of}"},
                "template": "blue",
            },
            "elements": elements,
        },
    }
    ok = _feishu_post(webhook, card)
    print(f"飞书推送：{'成功' if ok else '失败'}"
          + (f"（含 {len(exits)} 条到期卖出）" if exits else ""))
    return ok


def _data_as_of(vipdoc: str) -> str:
    """全池最新交易日（用上证指数日历近似）。"""
    idx = os.path.join(vipdoc, "sh", "lday", "sh000001.day")
    last = day_reader.read_day_tail(idx, 1)
    return last[-1]["date"] if last else ""


def _is_trading_day(vipdoc: str, last_known: str) -> bool:
    """今天是否**本应**已有新数据。

    判据：今天已过 15:05 收盘，且**交易日历里存在今天这个日期**。
    —— 不硬编码法定节假日表（会每年过期）；直接问通达信数据
    「今天算交易日吗」。``last_known`` 已知为尚未更新的最新交易日，
    因此这里只需判断「今天比它新」。
    """
    now = _dt.datetime.now()
    if now.weekday() >= 5:          # 周末直接排除（含调休上班的周六）
        return False
    if (now.hour, now.minute) < (15, 5):
        return False
    # 日历里出现过晚于 last_known 的日期 → 说明日历已覆盖今天
    idx = os.path.join(vipdoc, "sh", "lday", "sh000001.day")
    cal = [b["date"] for b in day_reader.read_day_tail(idx, 30)]
    return any(d > last_known for d in cal)


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


def _read_webhook(cli_value: str, path: str) -> str:
    """Webhook 读取顺序：命令行 > 环境变量 > 本地明文文件。

    为什么支持文件：计划任务无法方便地传命令行参数，而 Webhook 有一百多
    字符，塞在 bat 里极易写错。

    **凭据纪律**：Webhook 等同于该群的发帖权限。本项目把它放
    ``.gitignore`` 忽略的 ``data/feishu_webhook.txt``，**绝不入库**；
    环境变量优先级更高，适合正式部署。
    """
    if cli_value:
        return cli_value
    env = os.environ.get("TDX_FEISHU_WEBHOOK", "").strip()
    if env:
        return env
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def run(vipdoc: str, top_n: int = 20, out_dir: str = "reports/daily",
        names_csv: str = "data/names.csv", events_cache: str = "data/gbbq_events.csv",
        feishu_webhook: str = "", force: bool = False,
        feishu_top: int = 5, feishu_quiet: bool = True) -> int:
    feishu_webhook = _read_webhook(
        feishu_webhook, "data/feishu_webhook.txt")
    if not feishu_webhook:
        print("提示：未配置飞书 Webhook（data/feishu_webhook.txt 或环境变量 "
              "TDX_FEISHU_WEBHOOK），本次不推送。异常会仅记入 run.log。")
    guard_unfinished_session(vipdoc)

    # 数据未更新保护：避免节假日/未开通达信时重复产出同一份报告
    track_path = os.path.join(out_dir, "tracking.csv")
    cur = _data_as_of(vipdoc)
    prev = _last_tracked_as_of(track_path)
    if not force and cur and prev and cur == prev:
        print(f"[跳过] 数据未更新（最新交易日仍为 {cur}，已登记过）。"
              "节假日或未更新通达信数据时属正常；如需强制重跑加 --force")
        # 区分「节假日正常跳过」与「数据真的陈旧」：若今天本身是交易日
        # 却拿不到新数据，说明通达信没下载，用退出码 3 显式告警——
        # 退出码 0 会让 schtasks 记为成功，静默跳过即无人察觉
        # （2026-10-02 审计：run.log 连续 3 次跳过而无人知情）。
        if _is_trading_day(vipdoc, cur):
            print(f"[告警] {cur} 是交易日却无新数据——通达信客户端可能未下载。"
                  f"请打开客户端更新行情后重跑。")
            feishu_alert(feishu_webhook, f"数据未更新 · {cur}", [
                f"**{cur} 是交易日，但通达信数据仍停在 {cur}，未产出新报告。**",
                "",
                "最可能原因：通达信客户端没打开下载。",
                "处理：打开客户端更新行情 → 重跑 `python -m tdx_native.run_daily`",
            ], level="error")
            return 3
        return 0

    if names_csv and not os.path.exists(names_csv):
        print(f"[提示] {names_csv} 不存在：将无名称显示、不做 ST 剔除。"
              "建议先运行 python -m tdx_native.fetch_names")

    # 数据完整性预检：残缺池会产出"看起来完全正常"的报告与跟踪记录，
    # 属于本项目最警惕的静默失效。宁可拒绝产出，也不写脏数据。
    pf = screen.preflight(vipdoc)
    if pf["problems"]:
        msg = "；".join(pf["problems"])
        feishu_alert(feishu_webhook, "数据完整性预检未通过", [
            "**已拒绝产出**（宁可不出，也不用残缺股票池写脏数据）",
            "",
            f"- 原因：{msg}",
            f"- 扫描到 {pf['stocks_found']} 只，更新至 {pf['as_of']}，"
            f"新鲜度 {pf['fresh_ratio']:.0%}",
            "",
            "处理：打开通达信客户端**重新完整下载**后重跑。",
            "（确认数据无误可加 `--force` 强制继续）",
        ], level="error")
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
        payload["exits"] = exits
        payload["feishu_quiet"] = feishu_quiet
        payload["feishu_top"] = feishu_top
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
                    help="可选：飞书群机器人 Webhook URL"
                         "（默认从 data/feishu_webhook.txt 或环境变量读）")
    ap.add_argument("--feishu-top", type=int, default=5,
                    help="飞书卡片列出的候选只数（默认 5，手机不刷屏）")
    ap.add_argument("--feishu-always", action="store_true",
                    help="默认仅在有到期待卖/异常时推送；加此参数每天都推")
    ap.add_argument("--force", action="store_true",
                    help="即使数据未更新（as_of 与上次相同）也强制重跑")
    args = ap.parse_args()
    return run(args.vipdoc, top_n=args.top, out_dir=args.out_dir,
               names_csv=args.names, events_cache=args.events_cache,
               feishu_webhook=args.feishu_webhook, force=args.force,
               feishu_top=args.feishu_top,
               feishu_quiet=not args.feishu_always)


if __name__ == "__main__":
    raise SystemExit(main())
