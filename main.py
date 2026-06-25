"""
学习通课件下载 + 本地 RAG 问答
用法：
  python main.py login               扫码登录，保存 cookie
  python main.py courses             列出所有课程
  python main.py download "课程名"   下载指定课程的全部课件
  python main.py build-rag           将已下载课件消化到 RAG 知识库
  python main.py ask                 进入交互问答模式
  python main.py ask "一句话提问"     单次提问
"""

import argparse
import sys
import os
from pathlib import Path

# ── 加载 .env 配置 ──
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        os.environ["PYTHONIOENCODING"] = "utf-8"

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent))

from auth import login, load_cookies
from crawler import list_courses, list_coursewares
from downloader import download_coursewares
from rag_engine import RAGEngine


def _check_rag_ready() -> bool:
    """检查 RAG 功能是否已配置（有 API key）"""
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if api_key and api_key not in ("你的DeepSeek_API_Key", ""):
        return True
    return False


def _rag_config_hint():
    """RAG 未配置时的提示信息"""
    print("⚠️  未配置 DeepSeek API Key，RAG 问答功能不可用。")
    print()
    print("   如需使用 AI 问答，请：")
    print("   1. 注册 DeepSeek：https://platform.deepseek.com")
    print("   2. 获取 API Key")
    print("   3. 复制 .env.example 为 .env，填入你的 API Key")
    print("      cp .env.example .env")
    print("      notepad .env")
    print()
    print("   如果只需要下载课件，可以忽略此提示。")


def cmd_wizard():
    """傻瓜式向导：登录 → 主菜单（下载 / RAG / 问答 / 设置）"""
    print()
    print("╔══════════════════════════════════════════╗")
    print("║     🎓 学习通课件下载器                 ║")
    print("╚══════════════════════════════════════════╝")
    print()

    cookie_file = Path(__file__).parent / "cookies.json"
    cookies = load_cookies()

    if cookies:
        print("✅ 已有登录记录")
    else:
        print("🔐 浏览器将弹出，请用学习通 APP 扫码...")
        login()
        cookies = load_cookies()
        if not cookies:
            print("❌ 登录失败，请重试")
            return
        print("✅ 登录成功！")

    # ── 主菜单 ──
    while True:
        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  [1] 下载课件")
        print("  [2] 消化课件到知识库（AI 问答前必做）")
        print("  [3] AI 问答")
        print("  [4] 设置 API Key")
        print("  [5] 重新登录")
        print("  [0] 退出")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        choice = input("  选择: ").strip()

        if choice == "1":
            _wizard_download(cookie_file, cookies)
        elif choice == "2":
            _wizard_build_rag()
        elif choice == "3":
            _wizard_ask()
        elif choice == "4":
            _wizard_set_key()
        elif choice == "5":
            if cookie_file.exists():
                cookie_file.unlink()
            login()
            cookies = load_cookies()
            if not cookies:
                print("❌ 登录失败")
                return
            print("✅ 重新登录成功！")
        elif choice == "0":
            print("👋 再见！")
            break
        else:
            print("输入不对，重新来")


def _wizard_download(cookie_file, cookies):
    """下载课件子流程"""
    print()
    print("━━━ 下载课件 ━━━")
    courses = list_courses(cookies)
    if not courses:
        print("⚠️ 未找到课程")
        relogin = input("Cookie 可能过期，重新登录？(y/n): ").strip().lower()
        if relogin != "n":
            if cookie_file.exists():
                cookie_file.unlink()
            login()
            cookies = load_cookies()
            if cookies:
                courses = list_courses(cookies)
        if not courses:
            print("⚠️ 仍未找到课程")
            return

    print(f"📚 你的课程（共 {len(courses)} 门）：")
    for i, c in enumerate(courses, 1):
        print(f"  [{i}] {c['name']}")
    print("  [0] 返回")

    choice = input("选课 (序号/a=全部/0=返回): ").strip()
    if choice == "0" or choice == "":
        return
    if choice.lower() == "a":
        targets = courses
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(courses):
                targets = [courses[idx]]
            else:
                print("序号不对")
                return
        except ValueError:
            print("输入不对")
            return

    for target in targets:
        print(f"\n📥 下载「{target['name']}」...")
        coursewares = list_coursewares(cookies, target)
        if not coursewares:
            print("⚠️ 该课程暂无课件")
            continue
        print(f"📄 共 {len(coursewares)} 个课件")
        download_coursewares(cookies, target["name"], coursewares)


def _wizard_build_rag():
    """构建 RAG 知识库"""
    print()
    if not _check_rag_ready():
        print("⚠️ 未配置 API Key，先选 [4] 设置 API Key")
        return
    print("📦 消化课件中...")
    engine = RAGEngine()
    engine.build_or_update()
    engine.persist()


def _wizard_set_key():
    """设置 API Key"""
    print()
    print("━━━ 设置 API Key ━━━")
    print("获取方式：platform.deepseek.com → 注册 → API Keys")
    print()
    apikey = input("粘贴 API Key（sk-开头）: ").strip()
    if not apikey:
        print("已取消")
        return
    env_path = Path(__file__).parent / ".env"
    env_path.write_text(
        f"ANTHROPIC_AUTH_TOKEN={apikey}\n"
        f"ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic\n"
        f"ANTHROPIC_MODEL=deepseek-v4-pro[1m]\n",
        encoding="utf-8"
    )
    os.environ["ANTHROPIC_AUTH_TOKEN"] = apikey
    print("✅ API Key 已保存")


