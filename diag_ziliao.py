"""诊断：返回根目录后再次操作，以及教师课件文件夹"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

COOKIE_FILE = Path(__file__).parent / "cookies.json"
debug_dir = Path(__file__).parent


def get_course_url(cookies, target_name):
    from crawler import list_courses
    courses = list_courses(cookies)
    matched = [c for c in courses if target_name in c.get("name", "")]
    return matched[0] if matched else None


def main():
    cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    course = get_course_url(cookies, "园艺植物栽培学")
    if not course:
        print("未找到课程")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        page.goto(course["url"], wait_until="networkidle", timeout=20000)
        time.sleep(4)

        # 点击资料
        page.evaluate("""
            () => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.innerText?.trim() === '资料') { el.click(); return; }
                }
            }
        """)
        time.sleep(5)

        for f in page.query_selector_all("iframe"):
            if "frame_content-zl" in (f.get_attribute("id") or ""):
                zl = f.content_frame()
                print("=== 根目录所有 DT 元素的 onclick ===")
                all_onclicks = zl.evaluate("""
                    () => {
                        const r = [];
                        document.querySelectorAll('dt, li, a').forEach(el => {
                            const oc = el.getAttribute('onclick') || '';
                            const text = (el.innerText || '').trim().substring(0,80);
                            if (oc || text) {
                                r.push({tag: el.tagName, text: text, onclick: oc.substring(0,200)});
                            }
                        });
                        return r;
                    }
                """)
                for o in all_onclicks:
                    print(f"  <{o['tag']}> text='{o['text']}' onclick={o['onclick']}")

                print("\n=== 手动点击'学习视频' ===")
                # 直接用 evaluate 调用 toOpen
                result = zl.evaluate("""
                    () => {
                        const els = document.querySelectorAll('[onclick*="toOpen"][onclick*="afolder"]');
                        const targets = [];
                        for (const el of els) {
                            const oc = el.getAttribute('onclick') || '';
                            const m = oc.match(/toOpen\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*(\d+)/);
                            if (m) {
                                targets.push({name: decodeURIComponent(m[1]), dataId: m[3], tag: el.tagName});
                            }
                        }
                        return targets;
                    }
                """)
                print(f"  afolder 元素: {result}")

                # 点"学习视频" — 先找到它的 dataId
                study_video_di = None
                for t in result:
                    if "视频" in t["name"]:
                        study_video_di = t["dataId"]
                        print(f"  找到学习视频 dataId={study_video_di}")
                        break

                if study_video_di:
                    # 尝试通过点击 DT 元素
                    clicked = zl.evaluate(f"""
                        () => {{
                            const els = document.querySelectorAll('dt[onclick*="{study_video_di}"]');
                            if (els.length) {{ els[0].click(); return 'dt'; }}
                            // 试 li
                            const lis = document.querySelectorAll('li[onclick*="{study_video_di}"]');
                            if (lis.length) {{ lis[0].click(); return 'li'; }}
                            return null;
                        }}
                    """)
                    print(f"  点击结果: {clicked}")
                    time.sleep(4)

                    body = zl.evaluate("() => document.body?.innerText?.substring(0,800) || '(空)'")
                    print(f"\n  内容:\n{body}")

                    # 返回
                    zl.evaluate("""
                        () => {
                            const all = document.querySelectorAll('a, span, li');
                            for (const el of all) {
                                if ((el.innerText || '').trim() === '全部文件') { el.click(); return; }
                            }
                        }
                    """)
                    time.sleep(3)

                print("\n=== 检查'教师课件' ===")
                # 教师课件可能没有 afolder onclick，直接看 DT 文本
                teacher_dts = zl.evaluate("""
                    () => {
                        const r = [];
                        document.querySelectorAll('dt').forEach(dt => {
                            const text = (dt.innerText || '').trim();
                            const oc = dt.getAttribute('onclick') || '';
                            if (text && text.includes('教师')) {
                                r.push({text, onclick: oc.substring(0,200), parentLiOnclick: ''});
                                // 也看父 LI 的 onclick
                                const li = dt.closest('li');
                                if (li) r[r.length-1].parentLiOnclick = (li.getAttribute('onclick')||'').substring(0,200);
                            }
                        });
                        return r;
                    }
                """)
                print(f"  教师课件相关 DT: {teacher_dts}")

                break

        browser.close()

if __name__ == "__main__":
    main()
