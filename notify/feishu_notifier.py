# -*- coding: utf-8 -*-
"""飞书通知模块：统一推送每日选股和单股深度分析结果。

优先从环境变量读取敏感配置；兼容旧版 feishu_config.json（非敏感字段）。
依赖已存在的 lark-cli，并以参数列表执行，避免 shell 拼接导致的转义问题。
"""
import json
import os
import shutil
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(WORK_DIR, "feishu_config.json")


def _read_config() -> Dict:
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    # 环境变量优先，避免密钥进入压缩包/Git。
    mapping = {
        "base_token": "FEISHU_BASE_TOKEN",
        "table_id": "FEISHU_TABLE_ID",
        "base_url": "FEISHU_BASE_URL",
        "notify_user_id": "FEISHU_NOTIFY_USER_ID",
        "notify_chat_id": "FEISHU_NOTIFY_CHAT_ID",
    }
    for key, env_key in mapping.items():
        value = os.getenv(env_key)
        if value:
            cfg[key] = value
    return cfg


def is_configured() -> bool:
    cfg = _read_config()
    return bool((cfg.get("notify_user_id") or cfg.get("notify_chat_id")) and shutil.which("lark-cli"))


def _run_lark(args):
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    try:
        result = subprocess.run(
            ["lark-cli", *args], cwd=WORK_DIR, env=env,
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def build_analysis_message(session, report_path: Optional[str] = None) -> str:
    """将多Agent分析压缩成适合飞书阅读的摘要。"""
    lines = [
        "🤖 AI股神 · A股深度分析完成",
        f"📌 标的：{session.company_name}（{session.stock_code}）",
        f"🕒 分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    score_map = {
        "analyst_fundamental": "📊 基本面",
        "analyst_sentiment": "🗣️ 情绪面",
        "analyst_news": "📰 消息面",
        "analyst_technical": "📈 技术面",
    }
    for key, label in score_map.items():
        item = session.analyst_reports.get(key)
        if item:
            score = "未评分" if item.score is None else f"{item.score}/10"
            rec = item.recommendation or "待综合判断"
            lines.append(f"{label}：{score}｜{rec}")

    if session.trade_proposal:
        lines += ["", "🧑‍💼 交易建议："]
        if session.trade_proposal.recommendation:
            lines.append(f"• {session.trade_proposal.recommendation}")
        if session.trade_proposal.score is not None:
            lines.append(f"• 信心评分：{session.trade_proposal.score}/10")
        text = (session.trade_proposal.content or "").strip().replace("\n", " ")
        if text:
            lines.append(f"• 摘要：{text[:500]}")

    if session.final_decision:
        lines += ["", "🛡️ 风控结论："]
        if session.final_decision.recommendation:
            lines.append(f"• {session.final_decision.recommendation}")
        if session.final_decision.score is not None:
            lines.append(f"• 风险评分：{session.final_decision.score}/10")
        text = (session.final_decision.content or "").strip().replace("\n", " ")
        if text:
            lines.append(f"• 摘要：{text[:500]}")

    lines += ["", "⚠️ 本系统输出仅用于研究和辅助决策，不构成任何投资建议。"]
    if report_path:
        lines.append(f"📄 本地报告已生成：{os.path.basename(report_path)}")
    return "\n".join(lines)


def send_analysis_summary(session, report_path: Optional[str] = None) -> Dict:
    cfg = _read_config()
    message = build_analysis_message(session, report_path)
    user_id = cfg.get("notify_user_id")
    chat_id = cfg.get("notify_chat_id")
    if not (user_id or chat_id):
        return {"ok": False, "message": "未配置 FEISHU_NOTIFY_USER_ID 或 FEISHU_NOTIFY_CHAT_ID"}
    if not shutil.which("lark-cli"):
        return {"ok": False, "message": "未检测到 lark-cli，跳过飞书推送"}

    target: List[str] = ["im", "+messages-send"]
    if chat_id:
        target += ["--chat-id", chat_id]
    else:
        if not user_id:
            return {"ok": False, "message": "未配置推送目标（chat_id / user_id 均为空）"}
        target += ["--user-id", user_id]
    target += ["--text", message, "--as", "user"]
    ok, output = _run_lark(target)
    return {"ok": ok, "message": output[:500], "content": message}