def _wizard_ask():
    """AI 问答子流程"""
    print()
    if not _check_rag_ready():
        print("⚠️ 未配置 API Key，先选 [4] 设置 API Key")
        return
    engine = RAGEngine()
    engine.load()
    if not engine.documents:
        print("⚠️ 知识库为空，先选 [2] 消化课件")
        return

    print("💬 AI 问答（输入 /exit 退出，/courses 查看课程）")
    print()
    while True:
        try:
            q = input("❓ 提问：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 返回主菜单")
            break
        if not q:
            continue
        if q.lower() == "/exit":
            break
        if q.lower() == "/courses":
            for c in engine.list_courses():
                print(f"   - {c}")
            continue
        print("⏳ 检索中...")
        answer = engine.ask(q)
        print(f"\n📝 {answer}\n")


def cmd_login():
    """扫码登录，保存 cookie"""
    print("🔐 打开浏览器，请扫码登录学习通...")
    login()
    print("✅ 登录成功，cookie 已保存")


def cmd_courses():
    """列出所有课程"""
    cookies = load_cookies()
    if not cookies:
        print("❌ 尚未登录，请先运行：python main.py login")
        return
    courses = list_courses(cookies)
    if not courses:
        print("⚠️ 未找到课程（可能需要调整选择器），请检查浏览器中的页面结构")
        return
    print(f"\n📚 共 {len(courses)} 门课程：\n")
    for i, c in enumerate(courses, 1):
        print(f"  {i}. {c['name']}")


def cmd_download(course_name: str):
    """下载指定课程的全部课件"""
    cookies = load_cookies()
    if not cookies:
        print("❌ 尚未登录，请先运行：python main.py login")
        return

    # 先获取课程列表，匹配目标课程
    courses = list_courses(cookies)
    if not courses:
        print("⚠️ 未找到任何课程")
        return

    # 模糊匹配课程名
    matched = [c for c in courses if course_name.lower() in c['name'].lower()]
    if not matched:
        print(f"❌ 未找到包含 '{course_name}' 的课程")
        print(f"   可用课程：{', '.join(c['name'] for c in courses)}")
        return
    if len(matched) > 1:
        print(f"⚠️ 找到 {len(matched)} 门匹配课程，请更精确指定：")
        for c in matched:
            print(f"   - {c['name']}")

    target = matched[0]
    print(f"📖 课程：{target['name']}")

    # 获取课件列表
    coursewares = list_coursewares(cookies, target)
    if not coursewares:
        print("⚠️ 该课程暂无课件或课件列表获取失败")
        return

    print(f"📄 共 {len(coursewares)} 个课件，开始下载...\n")
    download_coursewares(cookies, target['name'], coursewares)


def cmd_build_rag():
    """构建/更新 RAG 知识库"""
    if not _check_rag_ready():
        _rag_config_hint()
        return
    engine = RAGEngine()
    engine.build_or_update()
    engine.persist()
    print("✅ RAG 知识库构建完成")


def cmd_ask(question: str | None = None):
    """问答模式"""
    if not _check_rag_ready():
        _rag_config_hint()
        return
    engine = RAGEngine()
    engine.load()

    if question:
        # 单次提问
        answer = engine.ask(question)
        if answer.startswith("[{'"):
            import ast
            try:
                items = ast.literal_eval(answer)
                for item in items:
                    if isinstance(item, dict) and item.get("type") == "text":
                        answer = item["text"]
                        break
            except:
                pass
        print(f"\n📝 {answer}")
    else:
        # 交互模式
        print("💬 交互问答模式（输入 /exit 退出，输入 /courses 查看已消化课程）")
        print()
        while True:
            try:
                q = input("❓ 你：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 再见")
                break

            if not q:
                continue
            if q.lower() == "/exit":
                print("👋 再见")
                break
            if q.lower() == "/courses":
                courses = engine.list_courses()
                if courses:
                    print(f"📚 已消化的课程 ({len(courses)} 门)：")
                    for c in courses:
                        print(f"   - {c}")
                else:
                    print("⚠️ 暂未消化任何课件，请先运行 build-rag")
                continue

            print("⏳ 检索中...")
            answer = engine.ask(q)
            # 如果返回的是 DeepSeek 原始列表格式，提取纯文本
            if answer.startswith("[{'"):
                import ast
                try:
                    items = ast.literal_eval(answer)
                    for item in items:
                        if isinstance(item, dict) and item.get("type") == "text":
                            answer = item["text"]
                            break
                except:
                    pass
            print(f"\n📝 {answer}\n")


def main():
    parser = argparse.ArgumentParser(
        description="学习通课件下载 + 本地 RAG 问答",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py login
  python main.py courses
  python main.py download "高等数学"
  python main.py build-rag
  python main.py ask
  python main.py ask "总结一下第三章的主要内容"
        """
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    sub.add_parser("login", help="扫码登录学习通，保存 cookie")
    sub.add_parser("courses", help="列出所有课程")
    sub_dl = sub.add_parser("download", help="下载指定课程的课件")
    sub_dl.add_argument("course_name", help="课程名（支持模糊匹配）")
    sub.add_parser("build-rag", help="将已下载课件消化到 RAG 知识库")
    sub_ask = sub.add_parser("ask", help="基于课件内容提问")
    sub_ask.add_argument("question", nargs="?", default=None, help="问题（不提供则进入交互模式）")
    sub.add_parser("wizard", help="傻瓜式向导：登录→下载→AI问答 一条龙")

    args = parser.parse_args()

    if args.command == "login":
        cmd_login()
    elif args.command == "courses":
        cmd_courses()
    elif args.command == "download":
        cmd_download(args.course_name)
    elif args.command == "build-rag":
        cmd_build_rag()
    elif args.command == "ask":
        cmd_ask(args.question)
    elif args.command == "wizard":
        cmd_wizard()
    else:
        # 默认启动向导
        cmd_wizard()


if __name__ == "__main__":
    main()
