# -*- coding: utf-8 -*-
"""每日选股 · 飞书通知（写多维表格 + 消息推送）。

由 daily_stock_pick.py 拆分而来（1.0）。

全部通过 lark-cli 以参数列表方式调用（不使用 shell=True），
避免命令行注入；连续快速调用可能触发 user token 刷新竞争，故带退避重试。
"""
import json
import os
import subprocess
import time
from datetime import datetime

from runtime.runtime_env import WORK_DIR, load_config, log


def run_lark_cmd_list(args, retries=4):
    """运行 lark-cli 命令（list 参数形式，避免 Windows cmd 引号/长度问题）。

    连续快速调用可能触发 user 临时 token 刷新竞争（报 ext err: parse temporary
    token from Authorization fail），失败时退避重试。
    """
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    last = ""
    for i in range(retries):
        try:
            result = subprocess.run(
                ["lark-cli"] + args, capture_output=True, text=True, cwd=WORK_DIR,
                env=env, encoding="utf-8", errors="replace"
            )
            out = result.stdout + result.stderr
            if result.returncode == 0 and '"ok": true' in out:
                return out
            last = out
        except Exception as e:
            last = str(e)
        time.sleep(2 + i * 2)
    return last


def add_records_to_base(stocks):
    """批量写入股票记录到飞书多维表格（分批，规避命令行长度限制）。

    注意：lark-cli base +record-batch-create 使用 --json '{"create_records":[{...}]}'，
    每条记录是直接字段映射（无 fields 包装）。
    """
    config = load_config()
    ok = True
    chunk = 10
    for i in range(0, len(stocks), chunk):
        part = stocks[i:i + chunk]
        create = []
        for s in part:
            row = {k: v for k, v in s.items() if v is not None}
            # 分析日期：毫秒时间戳 -> datetime 字符串（新表 datetime 字段）
            if "分析日期" in row and isinstance(row["分析日期"], (int, float)):
                row["分析日期"] = datetime.fromtimestamp(
                    row["分析日期"] / 1000.0
                ).strftime("%Y-%m-%d %H:%M:%S")
            create.append(row)
        payload = json.dumps({"create_records": create}, ensure_ascii=False)
        result = run_lark_cmd_list([
            "base", "+record-batch-create",
            "--base-token", config["base_token"],
            "--table-id", config["table_id"],
            "--json", payload,
            "--as", "user",
        ])
        log("写飞书表格批次%d/%d: %s" % (i // chunk + 1, (len(stocks) - 1) // chunk + 1, result[:200]))
        if '"ok": false' in result or '"ok":false' in result:
            ok = False
    return ok


def send_push(stocks, pool_note=""):
    config = load_config()
    today = datetime.now().strftime("%m月%d日")
    lines = [
        "**AI股神团队 · %s 每日选股推荐**" % today,
        "",
        "今日筛选 %d 支关注股票（股票池内打分排序）" % len(stocks),
        "",
    ]
    for i, s in enumerate(stocks, 1):
        name = s["股票名称"]
        code = s["股票代码"]
        comp = s["综合评分"]
        advice = s["投资建议"]
        risk = s["风险等级"]
        logic = s["核心逻辑"]
        deep = s.get("深析决策") or ""
        lines.append("Top%d. %s(%s) 评分 %s/10 | %s | 风险 %s" % (i, name, code, comp, advice, risk))
        if deep:
            lines.append("   深析：%s" % deep[:200])
        else:
            lines.append("   %s" % logic[:120])
        lines.append("")
    if pool_note:
        lines.append("【池子更新】%s" % pool_note)
        lines.append("")
    lines.append("以上由 AI 股神团队自动生成，仅供参考，不构成投资建议。")

    message = "\n".join(lines)
    result = run_lark_cmd_list([
        "im", "+messages-send",
        "--user-id", config["notify_user_id"],
        "--markdown", message,
        "--as", "user",
    ])
    log("推送结果: %s" % result[:300])
    return result
