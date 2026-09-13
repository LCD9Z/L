# -*- coding: utf-8 -*-
"""
AI股神团队 - 快速入口
Usage:
    python stock_god.py analyze <股票代码>    # 分析单只股票
    python stock_god.py ppt <股票代码>        # 生成PPT报告
    python stock_god.py daily                  # 每日选股
"""

import sys
import os

WORK_DIR = os.path.dirname(os.path.abspath(__file__))


def print_help():
    print("""
🤖 AI股神团队 - 使用指南

用法:
  python stock_god.py analyze <股票代码>    分析单只股票，生成HTML报告
  python stock_god.py ppt <股票代码>        生成PPT格式分析报告
  python stock_god.py daily                  每日选股（写入飞书表格+推送）

示例:
  python stock_god.py analyze 600519
  python stock_god.py ppt AAPL
  python stock_god.py daily
""")


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    cmd = sys.argv[1].lower()

    if cmd == 'analyze':
        if len(sys.argv) < 3:
            print("❌ 请输入股票代码")
            print("   用法: python stock_god.py analyze <股票代码>")
            return
        stock = sys.argv[2]
        print(f"📊 AI股神团队开始分析: {stock}")
        print("   请在TRAE对话中描述你要分析的股票，AI将自动调用股神团队")
        print(f"   报告将保存在: {WORK_DIR}/reports/")

    elif cmd == 'ppt':
        if len(sys.argv) < 3:
            print("❌ 请输入股票代码")
            print("   用法: python stock_god.py ppt <股票代码>")
            return
        stock = sys.argv[2]
        print(f"📊 AI股神团队生成PPT报告: {stock}")
        print("   请在TRAE对话中要求生成PPT报告")

    elif cmd == 'daily':
        print("📈 启动每日选股任务")
        print("   请在TRAE对话中输入'每日选股'")

    elif cmd in ['help', '-h', '--help']:
        print_help()

    else:
        print(f"❌ 未知命令: {cmd}")
        print_help()


if __name__ == "__main__":
    main()
