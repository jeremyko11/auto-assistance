#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容分发中心 CLI 启动器
======================
更友好的命令行界面，带菜单导航

使用：
    python -m scripts.dispatcher.cli
    python scripts/dispatcher/cli.py
"""

import os
import sys
from pathlib import Path

# 确保项目根目录在路径中
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dispatcher.content_dispatcher import ContentDispatcher, DispatchConfig


def clear_screen():
    """清屏"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_banner():
    """打印横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║     ██████╗  ██████╗ ██████╗ ████████╗ ██████╗  ██████╗ ██████╗   ║
║     ██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝██╔═══██╗██╔═══██╗██╔══██╗  ║
║     ██████╔╝██║   ██║██████╔╝   ██║   ██║   ██║██║   ██║██████╔╝  ║
║     ██╔═══╝ ██║   ██║██╔══██╗   ██║   ██║   ██║██║   ██║██╔═══╝   ║
║     ██║     ╚██████╔╝██║  ██║   ██║   ╚██████╔╝╚██████╔╝██║       ║
║     ╚═╝      ╚═════╝ ╚═╝  ╚═╝   ╚═╝    ╚═════╝  ╚═════╝ ╚═╝       ║
║                                                                  ║
║              📦 虚拟资料商业化项目 — 内容分发中心 v2.0            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_menu():
    """打印菜单"""
    menu = """
╔══════════════════════════════════════════════════════════════════╗
║                         📋 操作菜单                              ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║   🚀 流水线                                                      ║
║      [1] 运行完整流水线 (爬取→提炼→改写→分发)                     ║
║      [2] 仅爬取阶段                                              ║
║      [3] 仅提炼阶段                                              ║
║      [4] 仅改写阶段                                              ║
║      [5] 仅分发阶段                                              ║
║                                                                  ║
║   📊 状态查看                                                    ║
║      [6] 查看当前状态                                            ║
║      [7] 查看待发布队列                                          ║
║      [8] 生成日报                                                ║
║                                                                  ║
║   ⚙️  设置                                                       ║
║      [9] 配置定时任务                                            ║
║                                                                  ║
║   [0] 退出                                                      ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(menu)


def run_dispatcher():
    """运行分发调度中心"""
    dispatcher = ContentDispatcher()

    while True:
        clear_screen()
        print_banner()
        dispatcher.show_status()
        print_menu()

        try:
            choice = input("\n请输入选项 [0-9]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n退出...")
            break

        if choice == "1":
            clear_screen()
            print_banner()
            dispatcher.run_full_pipeline()
            input("\n按回车继续...")

        elif choice == "2":
            clear_screen()
            print_banner()
            dispatcher.run_crawl()
            input("\n按回车继续...")

        elif choice == "3":
            clear_screen()
            print_banner()
            dispatcher.run_refine()
            input("\n按回车继续...")

        elif choice == "4":
            clear_screen()
            print_banner()
            platforms = input("输入目标平台 (多个用空格分隔, 默认: 微博 小红书 抖音): ").strip()
            if platforms:
                dispatcher.run_rewrite(target_platforms=platforms.split())
            else:
                dispatcher.run_rewrite()
            input("\n按回车继续...")

        elif choice == "5":
            clear_screen()
            print_banner()
            auto = input("是否自动发布? (y/N): ").strip().lower() == 'y'
            platforms = input("输入目标平台 (多个用空格分隔, 默认: 微博): ").strip()
            if platforms:
                dispatcher.run_dispatch(platforms=platforms.split(), auto=auto)
            else:
                dispatcher.run_dispatch(auto=auto)
            input("\n按回车继续...")

        elif choice == "6":
            clear_screen()
            print_banner()
            dispatcher.show_status(detailed=True)
            input("\n按回车继续...")

        elif choice == "7":
            clear_screen()
            print_banner()
            platform = input("输入平台 (直接回车查看全部): ").strip()
            dispatcher.show_queue(platform if platform else None)
            input("\n按回车继续...")

        elif choice == "8":
            clear_screen()
            print_banner()
            print(dispatcher.get_daily_report())
            input("\n按回车继续...")

        elif choice == "9":
            clear_screen()
            print_banner()
            setup_schedules()
            input("\n按回车继续...")

        elif choice == "0":
            print("\n\n👋 再见！\n")
            break

        else:
            print("无效选项，请重新输入")
            time.sleep(1)


def setup_schedules():
    """配置定时任务"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                      ⚙️ 定时任务配置                             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║   [1] 配置每日 06:00 自动运行完整流水线                           ║
║   [2] 配置每小时爬虫 + 早8点提炼                                  ║
║   [3] 查看当前定时任务                                           ║
║   [4] 删除所有定时任务                                           ║
║   [0] 返回                                                     ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")

    choice = input("请输入选项: ").strip()

    if choice == "1":
        script = PROJECT_ROOT / "scripts" / "setup_schedules.bat"
        print(f"\n请以管理员身份运行: {script}")
        print("或手动运行后选择 [1]")

    elif choice == "2":
        script = PROJECT_ROOT / "scripts" / "setup_schedules.bat"
        print(f"\n请以管理员身份运行: {script}")
        print("或手动运行后选择 [2]")

    elif choice == "3":
        os.system("schtasks /query /fo LIST | findstr VirtualInfo")

    elif choice == "4":
        confirm = input("确认删除所有定时任务? (y/N): ").strip().lower()
        if confirm == 'y':
            os.system("schtasks /delete /tn \"VirtualInfo_DailyPipeline\" /f >nul 2>&1")
            os.system("schtasks /delete /tn \"VirtualInfo_Crawler\" /f >nul 2>&1")
            os.system("schtasks /delete /tn \"VirtualInfo_RefineDispatch\" /f >nul 2>&1")
            os.system("schtasks /delete /tn \"VirtualInfo_RewriteDispatch\" /f >nul 2>&1")
            print("✅ 所有定时任务已删除")


if __name__ == "__main__":
    import time

    try:
        run_dispatcher()
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，退出...")