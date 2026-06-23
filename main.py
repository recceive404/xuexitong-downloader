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
    engine = RAGEngine()
    engine.build_or_update()
    engine.persist()
    print("✅ RAG 知识库构建完成")


def cmd_ask(question: str | None = None):
    """问答模式"""
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
