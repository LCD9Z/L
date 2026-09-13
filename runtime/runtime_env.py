# -*- coding: utf-8 -*-
"""每日选股 · 运行环境（路径 / 日志 / 配置加载）。

由 daily_stock_pick.py 拆分而来（1.0）。本模块**不依赖项目内其他模块**，
供 stock_scoring / pool_manager / industry_context / lark_notify 共用，
避免拆分后出现循环导入。

运行时状态目录默认外置到 ~/.ai-stock-god/（数据卫生设计），可用环境变量覆盖：
    AI_STOCK_WATCHLIST_FILE  股票池路径
    AI_STOCK_STATE_DIR       状态目录（候选池 / 游标）
    AI_STOCK_LOG_DIR         日志目录
"""
import json
import os
import sys
from datetime import datetime

# 确保项目根目录在 sys.path（供同目录模块互相导入）
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
if WORK_DIR not in sys.path:
    sys.path.insert(0, WORK_DIR)

WATCHLIST_FILE = os.environ.get("AI_STOCK_WATCHLIST_FILE", os.path.join(os.path.expanduser("~"), ".ai-stock-god", "watchlist.json"))
CONFIG_FILE = os.path.join(WORK_DIR, "feishu_config.json")
LOG_FILE = os.path.join(os.environ.get("AI_STOCK_LOG_DIR", os.path.join(WORK_DIR, "runtime_logs")), "daily_stock_pick.log")
REPORT_DIR = os.path.join(WORK_DIR, "reports", "daily")
STATE_DIR = os.environ.get("AI_STOCK_STATE_DIR", os.path.join(os.path.expanduser("~"), ".ai-stock-god"))
CANDIDATE_FILE = os.path.join(STATE_DIR, "candidate_pool.json")
POOL_STATE_FILE = os.path.join(STATE_DIR, "pool_state.json")


def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s" % (timestamp, msg)
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        raise FileNotFoundError(
            "未找到每日选股股票池：%s。请通过 AI_STOCK_WATCHLIST_FILE 指定外部股票池；禁止使用项目内静态/历史股票池。" % WATCHLIST_FILE
        )
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
