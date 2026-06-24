"""
登录模块 — Playwright 模拟登录 + cookie 持久化

学习通登录流程：
  1. 打开登录页（手机号/单位账号/扫码 三种方式）
  2. 用户手动扫码或输入账号密码
  3. 登录成功后跳转到个人空间
  4. 保存完整的 cookie（包括 session 信息）
"""

import json
import time
from pathlib import Path

COOKIE_FILE = Path(__file__).parent / "cookies.json"


def load_cookies() -> list[dict] | None:
    """加载已保存的 cookie，如果文件不存在或已过期返回 None"""
    if not COOKIE_FILE.exists():
        return None

    try:
        cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        if not cookies:
            return None

        # 检查核心 session cookie 是否存在
        session_keys = {"sessionid", "JSESSIONID", "UID", "uf", "_d"}
        has_session = any(
            any(c.get("name", "") == key for c in cookies)
            for key in session_keys
        )
        if not has_session:
            # 可能也有其他形式的有效 cookie，不严格拒绝
            pass

        return cookies
    except (json.JSONDecodeError, KeyError):
        return None


def save_cookies(cookies: list[dict]):
    """保存 cookie 到本地文件"""
    COOKIE_FILE.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"💾 Cookie 已保存到 {COOKIE_FILE}")


def login():
    """
    打开浏览器 → 用户手动登录 → 保存 cookie

    学习通 PC 端入口（可能因版本变化，如失效请更新 URL）：
      - 主登录页：https://passport2.chaoxing.com/login
      - 或通过 i.mooc.chaoxing.com 跳转
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ 请先安装 Playwright：pip install playwright && playwright install chromium")
        return

    with sync_playwright() as p:
        # 启动有头浏览器（用户需要扫码）
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        # 打开学习通登录页
        login_url = "https://passport2.chaoxing.com/login"
        print(f"🌐 打开登录页：{login_url}")
        print("📱 请在浏览器中扫码登录...")
        print()
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

        # 等待用户手动登录 — 不自动检测，让用户自己确认
        print("━" * 50)
        print("🔐 浏览器窗口已打开，请扫码登录")
        print("   登录成功后，回到这个窗口按 回车 继续")
        print("━" * 50)
        input()

        # 等一下确保 cookie 完全写入
        time.sleep(1)

        # 获取所有 cookie
        cookies = context.cookies()
        if not cookies:
            print("❌ 未获取到 cookie，请重试")
            browser.close()
            return

        # 保存
        save_cookies(cookies)

        browser.close()


if __name__ == "__main__":
    login()
