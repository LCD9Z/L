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
import datetime as _dt
import json
import os
import time
import urllib.request

from . import backfill as backfill_mod
from . import daily_report
from . import day_reader


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


def run(vipdoc: str, top_n: int = 20, out_dir: str = "reports/daily",
        names_csv: str = "data/names.csv", events_cache: str = "data/gbbq_events.csv",
        feishu_webhook: str = "", skip_report: bool = False) -> int:
    guard_unfinished_session(vipdoc)

    if names_csv and not os.path.exists(names_csv):
        print(f"[提示] {names_csv} 不存在：将无名称显示、不做 ST 剔除。"
              "建议先运行 python -m tdx_native.fetch_names")

    print("=" * 60)
    print("[1/3] 生成每日推荐（C20+V1+V2+前复权+ST 剔除）")
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
    print(f"[2/3] 通达信自选股已导出：{wl_path}"
          "（客户端 Ctrl+D → 批量导入）")

    print("[3/3] 回填到期跟踪样本")
    backfill_mod.run(
        vipdoc,
        os.path.join(out_dir, "tracking.csv"),
        os.path.join(out_dir, "tracking_filled.csv"))

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
    args = ap.parse_args()
    return run(args.vipdoc, top_n=args.top, out_dir=args.out_dir,
               names_csv=args.names, events_cache=args.events_cache,
               feishu_webhook=args.feishu_webhook)


if __name__ == "__main__":
    raise SystemExit(main())
