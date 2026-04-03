#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书自动发帖器 - Playwright方案
=================================
参考 content-pilot 项目实现

原理：
1. 访问 creator.xiaohongshu.com 扫码登录
2. 保存Session（Cookie + LocalStorage）
3. 自动发帖：上传图片 → 填标题 → 填正文 → 加话题 → 发布

依赖：
    pip install playwright
    playwright install chromium

使用：
    python xiaohongshu_poster.py                    # 交互式发帖
    python xiaohongshu_poster.py --content "内容"  # 直接发帖
    python xiaohongshu_poster.py --file queue_小红书.json  # 从队列读取
"""

import sys
import time
import json
import asyncio
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


# ═══════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════

CREATOR_URL = "https://creator.xiaohongshu.com"
LOGIN_URL = "https://creator.xiaohongshu.com/login"
PUBLISH_URL = "https://creator.xiaohongshu.com/explore/publish"

SESSION_FILE = PROJECT_ROOT / "content_pool" / "xiaohongshu_state.json"

# ═══════════════════════════════════════════════════════════════════════════
# Stealth JS - 反检测
# ═══════════════════════════════════════════════════════════════════════════

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
"""


# ═══════════════════════════════════════════════════════════════════════════
# 人类行为模拟
# ═══════════════════════════════════════════════════════════════════════════

def random_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """随机延迟"""
    import random
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def human_type(page, selector: str, text: str):
    """模拟人类打字"""
    import random
    page.click(selector)
    for char in text:
        page.keyboard.type(char, delay=random.uniform(0.05, 0.15))
        # 5%概率长停顿
        if random.random() < 0.05:
            time.sleep(random.uniform(0.3, 0.8))


# ═══════════════════════════════════════════════════════════════════════════
# 小红书发帖器
# ═══════════════════════════════════════════════════════════════════════════

