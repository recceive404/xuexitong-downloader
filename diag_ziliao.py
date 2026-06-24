"""诊断资料 iframe 结构 — 指定课程"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

COOKIE_FILE = Path(__file__).parent / "cookies.json"
debug_dir = Path(__file__).parent


def get_course_url(cookies, target_name):
    """先通过独立 Playwright 实例获取课程 URL"""
    from crawler import list_courses
    courses = list_courses(cookies)
    matched = [c for c in courses if target_name in c.get("name", "")]
    if not matched:
        print(f"未找到: {target_name}")
        print(f"可用: {[c['name'][:20] for c in courses[:10]]}")
        return None
    return matched[0]


def main():
    cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    target_name = "园艺植物栽培学"

    # 步骤1：获取课程 URL（独立 Playwright 实例）
    course = get_course_url(cookies, target_name)
    if not course:
        return
    print(f"找到课程: {course['name']}")
    print(f"URL: {course['url'][:120]}")

    # 步骤2：用新 Playwright 实例进入课程，点击资料，分析 DOM
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        # 进入课程
        page.goto(course["url"], wait_until="networkidle", timeout=20000)
        time.sleep(4)

        # 点击"资料"
        print("\n点击资料...")
        page.evaluate("""
            () => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.innerText?.trim() === '资料') {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            el.click();
                            return;
                        }
                    }
                }
            }
        """)
        time.sleep(5)

        # 列出所有 iframe
        print("\n=== 所有 iframe ===")
        iframes = page.query_selector_all("iframe")
        for f in iframes:
            src = f.get_attribute("src") or ""
            fid = f.get_attribute("id") or ""
            fname = f.get_attribute("name") or ""
            print(f"  id={fid} name={fname} src={src[:200]}")

        if not iframes:
            print("  （无 iframe，尝试在主页面找内容）")
            page.screenshot(path=str(debug_dir / "debug_ziliao_mainpage.png"))
            body = page.evaluate("() => document.body?.innerText?.substring(0,2000) || '(空)'")
            print(f"\n--- 主页面 Body 文本 ---\n{body}")

        # 找资料相关 iframe
        for f in iframes:
            src = f.get_attribute("src") or ""
            fid = (f.get_attribute("id") or "") + (f.get_attribute("name") or "")
            if any(kw in (src + fid).lower() for kw in ["coursedata", "datalist", "work", "document", "resource", "file", "attachment"]):
                fr = f.content_frame()
                if not fr:
                    print("无法获取 iframe 内容")
                    continue

                print(f"\n=== 资料 iframe 内容 (src={src[:120]}) ===")
                print(f"iframe URL: {fr.url[:200]}")

                # 截图
                page.screenshot(path=str(debug_dir / "debug_ziliao_full.png"))
                print("截图: debug_ziliao_full.png")

                # 获取 body 文本
                body = fr.evaluate("() => document.body?.innerText?.substring(0,3000) || '(空)'")
                print(f"\n--- Body 文本 ---\n{body}")

                # 获取所有 a 标签
                links = fr.evaluate("""
                    () => {
                        const r = [];
                        document.querySelectorAll('a[href]').forEach((a, i) => {
                            r.push({
                                i, href: a.href?.substring(0,250),
                                text: (a.innerText || '').trim().substring(0,100),
                                class: a.className?.substring(0,60)
                            });
                        });
                        return r;
                    }
                """)
                print(f"\n--- 所有 <a> 链接 ({len(links)}) ---")
                for l in links[:50]:
                    print(f"  [{l['i']}] text='{l['text']}' href={l['href']}")

                # 获取 onclick 元素
                onclicks = fr.evaluate("""
                    () => {
                        const r = [];
                        document.querySelectorAll('[onclick]').forEach((el, i) => {
                            r.push({
                                i, tag: el.tagName,
                                onclick: (el.getAttribute('onclick')||'').substring(0,300),
                                text: (el.innerText||'').trim().substring(0,100)
                            });
                        });
                        return r;
                    }
                """)
                print(f"\n--- 所有 onclick 元素 ({len(onclicks)}) ---")
                for o in onclicks[:30]:
                    print(f"  [{o['i']}] <{o['tag']}> text='{o['text']}' onclick={o['onclick']}")

                # 找所有可见的元素 class 名称
                classes = fr.evaluate("""
                    () => {
                        const s = new Set();
                        document.querySelectorAll('[class]').forEach(el => {
                            const c = el.className;
                            if (typeof c === 'string') {
                                c.split(' ').forEach(cls => { if (cls.length > 1 && cls.length < 40) s.add(cls); });
                            }
                        });
                        return [...s].sort();
                    }
                """)
                print(f"\n--- CSS class 名 ---")
                print("  " + ", ".join(classes[:80]))

                break
        else:
            print("\n未找到资料 iframe")

        browser.close()


if __name__ == "__main__":
    main()
