# -*- coding: utf-8 -*-
"""
AI股神团队 - 主入口脚本

使用方法:
    python main.py

交互式引导用户完成多Agent股票分析流程，并生成HTML报告。
"""

import os
import sys
from datetime import datetime
from typing import List, Optional

from orchestrator import WorkflowOrchestrator, create_workflow
from reporting.report_generator import HTMLReportGenerator
from feishu_notifier import send_analysis_summary, is_configured


class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_banner():
    """打印启动横幅"""
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


def print_progress_bar(progress: int, width: int = 50):
    """打印进度条"""
    filled = int(width * progress / 100)
    bar = '█' * filled + '░' * (width - filled)
    print(f"\n{Colors.CYAN}进度: [{bar}] {progress}%{Colors.END}\n")


def print_stage_header(title: str, emoji: str, description: str):
    """打印阶段标题"""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.GREEN}{emoji} {title}{Colors.END}")
    print(f"{Colors.BLUE}{description}{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")


def get_input(prompt: str, required: bool = True) -> str:
    """获取用户输入"""
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
    """获取多行输入"""
    print(f"{Colors.CYAN}{prompt}{Colors.END}")
    print(f"{Colors.WARNING}(输入空行结束，或输入 'END' 结束){Colors.END}")
    lines: List[str] = []
    while True:
        try:
            line = input()
            if line.strip().upper() == 'END' or (lines and not line.strip()):
                break
            lines.append(line)
        except (EOFError, KeyboardInterrupt):
            break
    return '\n'.join(lines)


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """询问是/否"""
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        answer = input(f"{Colors.CYAN}{prompt}{suffix}{Colors.END}").strip().lower()
        if not answer:
            return default
        if answer in ('y', 'yes', '是'):
            return True
        if answer in ('n', 'no', '否'):
            return False
        print(f"{Colors.WARNING}⚠️  请输入 y 或 n{Colors.END}")


def run_analyst_team(orch: WorkflowOrchestrator):
    """运行分析师团队"""
    analyst_stages = [
        ("analyst_fundamental", "📊 基本面分析师", "深度挖掘公司财务与价值"),
        ("analyst_sentiment", "🗣️ 情绪分析师", "追踪市场情绪与舆情"),
        ("analyst_news", "📰 新闻分析师", "解读宏观事件与公司动态"),
        ("analyst_technical", "📈 技术分析师", "分析价格行为与技术指标"),
    ]
    
    for stage, title, desc in analyst_stages:
        if orch.session.current_stage != stage:
            continue
            
        print_stage_header(title, title[0], desc)
        
        # 获取提示词
        prompt = orch.get_next_prompt()
        if not prompt:
            print(f"{Colors.WARNING}⚠️ 该阶段无可用提示词，跳过：{stage}{Colors.END}")
            continue
        
        print(f"{Colors.BOLD}📝 请将此提示词复制到TRAE聊天中，获取AI分析结果：{Colors.END}\n")
        print(f"{Colors.WARNING}{'─'*70}{Colors.END}")
        print(prompt)
        print(f"{Colors.WARNING}{'─'*70}{Colors.END}\n")
        
        # 保存提示词到文件（方便复制）
        prompt_file = f"reports/{orch.session.session_id}_{stage}_prompt.txt"
        os.makedirs("reports", exist_ok=True)
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"{Colors.GREEN}✅ 提示词已保存到: {prompt_file}{Colors.END}\n")
        
        # 获取分析结果
        print(f"{Colors.BOLD}📥 请将AI返回的分析结果粘贴 below (输入空行结束):{Colors.END}")
        result = get_multiline_input("")
        
        if not result.strip():
            print(f"{Colors.WARNING}⚠️  未输入内容，跳过此步骤。{Colors.END}")
            continue
        
        # 询问评分和建议
        print(f"\n{Colors.BOLD}📊 请提取分析中的评分和建议:{Colors.END}")
        score_str = get_input("评分 (1-10，如无可直接回车跳过): ", required=False)
        score = float(score_str) if score_str else None
        
        recommendation = get_input("投资建议 (如：强烈买入/买入/持有/卖出/强烈卖出): ", required=False)
        
        # 提交结果
        orch.submit_result(stage, result, score, recommendation)
        orch.save_session()
        
        progress = orch.get_progress()
        print_progress_bar(progress["progress_percent"])
        
        print(f"{Colors.GREEN}✅ {title} 分析已完成并保存！{Colors.END}\n")


def run_research_team(orch: WorkflowOrchestrator):
    """运行研究员团队（辩论）"""
    research_stages = [
        ("research_bullish", "🐂 看多研究员", "寻找买入理由，构建做多逻辑"),
        ("research_bearish", "🐻 看空研究员", "寻找风险信号，构建避险逻辑"),
    ]
    
    for stage, title, desc in research_stages:
        if orch.session.current_stage != stage:
            continue
        
        print_stage_header(title, title[0], desc)
        
        # 获取提示词
        prompt = orch.get_next_prompt()
        if not prompt:
            print(f"{Colors.WARNING}⚠️ 该阶段无可用提示词，跳过：{stage}{Colors.END}")
            continue
        
        print(f"{Colors.BOLD}📝 请将此提示词复制到TRAE聊天中：{Colors.END}\n")
        print(f"{Colors.WARNING}{'─'*70}{Colors.END}")
        print(prompt)
        print(f"{Colors.WARNING}{'─'*70}{Colors.END}\n")
        
        # 保存提示词
        prompt_file = f"reports/{orch.session.session_id}_{stage}_prompt.txt"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"{Colors.GREEN}✅ 提示词已保存到: {prompt_file}{Colors.END}\n")
        
        # 获取分析结果
        print(f"{Colors.BOLD}📥 请将AI返回的分析结果粘贴 below (输入空行结束):{Colors.END}")
        result = get_multiline_input("")
        
        if not result.strip():
            print(f"{Colors.WARNING}⚠️  未输入内容，跳过此步骤。{Colors.END}")
            continue
        
        # 询问评分
        score_str = get_input("强度评分 (1-10): ", required=False)
        score = float(score_str) if score_str else None
        
        recommendation = get_input("建议 (如：重仓/中等/轻仓/卖出/观望): ", required=False)
        
        # 提交结果
        orch.submit_result(stage, result, score, recommendation)
        orch.save_session()
        
        progress = orch.get_progress()
        print_progress_bar(progress["progress_percent"])
        
        print(f"{Colors.GREEN}✅ {title} 论证已完成并保存！{Colors.END}\n")