class XiaohongshuPoster:
    """小红书自动发帖器"""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None

    async def setup(self, headless: bool = False):
        """初始化浏览器"""
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        # 创建上下文
        context_options = {
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }

        # 加载已保存的Session
        if SESSION_FILE.exists():
            try:
                context_options["storage_state"] = str(SESSION_FILE)
                print("✅ 已加载保存的登录状态")
            except Exception as e:
                print(f"⚠️ 加载Session失败: {e}")

        self.context = self.browser.new_context(**context_options)

        # 注入Stealth JS
        self.context.add_init_script(STEALTH_JS)

        return self

    async def login(self) -> bool:
        """扫码登录"""
        print("\n" + "=" * 50)
        print("📱 小红书登录")
        print("=" * 50)

        page = self.context.new_page()

        try:
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            random_delay(1, 3)

            # 等待二维码出现
            qr_selector = 'img[src^="data:image/png"]'
            try:
                qr_element = page.wait_for_selector(qr_selector, timeout=15000)
                print("\n📋 二维码已显示，请用小红书App扫码登录...")
                print("   (手机上：我的 → 扫一扫)")
            except Exception:
                # 可能已经登录了
                if "login" not in page.url.lower():
                    print("✅ 已登录，跳过扫码")
                    await page.close()
                    return True
                raise Exception("未找到二维码")

            # 等待登录成功（URL不再包含login）
            page.wait_for_url(lambda url: "login" not in url.lower(), timeout=120000)
            print("✅ 登录成功！")

            # 保存Session
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.context.storage_state(path=str(SESSION_FILE))
            print(f"💾 登录状态已保存到: {SESSION_FILE}")

            await page.close()
            return True

        except Exception as e:
            print(f"❌ 登录失败: {e}")
            await page.close()
            return False

    async def check_login(self) -> bool:
        """检查登录状态"""
        page = self.context.new_page()
        try:
            await page.goto(CREATOR_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            is_logged_in = "login" not in page.url.lower()
            await page.close()
            return is_logged_in
        except Exception:
            await page.close()
            return False

    async def post(self, title: str, content: str, images: list = None, tags: list = None) -> bool:
        """发布图文笔记"""
        if images is None:
            images = []
        if tags is None:
            tags = []

        page = self.context.new_page()

        try:
            print(f"\n📤 开始发帖...")
            print(f"标题: {title[:30]}...")
            print(f"内容: {content[:50]}...")

            # Step 1: 导航到发布页
            await page.goto(PUBLISH_URL, wait_until="networkidle", timeout=60000)
            random_delay(3, 6)

            # Step 2: 点击"上传图文"tab (默认是视频)
            tabs = await page.query_selector_all('span.title')
            for tab in tabs:
                text = (await tab.text_content() or "").strip()
                if "图文" in text:
                    await tab.evaluate("e => e.click()")
                    print("✅ 切换到图文模式")
                    break

            random_delay(1, 2)

            # Step 3: 上传图片
            if images:
                file_input = await page.wait_for_selector('input.upload-input', timeout=10000, state="attached")
                await file_input.set_input_files(images)
                print(f"✅ 已上传 {len(images)} 张图片")
            else:
                # 无图片时创建占位图
                placeholder = await self._create_placeholder()
                file_input = await page.wait_for_selector('input.upload-input', timeout=10000, state="attached")
                await file_input.set_input_files([placeholder])
                print("✅ 已上传占位图")

            random_delay(4, 8)  # 等待图片上传

            # Step 4: 填写标题
            title_input = page.wait_for_selector('input[placeholder*="标题"]', timeout=15000)
            await title_input.fill(title[:20])
            print("✅ 已填写标题")

            random_delay(1, 2)

            # Step 5: 填写正文 (TipTap编辑器)
            content_selector = '.tiptap.ProseMirror[contenteditable="true"]'
            content_input = page.wait_for_selector(content_selector, timeout=10000)
            await content_input.click()
            await page.keyboard.type(content, delay=50)
            print("✅ 已填写正文")

            # Step 6: 添加话题标签
            for tag in tags[:5]:
                await page.keyboard.type(f" #{tag}", delay=50)
                random_delay(0.5, 1.0)
            if tags:
                print(f"✅ 已添加 {min(len(tags), 5)} 个话题")

            random_delay(2, 4)

            # Step 7: 点击发布
            publish_btn = page.wait_for_selector('button:has-text("发布")', timeout=10000)
            await publish_btn.click()
            print("✅ 已点击发布")

            # Step 8: 等待发布成功
            random_delay(3, 5)
            try:
                page.wait_for_url(lambda url: "publish" not in url.lower(), timeout=30000)
            except Exception:
                pass  # URL可能没变但已成功

            print("✅ 发帖成功！")
            await page.close()
            return True

        except Exception as e:
            print(f"❌ 发帖失败: {e}")
            # 打印页面HTML帮助调试
            try:
                html = await page.content()
                print(f"页面URL: {page.url}")
            except Exception:
                pass
            await page.close()
            return False

    async def _create_placeholder(self) -> str:
        """创建占位图"""
        from PIL import Image
        import io

        # 创建灰色占位图
        img = Image.new('RGB', (800, 800), color=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)

        placeholder_path = PROJECT_ROOT / "content_pool" / "placeholder.png"
        placeholder_path.parent.mkdir(parents=True, exist_ok=True)
        with open(placeholder_path, 'wb') as f:
            f.write(buf.read())

        return str(placeholder_path)

    async def close(self):
        """关闭浏览器"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


# ═══════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="小红书自动发帖器")
    parser.add_argument("--content", "-c", type=str, help="直接指定发帖内容")
    parser.add_argument("--title", "-t", type=str, help="帖子标题（默认自动生成）")
    parser.add_argument("--file", "-f", type=str, help="从JSON队列文件读取")
    parser.add_argument("--headless", action="store_true", help="无头模式（不显示浏览器）")
    args = parser.parse_args()

    content_to_post = []

    # 获取待发内容
    if args.file:
        queue_file = Path(args.file)
        if queue_file.exists():
            queue = json.loads(queue_file.read_text(encoding="utf-8"))
            for item in queue[:5]:  # 最多5条
                content_to_post.append({
                    "title": item.get("title", args.title or "标题"),
                    "content": item["content"],
                    "tags": item.get("tags", [])
                })
            print(f"📋 从队列读取 {len(content_to_post)} 条内容")
        else:
            print(f"❌ 文件不存在: {args.file}")
            sys.exit(1)
    elif args.content:
        content_to_post = [{
            "title": args.title or "自动生成标题",
            "content": args.content,
            "tags": ["成长", "干货", "分享"]
        }]
    else:
        print("请使用 --content 或 --file 指定内容")
        sys.exit(1)

    if not content_to_post:
        print("❌ 没有要发布的内容")
        sys.exit(1)

    # 运行异步任务
    async def run():
        poster = XiaohongshuPoster()
        await poster.setup(headless=args.headless)

        # 检查是否已登录
        if not await poster.check_login():
            if not await poster.login():
                await poster.close()
                sys.exit(1)

        success_count = 0
        for i, item in enumerate(content_to_post, 1):
            print(f"\n[{i}/{len(content_to_post)}] {'='*40}")
            if await poster.post(
                title=item["title"],
                content=item["content"],
                tags=item.get("tags", [])
            ):
                success_count += 1
                if i < len(content_to_post):
                    print("⏳ 休息60秒...")
                    time.sleep(60)  # 小红书间隔要长一些

        print("\n" + "=" * 50)
        print(f"📊 发帖完成: {success_count}/{len(content_to_post)} 成功")
        print("=" * 50)

        await poster.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
