"""
爬取模块 — 基于实际 DOM 结构的学习通课件获取

课件路径：
  课程页 → 侧边栏点"章节" → iframe#frame_content-zj（章节列表）
  → 点击 div.chapter_item → 主页面出现 iframe（knowledge/cards）
  → iframe 内含课件图片
"""
import time, random, re
from pathlib import Path
from urllib.parse import urljoin

COURSE_LIST_URL = "https://mooc1.chaoxing.com/visit/interaction"
BASE_URL = "https://mooc1.chaoxing.com"


def list_courses(cookies: list[dict]) -> list[dict]:
    """获取课程列表"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        page.goto(COURSE_LIST_URL, wait_until="networkidle", timeout=20000)
        time.sleep(3)

        courses = page.evaluate("""
            () => {
                const r = [];
                const seen = new Set();
                // 方法1: li[courseid] 带 stucoursemiddle 链接
                document.querySelectorAll('li[courseid]').forEach(li => {
                    const a = li.querySelector('a[href*="stucoursemiddle"]');
                    if (a && a.href) {
                        // 用 a 标签的文本（更准确）
                        const name = (a.innerText || li.innerText.split('\\n')[0] || '').trim();
                        if (name && name.length > 1 && !seen.has(a.href)) {
                            seen.add(a.href);
                            r.push({name, url: a.href, id: li.getAttribute('courseid')||''});
                        }
                    }
                });
                // 方法2: 所有带 courseid 的链接
                document.querySelectorAll('a[href*="courseid"]').forEach(a => {
                    const text = (a.innerText || a.title || '').trim();
                    if (text.length > 2 && text.length < 60 && !seen.has(a.href)) {
                        seen.add(a.href);
                        const m = a.href.match(/courseid=(\\d+)/i);
                        r.push({name: text, url: a.href, id: m ? m[1] : ''});
                    }
                });
                return r;
            }
        """)
        browser.close()
    return courses


def list_coursewares(cookies: list[dict], course: dict) -> list[dict]:
    """获取指定课程的全部课件"""
    from playwright.sync_api import sync_playwright

    all_files = []
    seen_urls = set()
    debug_dir = Path(__file__).parent

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        # ── 1. 进入课程 ──
        course_url = course.get("url", "")
        print(f"   进入课程...")
        page.goto(course_url, wait_until="networkidle", timeout=20000)
        time.sleep(4)
        page.screenshot(path=str(debug_dir / "debug_01_course.png"))

        # ── 2. 点击"章节" ──
        _click_visible_text(page, "章节")
        time.sleep(4)

        # ── 3. 获取章节 iframe ──
        zj_frame = _wait_for_iframe(page, "frame_content-zj")
        if not zj_frame:
            print("   [ERROR] 未找到章节 iframe")
            browser.close()
            return []

        # ── 4. 提取任务点列表 ──
        tasks = zj_frame.evaluate("""
            () => {
                const r = [];
                document.querySelectorAll('div.chapter_item[onclick]').forEach(el => {
                    const onclick = el.getAttribute('onclick') || '';
                    const m = onclick.match(/toOld\\('([^']+)','([^']+)','([^']+)'/);
                    r.push({
                        text: el.innerText?.trim().substring(0,60),
                        courseId: m ? m[1] : '',
                        knowledgeId: m ? m[2] : '',
                        clazzId: m ? m[3] : '',
                    });
                });
                return r;
            }
        """)
        print(f"   找到 {len(tasks)} 个任务点")
        for i, t in enumerate(tasks):
            print(f"     [{i+1}] {t['text']}")

        # ── 5. 逐个点击任务点，通过网络拦截 + API 拦截捕获课件图片 ──
        captured_urls = set()
        api_images = {}  # {knowledgeId: [img_url, ...]}

        def on_response(response):
            url = response.url
            # 捕获 CDN 图片
            if any(kw in url for kw in ["cldisk.com", "/doc/", "/thumb/"]):
                if any(url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                    captured_urls.add(url)
            # 拦截 API 返回的图片列表
            if "ananas" in url or "knowledge" in url or "status" in url or "card" in url:
                if "json" in response.headers.get("content-type", ""):
                    try:
                        body = response.json()
                        _extract_images_from_json(body, api_images)
                    except:
                        pass

        page.on("response", on_response)

        # 获取已下载的 PDF 列表
        course_dir = Path(__file__).parent / "courses" / course["name"]
        existing_pdfs = set()
        if course_dir.exists():
            for f in course_dir.glob("*.pdf"):
                existing_pdfs.add(f.stem)

        for i, task in enumerate(tasks):
            # 跳过已下载的章节
            chapter_name = task["text"].split("\n")[0].strip()
            if chapter_name in existing_pdfs:
                print(f"   [{i+1}/{len(tasks)}] {task['text']} ⏭️ 已有PDF，跳过")
                continue

            print(f"   [{i+1}/{len(tasks)}] {task['text']}")

            # 重新回到课程页 → 点章节 → 等 iframe
            page.goto(course_url, wait_until="networkidle", timeout=15000)
            time.sleep(3)
            _click_visible_text(page, "章节")
            time.sleep(4)

            zj_frame = _wait_for_iframe(page, "frame_content-zj")
            if not zj_frame:
                print("     [WARN] 章节 iframe 丢失")
                continue

            # 点击任务点
            before_count = len(captured_urls)
            before_api = sum(len(v) for v in api_images.values())
            clicked = zj_frame.evaluate(f"""
                () => {{
                    const els = document.querySelectorAll('div.chapter_item[onclick]');
                    if (els.length > {i}) {{
                        els[{i}].click();
                        return true;
                    }}
                    return false;
                }}
            """)
            if not clicked:
                print("     [WARN] 点击失败")
                continue
            time.sleep(2)

            # 在 knowledge/cards iframe 中逐页点击"下一页"
            kc_frame = _wait_for_knowledge_iframe(page, timeout=5)
            if kc_frame:
                _click_through_pages(kc_frame)
            time.sleep(3)

            # 汇总图片
            new_urls = captured_urls - seen_urls
            new_api = sum(len(v) for v in api_images.values()) - before_api

            if new_urls:
                for img_url in sorted(new_urls):
                    seen_urls.add(img_url)
                    all_files.append({
                        "name": f"{task['text']}_{len(all_files)+1:02d}",
                        "url": img_url,
                        "type": "image"
                    })
                print(f"     -> {len(new_urls)} 张图片")
            else:
                print(f"     [DEBUG] 未捕获（网络:{before_count}→{len(captured_urls)}，API新增:{new_api}）")

            time.sleep(random.uniform(1, 2))

        # ── 8. 资料 ──
        print("   --- 扫描'资料' ---")
        page.goto(course_url, wait_until="networkidle", timeout=15000)
        time.sleep(3)
        _click_visible_text(page, "资料")
        time.sleep(3)
        page.screenshot(path=str(debug_dir / "debug_ziliao.png"))

        zl_files = _extract_images_from_page(page, "资料", seen_urls)
        all_files.extend(zl_files)
        print(f"   资料区找到 {len(zl_files)} 个文件")

        browser.close()

    # 去重
    unique = []
    seen = set()
    for f in all_files:
        if f["url"] not in seen:
            seen.add(f["url"])
            unique.append(f)

    print(f"   共找到 {len(unique)} 个课件文件")
    return unique


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _click_visible_text(page, text: str):
    """点击页面上可见的、文本精确匹配的元素"""
    r = page.evaluate(f"""
        () => {{
            const all = document.querySelectorAll('*');
            // 收集所有匹配元素
            const matches = [];
            for (const el of all) {{
                if (el.innerText?.trim() === '{text}') {{
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.y >= 0) {{
                        matches.push({{x: rect.x+rect.width/2, y: rect.y+rect.height/2, tag: el.tagName, y: rect.y}});
                    }}
                }}
            }}
            // 选 y 坐标最小的可见元素（最高的那个，通常是侧边栏里的）
            matches.sort((a,b) => a.y - b.y);
            return matches.length > 0 ? matches[0] : null;
        }}
    """)
    if r:
        print(f"   [OK] 点击'{text}' ({r['tag']} at {r['x']:.0f},{r['y']:.0f})")
        page.mouse.click(r["x"], r["y"])
    else:
        print(f"   [WARN] 未找到可见的'{text}'")


def _wait_for_iframe(page, id_contains: str, timeout: int = 10):
    """等待特定 iframe 出现"""
    for _ in range(timeout):
        iframes = page.query_selector_all("iframe")
        for f in iframes:
            fid = (f.get_attribute("id") or "") + (f.get_attribute("name") or "")
            if id_contains in fid:
                try:
                    fr = f.content_frame()
                    if fr:
                        return fr
                except:
                    pass
        time.sleep(1)
    return None


def _wait_for_knowledge_iframe(page, timeout: int = 10):
    """等待 knowledge/cards iframe"""
    for _ in range(timeout):
        iframes = page.query_selector_all("iframe")
        for f in iframes:
            src = f.get_attribute("src") or ""
            if "knowledge/cards" in src or "knowledge/card" in src:
                try:
                    fr = f.content_frame()
                    if fr:
                        return fr
                except:
                    pass
        time.sleep(1)
    return None


def _scroll_through(target):
    """在页面/iframe 中逐步滚动，触发懒加载图片和自动激活"""
    try:
        # 获取总高度
        height = target.evaluate("() => document.body.scrollHeight || 5000")
        # 分 10 步滚动
        for step in range(10):
            scroll_y = int(height * step / 10)
            target.evaluate(f"window.scrollTo(0, {scroll_y})")
            time.sleep(0.5)
        # 滚到底
        target.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        # 滚回顶部
        target.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)
    except:
        pass


def _wait_for_knowledge_iframe(page, timeout: int = 10):
    """等待 knowledge/cards iframe 出现"""
    for _ in range(timeout):
        for f in page.query_selector_all("iframe"):
            src = f.get_attribute("src") or ""
            if "knowledge/cards" in src or "knowledge/card" in src:
                try:
                    fr = f.content_frame()
                    if fr:
                        return fr
                except:
                    pass
        time.sleep(1)
    return None


def _click_through_pages(frame, max_pages: int = 30):
    """在课件 iframe 中逐页点击，触发所有图片加载"""
    for page_num in range(max_pages):
        # 找"下一页"按钮
        found = frame.evaluate(f"""
            () => {{
                const selectors = [
                    '.next-page', '.next', '.btn-next', '#next',
                    '[class*="next"]', '[class*="arrow-right"]',
                    '.turn_next', '.page-next', '.nav-next',
                ];
                for (const sel of selectors) {{
                    const el = document.querySelector(sel);
                    if (el && el.offsetWidth > 0) {{
                        el.click();
                        return true;
                    }}
                }}
                // 文本匹配
                const all = document.querySelectorAll('button, a, div, span, i');
                for (const el of all) {{
                    const t = (el.innerText || el.textContent || '').trim();
                    if (['下一页', '❯', '>', '›', 'next', '→'].includes(t)) {{
                        if (el.offsetWidth > 0) {{ el.click(); return true; }}
                    }}
                }}
                return false;
            }}
        """)
        if not found:
            break
        time.sleep(0.8)
    # 滚动
    _scroll_through(frame)


def _extract_images_from_json(obj, api_images: dict):
    """递归从 API 响应 JSON 中提取图片 URL"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                if any(domain in v for domain in ["cldisk.com", "/doc/", "/thumb/", "/upload/"]):
                    if any(v.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                        kid = obj.get("knowledgeid", obj.get("knowledgeId", ""))
                        if kid not in api_images:
                            api_images[kid] = []
                        if v not in api_images[kid]:
                            api_images[kid].append(v)
            else:
                _extract_images_from_json(v, api_images)
    elif isinstance(obj, list):
        for item in obj:
            _extract_images_from_json(item, api_images)


def _click_activation(target_page) -> bool:
    """在页面/iframe中找并点击激活按钮，返回是否点击成功"""
    return target_page.evaluate("""
        () => {
            const texts = ['开始学习', '开始', '进入学习', '开始任务', '开始上课',
                           '立即开始', 'start', 'begin', '进入', '确认', '我知道了', '知道了'];
            const all = document.querySelectorAll(
                'button, a, div, span, input[type="button"], input[type="submit"], '
                + '.btn, [class*="btn"], [class*="start"], [class*="begin"]'
            );
            for (const el of all) {
                const t = (el.innerText || el.textContent || el.value || '').trim();
                if (t.length < 1 || t.length > 20) continue;
                for (const target of texts) {
                    if (t === target || t.startsWith(target)) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && r.x >= 0 && r.y >= 0) {
                            el.click();
                            el.dispatchEvent(new MouseEvent('click', {bubbles:true}));
                            return true;
                        }
                    }
                }
            }
            return false;
        }
    """)


def _extract_images_from_page(page, label: str, seen_urls: set) -> list[dict]:
    """从页面提取课件图片"""
    results = []
    imgs = page.evaluate("""
        () => {
            const r = [];
            document.querySelectorAll('img[src]').forEach(img => {
                const s = img.src || '';
                const w = img.naturalWidth || img.width || 0;
                if (s.startsWith('http') && w > 200 && !s.includes('kaptcha') && !s.includes('verify')
                    && (s.includes('cldisk') || s.includes('/doc/') || s.includes('/thumb/') || s.includes('/upload/') || w > 400))
                    r.push(s);
            });
            return r;
        }
    """)
    for img_url in imgs:
        if img_url not in seen_urls:
            seen_urls.add(img_url)
            idx = len(results) + 1
            results.append({"name": f"{label}_{idx:02d}", "url": img_url, "type": "image"})
    return results
