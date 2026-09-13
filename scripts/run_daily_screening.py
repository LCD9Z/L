#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI股神团队 - 每日选股执行脚本
Daily Stock Screening Runner

每天早上8:30由定时任务调用，执行选股分析并写入飞书表格，发送推送通知。
"""

# 脚本位于 scripts/ 下，需把项目根目录加入导入路径
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import os
import sys
import json
import subprocess
from datetime import datetime

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(WORK_DIR, "feishu_config.json")
LOG_FILE = os.path.join(WORK_DIR, "daily_monitor.log")


def log(msg):
    """日志记录"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


def load_config():
    """加载配置"""
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def run_lark_cmd(args):
    """运行 lark-cli 命令。

    使用参数列表（不使用 shell=True），避免命令行注入；
    通过 env 传递 LARKSUITE_* 环境变量，兼容 Windows / POSIX。
    """
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    result = subprocess.run(
        ["lark-cli"] + args,
        capture_output=True, text=True, cwd=WORK_DIR, env=env
    )
    return result.stdout + result.stderr


def add_records_to_base(stocks):
    """批量写入股票记录到飞书多维表格"""
    config = load_config()
    base_token = config["base_token"]
    table_id = config["table_id"]

    records = []
    for stock in stocks:
        fields = {}
        for key, value in stock.items():
            if value is not None:
                fields[key] = value
        records.append({"fields": fields})

    records_json = json.dumps(records, ensure_ascii=False)

    args = [
        "base", "+record-batch-create",
        "--base-token", base_token,
        "--table-id", table_id,
        "--records", records_json,
        "--as", "user",
    ]

    result = run_lark_cmd(args)
    log(f"写入飞书表格结果: {result[:200]}")
    return result


def send_push_notification(stocks, base_url):
    """发送飞书消息推送"""
    config = load_config()

    # 构造消息内容
    today = datetime.now().strftime("%m月%d日")
    top3 = stocks[:3]

    msg_lines = [
        f"🤖 AI股神团队 - {today}选股报告",
        "",
        f"📊 今日筛选: {len(stocks)} 支关注股票",
        "",
    ]

    for i, stock in enumerate(top3, 1):
        name = stock.get("股票名称", "未知")
        code = stock.get("股票代码", "")
        score = stock.get("综合评分", 0)
        advice = stock.get("投资建议", "")
        logic = stock.get("核心逻辑", "")
        msg_lines.append(f"Top{i}. {name}({code})")
        msg_lines.append(f"   综合评分: {score}/10 | {advice}")
        msg_lines.append(f"   {logic}")
        msg_lines.append("")

    msg_lines.append(f"🔗 完整表格: {base_url}")
    msg_lines.append("")
    msg_lines.append("💡 以上由AI股神团队自动生成，仅供参考")

    message = "\n".join(msg_lines)

    # 发送给自己
    args = [
        "im", "+messages-send",
        "--user-id", config["notify_user_id"],
        "--msg-type", "text",
        "--content", message,
        "--as", "user",
    ]

    result = run_lark_cmd(args)
    log(f"推送通知结果: {result[:200]}")
    return result


def main():
    """主入口 - 由TRAE定时任务的AI分析完成后调用"""
    log("=" * 60)
    log("🚀 AI股神每日选股 - 开始执行")

    # 从命令行参数或环境变量读取股票数据
    # 实际使用时，由TRAE AI分析完成后生成数据传入
    if len(sys.argv) > 1:
        stocks_json = sys.argv[1]
    else:
        stocks_json = os.environ.get("STOCKS_DATA", "")

    if not stocks_json:
        log("❌ 未提供股票数据：拒绝写入演示/静态示例数据")
        raise SystemExit(2)

    try:
        stocks = json.loads(stocks_json)
    except json.JSONDecodeError as exc:
        log(f"❌ STOCKS_DATA 不是合法 JSON: {exc}")
        raise SystemExit(2) from exc
    if not isinstance(stocks, list):
        log("❌ STOCKS_DATA 顶层必须是 JSON 数组")
        raise SystemExit(2)

    log(f"📊 准备写入 {len(stocks)} 支股票数据")

    # 写入飞书表格
    config = load_config()
    add_records_to_base(stocks)

    # 发送推送通知
    base_url = config.get("base_url", "")
    send_push_notification(stocks, base_url)

    log("✅ 每日选股任务完成")
    log("=" * 60)


if __name__ == "__main__":
    main()
