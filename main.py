# -*- coding: utf-8 -*-
"""AI股神团队 - 主入口脚本

使用方法::

    python main.py

交互式引导用户完成多 Agent 股票分析流程，并生成 HTML 报告。

## 结构说明

本模块**只保留入口与编排**：加载会话 → 依次跑三个团队 → 生成报告 → 可选推送。
展示与交互细节已迁至 :mod:`console`（`console.display` 负责打印与输入，
`console.teams` 负责团队阶段规格与执行）。

下方对 `console` 符号的重新导入构成**门面**：`main.print_banner` / `main.run_analyst_team`
等名称继续可用，既有调用方与测试无需改动。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from orchestrator import WorkflowOrchestrator, create_workflow
from reporting.report_generator import HTMLReportGenerator
from notify.feishu_notifier import send_analysis_summary, is_configured

from console.display import (  # noqa: F401  —— 门面重导出，供既有调用方与测试使用
    Colors,
    ask_yes_no,
    get_input,
    get_multiline_input,
    print_banner,
    print_progress_bar,
    print_stage_header,
)
from console.teams import (  # noqa: F401  —— 门面重导出
    DECISION_STAGES,
    RESEARCH_STAGES,
    ANALYST_STAGES,
    StageSpec,
    run_analyst_team,
    run_decision_team,
    run_research_team,
)


def generate_final_report(orch: WorkflowOrchestrator) -> str:
    """生成最终 HTML 报告。"""
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
    print(f"{Colors.GREEN}📄 正在生成HTML分析报告...{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 70}{Colors.END}\n")

    generator = HTMLReportGenerator(orch.session)
    report_path = generator.save(f"reports/{orch.session.session_id}.html")

    print(f"{Colors.GREEN}✅ HTML报告已生成！{Colors.END}")
    print(f"{Colors.CYAN}📂 报告路径: {os.path.abspath(report_path)}{Colors.END}\n")
    return report_path


def load_existing_session() -> Optional[WorkflowOrchestrator]:
    """加载已有会话；无可加载会话时返回 None。"""
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        return None

    json_files = [f for f in os.listdir(reports_dir) if f.endswith(".json")]
    if not json_files:
        return None

    json_files.sort(key=lambda x: os.path.getmtime(os.path.join(reports_dir, x)), reverse=True)

    print(f"\n{Colors.BOLD}📂 发现以下未完成的分析会话：{Colors.END}")
    for i, f in enumerate(json_files[:5], 1):
        mtime = datetime.fromtimestamp(os.path.getmtime(os.path.join(reports_dir, f)))
        print(f"  {i}. {f} ({mtime.strftime('%Y-%m-%d %H:%M:%S')})")
    print("  0. 开始新分析")

    choice = get_input(f"请选择要加载的会话编号 (0-{min(5, len(json_files))}): ", required=False)

    if choice == "0" or not choice:
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(json_files):
            filepath = os.path.join(reports_dir, json_files[idx])
            print(f"{Colors.GREEN}✅ 已加载会话: {json_files[idx]}{Colors.END}")
            return WorkflowOrchestrator.load_session(filepath)
    except (ValueError, IndexError):
        pass

    return None


def main() -> None:
    """主函数。"""
    print_banner()

    orch = load_existing_session()

    if orch is None:
        print(f"\n{Colors.BOLD}🚀 开始新的股票分析{Colors.END}\n")
        stock_code = get_input("请输入股票代码 (如: AAPL, TSLA, 600519): ")
        company_name = get_input("请输入公司名称 (可选，直接回车跳过): ", required=False)

        orch = create_workflow(stock_code, company_name)
        orch.save_session()

        print(f"\n{Colors.GREEN}✅ 分析会话已创建！{Colors.END}")
        print(f"{Colors.CYAN}📊 股票代码: {stock_code}{Colors.END}")
        print(f"{Colors.CYAN}🏢 公司名称: {company_name or stock_code}{Colors.END}")
        print(f"{Colors.CYAN}🔍 Session ID: {orch.session.session_id}{Colors.END}\n")
    else:
        print(f"\n{Colors.GREEN}📊 继续分析: {orch.session.stock_code}{Colors.END}")
        print(f"{Colors.CYAN}当前阶段: {orch.get_progress()['current_stage_name']}{Colors.END}\n")

    print(f"{Colors.BOLD}🎯 开始多维度分析流程...{Colors.END}\n")

    run_analyst_team(orch)
    run_research_team(orch)
    run_decision_team(orch)

    if orch.is_completed():
        report_path = generate_final_report(orch)

        # 自动推送分析摘要到飞书：不影响本地报告生成，即使推送失败也不中断流程。
        if is_configured():
            push_result = send_analysis_summary(orch.session, report_path)
            if push_result.get("ok"):
                print(f"{Colors.GREEN}📨 分析摘要已成功发送到飞书！{Colors.END}")
            else:
                print(f"{Colors.WARNING}⚠️ 飞书推送失败：{push_result.get('message', '')}{Colors.END}")
        else:
            print(f"{Colors.WARNING}ℹ️ 未完成飞书配置或未安装 lark-cli，本次仅生成本地报告。{Colors.END}")

        print(f"\n{Colors.CYAN}")
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                                                              ║")
        print("║              🎉 AI股神团队分析流程已全部完成！                ║")
        print("║                                                              ║")
        print(f"║     📄 HTML报告: reports/{orch.session.session_id}.html          ║")
        print("║                                                              ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print(f"{Colors.END}\n")

        if ask_yes_no("是否现在打开HTML报告?", default=True):
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(report_path)}")
    else:
        print(f"\n{Colors.WARNING}⚠️  分析尚未完成，进度: {orch.get_progress()['progress_percent']}%{Colors.END}")
        print(f"{Colors.CYAN}💡 您可以随时重新运行 main.py 继续分析。{Colors.END}\n")


if __name__ == "__main__":
    main()