def run_decision_team(orch: WorkflowOrchestrator):
    """运行决策团队"""
    decision_stages = [
        ("decision_trade", "🧑‍💼 交易员", "综合研判，制定交易策略"),
        ("decision_risk", "🛡️ 风控官&投资经理", "风险评估，最终审批"),
    ]
    
    for stage, title, desc in decision_stages:
        if orch.session.current_stage != stage:
            continue
        
        print_stage_header(title, title[0], desc)
        
        # 获取提示词
        prompt = orch.get_next_prompt()
        if not prompt:
            print(f"{Colors.WARNING}⚠️ 该阶段无可用提示词，跳过：{stage}{Colors.END}")
            continue
        
        print(f"{Colors.BOLD}📝 请将此提示词复制到TRAE聊天中：{Colors.END}\n")
        print(f"{Colors.WARNING}{'─'*70}{Colors.END}")
        print(prompt)
        print(f"{Colors.WARNING}{'─'*70}{Colors.END}\n")
        
        # 保存提示词
        prompt_file = f"reports/{orch.session.session_id}_{stage}_prompt.txt"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"{Colors.GREEN}✅ 提示词已保存到: {prompt_file}{Colors.END}\n")
        
        # 获取分析结果
        print(f"{Colors.BOLD}📥 请将AI返回的分析结果粘贴 below (输入空行结束):{Colors.END}")
        result = get_multiline_input("")
        
        if not result.strip():
            print(f"{Colors.WARNING}⚠️  未输入内容，跳过此步骤。{Colors.END}")
            continue
        
        # 询问评分和建议
        if stage == "decision_trade":
            score_str = get_input("信心评分 (1-10): ", required=False)
            score = float(score_str) if score_str else None
            recommendation = get_input("交易指令 (如：强烈买入/买入/持有/卖出/强烈卖出): ", required=False)
        else:
            score_str = get_input("风险等级 (1-10): ", required=False)
            score = float(score_str) if score_str else None
            recommendation = get_input("审批结果 (如：批准/拒绝/有条件批准): ", required=False)
        
        # 提交结果
        orch.submit_result(stage, result, score, recommendation)
        orch.save_session()
        
        progress = orch.get_progress()
        print_progress_bar(progress["progress_percent"])
        
        print(f"{Colors.GREEN}✅ {title} 决策已完成并保存！{Colors.END}\n")


def generate_final_report(orch: WorkflowOrchestrator) -> str:
    """生成最终HTML报告"""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.GREEN}📄 正在生成HTML分析报告...{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")
    
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
    
    json_files = [f for f in os.listdir(reports_dir) if f.endswith('.json')]
    if not json_files:
        return None
    
    # 按修改时间排序
    json_files.sort(key=lambda x: os.path.getmtime(os.path.join(reports_dir, x)), reverse=True)
    
    print(f"\n{Colors.BOLD}📂 发现以下未完成的分析会话：{Colors.END}")
    for i, f in enumerate(json_files[:5], 1):
        mtime = datetime.fromtimestamp(os.path.getmtime(os.path.join(reports_dir, f)))
        print(f"  {i}. {f} ({mtime.strftime('%Y-%m-%d %H:%M:%S')})")
    print("  0. 开始新分析")
    
    choice = get_input(f"请选择要加载的会话编号 (0-{min(5, len(json_files))}): ", required=False)
    
    if choice == '0' or not choice:
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


def main():
    """主函数"""
    print_banner()
    
    # 尝试加载已有会话
    orch = load_existing_session()
    
    if orch is None:
        # 开始新分析
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
    
    # 运行分析流程
    print(f"{Colors.BOLD}🎯 开始多维度分析流程...{Colors.END}\n")
    
    # 分析师团队
    run_analyst_team(orch)
    
    # 研究员团队
    run_research_team(orch)
    
    # 决策团队
    run_decision_team(orch)
    
    # 生成最终报告
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

        # 完成总结
        print(f"\n{Colors.CYAN}")
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                                                              ║")
        print("║              🎉 AI股神团队分析流程已全部完成！                ║")
        print("║                                                              ║")
        print(f"║     📄 HTML报告: reports/{orch.session.session_id}.html          ║")
        print("║                                                              ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print(f"{Colors.END}\n")
        
        # 询问是否打开报告
        if ask_yes_no("是否现在打开HTML报告?", default=True):
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(report_path)}")
    else:
        print(f"\n{Colors.WARNING}⚠️  分析尚未完成，进度: {orch.get_progress()['progress_percent']}%{Colors.END}")
        print(f"{Colors.CYAN}💡 您可以随时重新运行 main.py 继续分析。{Colors.END}\n")


if __name__ == "__main__":
    main()
