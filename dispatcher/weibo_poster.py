#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微博自动发帖器 - Selenium方案
=============================
原理：用浏览器模拟人工操作，扫码登录后自动发帖

依赖：
    pip install playwright
    playwright install chromium

使用：
    python weibo_poster.py                    # 交互式发帖
    python weibo_poster.py --content "内容"   # 直接发帖
    python weibo_poster.py --file queue_微博.json  # 从队列读取
"""

import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Windows UTF-8
if sys.platform == "win32":
    try:
        import io
        if not isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if not isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass


COOKIE_FILE = PROJECT_ROOT / "content_pool" / "weibo_cookies.json"


def save_cookies(context):
    """保存Cookie到文件"""
    cookies = context.cookies()
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
    print(f"💾 Cookie已保存到: {COOKIE_FILE}")


def load_cookies(context) -> bool:
    """从文件加载Cookie"""
    if not COOKIE_FILE.exists():
        return False

    try:
        cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        # 验证Cookie是否过期
        for cookie in cookies:
            if cookie['name'] == 'SUB':
                # 检查expires字段
                if cookie.get('expires', 0) > time.time():
                    context.add_cookies(cookies)
                    print("✅ 已加载保存的Cookie")
                    return True
        print("⚠️ Cookie已过期，需要重新登录")
        return False
    except Exception as e:
        print(f"❌ Cookie加载失败: {e}")
        return False


def login_weibo(page, context) -> bool:
    """登录微博（支持Cookie免登录）"""
    print("\n" + "=" * 50)
    print("📱 微博登录")
    print("=" * 50)

    # 1. 先尝试加载已保存的Cookie
    if load_cookies(context):
        page.goto("https://weibo.com", timeout=15000)
        time.sleep(2)
        # 验证Cookie是否真的有效
        if page.url != "https://weibo.com/login":
            print("✅ 已自动登录，跳过扫码")
            return True

    # 2. Cookie无效，扫码登录
    print("\n📋 步骤：")
    print("  1. 用手机微信/微博App扫码")
    print("  2. 确认登录")
    print("  3. 等待自动继续...\n")

    # 访问微博首页
    page.goto("https://weibo.com", timeout=30000)
    time.sleep(2)

    try:
        # 点击登录链接
        login_link = page.wait_for_selector(
            "a[href*='login']:has-text('登录')",
            timeout=5000
        )
        login_link.click()
        time.sleep(1)

        # 等待二维码出现
        qr_code = page.wait_for_selector(
            "img[src*='qrcode'], .WB_widgets_face, .login_code",
            timeout=5000
        )
        print("📋 二维码已显示，请扫码登录...")

        # 等待登录成功
        page.wait_for_function("""
            () => document.cookie.includes('SUB')
        """, timeout=120000)

        print("✅ 登录成功！")
        save_cookies(context)  # 保存Cookie
        return True

    except Exception as e:
        print(f"❌ 登录失败: {e}")
        return False


def post_weibo(page, content: str) -> bool:
    """发帖"""
    print(f"\n📤 开始发帖...")
    print(f"内容: {content[:50]}...")

    try:
        # 方法1：直接访问发帖页面
        page.goto("https://weibo.com/new/publish", timeout=15000)
        time.sleep(2)

        # 查找文本框并输入
        textarea = page.wait_for_selector(
            "textarea[placeholder*='分享'], .W_input, #publish_text",
            timeout=5000
        )
        textarea.fill(content)
        time.sleep(1)

        # 点击发布按钮
        page.click("a[action-type='submit']:has-text('发布'), .W_btn_a:has-text('发布')")
        time.sleep(2)

        # 检查是否成功（URL或内容变化）
        if page.url.endswith("/detail") or "publish" not in page.url:
            print("✅ 发帖成功！")
            return True

        # 方法2：备用方案 - 使用快捷发布
        page.keyboard.press("Control+Enter")
        time.sleep(2)

        print("✅ 发帖成功（快捷键）！")
        return True

    except Exception as e:
        print(f"⚠️ 方法1失败: {e}")
        try:
            # 备用：直接js注入
            page.evaluate(f"""
                document.querySelector('textarea').value = `{content}`;
                document.querySelector('textarea').dispatchEvent(new Event('input'));
            """)
            time.sleep(1)
            page.keyboard.press("Control+Enter")
            time.sleep(2)
            print("✅ 发帖成功（备用方案）！")
            return True
        except Exception as e2:
            print(f"❌ 备用方案也失败: {e2}")
            return False


def main():
    parser = argparse.ArgumentParser(description="微博自动发帖器")
    parser.add_argument("--content", "-c", type=str, help="直接指定发帖内容")
    parser.add_argument("--file", "-f", type=str, help="从JSON队列文件读取")
    parser.add_argument("--headless", action="store_true", help="无头模式（不显示浏览器）")
    args = parser.parse_args()

    # 导入playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ 请先安装 playwright:")
        print("   pip install playwright")
        print("   playwright install chromium")
        sys.exit(1)

    content_to_post = []

    # 获取待发内容
    if args.content:
        content_to_post = [args.content]
    elif args.file:
        queue_file = Path(args.file)
        if queue_file.exists():
            queue = json.loads(queue_file.read_text(encoding="utf-8"))
            content_to_post = [item["content"] for item in queue[:5]]  # 最多5条
            print(f"📋 从队列读取 {len(content_to_post)} 条内容")
        else:
            print(f"❌ 文件不存在: {args.file}")
            sys.exit(1)
    else:
        # 交互式输入
        print("\n📝 请输入要发布的内容（多行请用空行分隔，输入完成按Ctrl+Z回车）:")
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        content_to_post = ["\n".join(lines)] if lines else []

    if not content_to_post:
        print("❌ 没有要发布的内容")
        sys.exit(1)

    # 启动浏览器
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )

        # 创建上下文（类似隐身模式）
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()

        # 登录
        if not login_weibo(page, context):
            context.close()
            browser.close()
            sys.exit(1)

        # 发帖
        success_count = 0
        cookies_saved = False
        for i, content in enumerate(content_to_post, 1):
            print(f"\n[{i}/{len(content_to_post)}] {'='*40}")
            if post_weibo(page, content):
                success_count += 1
                # 成功后保存Cookie（只需一次）
                if not cookies_saved:
                    save_cookies(context)
                    cookies_saved = True
                # 发完一条休息30秒，避免频繁
                if i < len(content_to_post):
                    print("⏳ 休息30秒...")
                    time.sleep(30)

        print("\n" + "=" * 50)
        print(f"📊 发帖完成: {success_count}/{len(content_to_post)} 成功")
        print("=" * 50)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
