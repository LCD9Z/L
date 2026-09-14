# -*- coding: utf-8 -*-
"""终端展示与交互层。

从 `main.py` 原样迁出（**零逻辑改动**）：终端颜色常量、打印辅助、输入辅助。
这些函数与业务流程无关，迁出后 `main.py` 只保留编排职责。

共同红线：

* **输入辅助必须能安全退出**：`EOFError` / `KeyboardInterrupt` 走 `sys.exit(0)`，
  不得抛出未捕获异常（交互式入口被管道或 Ctrl-C 中断是常态）。
* **`required=True` 时空输入必须重试**，不得返回空串 —— 股票代码为空会污染后续会话。
* 本层**不做任何业务判断**，只负责「读一行」「打一段」。
"""
from __future__ import annotations

import sys
from typing import List


class Colors:
    """终端 ANSI 颜色。"""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    END = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_banner() -> None:
    """打印启动横幅。"""
    banner = f"""
{Colors.CYAN}
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     🤖 AI股神团队 - 多维度智能股票分析系统                    ║
║                                                              ║
║     📊 基本面  🗣️ 情绪  📰 新闻  📈 技术                     ║
║     🐂 看多  🐻 看空  🧑‍💼 交易  🛡️ 风控                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
{Colors.END}
"""
    print(banner)


def print_progress_bar(progress: int, width: int = 50) -> None:
    """打印进度条。越界进度按 0~100 裁剪，避免条形渲染错乱。"""
    pct = max(0, min(100, int(progress)))
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    print(f"\n{Colors.CYAN}进度: [{bar}] {progress}%{Colors.END}\n")


def print_stage_header(title: str, emoji: str, description: str) -> None:
    """打印阶段标题。"""
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
    print(f"{Colors.GREEN}{emoji} {title}{Colors.END}")
    print(f"{Colors.BLUE}{description}{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 70}{Colors.END}\n")


def get_input(prompt: str, required: bool = True) -> str:
    """获取用户输入。`required=True` 时空输入重试；EOF/中断则干净退出。"""
    while True:
        try:
            value = input(f"{Colors.CYAN}{prompt}{Colors.END}").strip()
            if required and not value:
                print(f"{Colors.WARNING}⚠️  输入不能为空，请重新输入。{Colors.END}")
                continue
            return value
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Colors.FAIL}👋 再见！{Colors.END}")
            sys.exit(0)


def get_multiline_input(prompt: str) -> str:
    """获取多行输入；空行（在有内容后）或 ``END`` 结束。"""
    print(f"{Colors.CYAN}{prompt}{Colors.END}")
    print(f"{Colors.WARNING}(输入空行结束，或输入 'END' 结束){Colors.END}")
    lines: List[str] = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "END" or (lines and not line.strip()):
                break
            lines.append(line)
        except (EOFError, KeyboardInterrupt):
            break
    return "\n".join(lines)


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """询问是/否；空输入返回默认值，非法输入重试。"""
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        answer = input(f"{Colors.CYAN}{prompt}{suffix}{Colors.END}").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes", "是"):
            return True
        if answer in ("n", "no", "否"):
            return False
        print(f"{Colors.WARNING}⚠️  请输入 y 或 n{Colors.END}")
