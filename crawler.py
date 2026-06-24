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
        time.sleep(4)

        # 尝试找到资料 iframe
        # 学习通资料 iframe 特征：id="frame_content-zl"，src 含 "coursedata/stu-datalist"
        zl_frame = None
        for f in page.query_selector_all("iframe"):
            src = f.get_attribute("src") or ""
            fid = f.get_attribute("id") or ""
            fname = f.get_attribute("name") or ""
            combined = (src + fid + fname).lower()
            # 优先精确匹配已知 ID，其次匹配关键词
            if "frame_content-zl" in combined or \
               any(kw in combined for kw in ["coursedata", "datalist", "work", "document", "attachment", "resource"]):
                try:
                    zl_frame = f.content_frame()
                    if zl_frame:
                        print(f"   [OK] 找到资料 iframe: id={fid} name={fname} src={src[:80]}...")
                        break
                except:
                    pass
        # 如果没匹配到特定 iframe，尝试取第一个非章节的 iframe
        if not zl_frame:
            for f in page.query_selector_all("iframe"):
                src = f.get_attribute("src") or ""
                fid = (f.get_attribute("id") or "") + (f.get_attribute("name") or "")
                if "frame_content-zj" not in fid and "knowledge/card" not in src:
                    try:
                        zl_frame = f.content_frame()
                        if zl_frame:
                            print(f"   [OK] 使用候选 iframe: src={src[:80]}...")
                            break
                    except:
                        pass

        page.screenshot(path=str(debug_dir / "debug_ziliao.png"))

        if zl_frame:
            # 1. 提取根目录文件
            zl_files = _extract_files_from_ziliao(zl_frame, seen_urls)
            print(f"   根目录找到 {len(zl_files)} 个文件")

            # 2. 获取文件夹列表（去重，通过 toOpen(..., 'afolder', dataId, ...)）
            folder_ids = zl_frame.evaluate(r"""
                () => {
                    const seen = new Set();
                    const r = [];
                    document.querySelectorAll('[onclick*="toOpen"][onclick*="afolder"]').forEach(el => {
                        const oc = el.getAttribute('onclick') || '';
                        const m = oc.match(/toOpen\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*(\d+)/);
                        if (m) {
                            const name = decodeURIComponent(m[1]);
                            const dataId = m[3];
                            if (!seen.has(dataId)) {
                                seen.add(dataId);
                                r.push({name: name, dataId: dataId});
                            }
                        }
                    });
                    return r;
                }
            """)
            print(f"   找到 {len(folder_ids)} 个文件夹: {[f['name'] for f in folder_ids]}")

            # 3. 依次进入每个文件夹，提取文件
            for folder in folder_ids:
                fname = folder["name"]
                fid = folder["dataId"]
                print(f"    进入文件夹: {fname}...")

                # 为确保 DOM 干净，重新点击"资料"回到根目录再操作
                # （breadcrumb 返回后 DOM 可能不完整）
                if zl_files:  # 非第一个文件夹时，重新加载资料页
                    page.goto(course_url, wait_until="networkidle", timeout=15000)
                    time.sleep(3)
                    _click_visible_text(page, "资料")
                    time.sleep(4)
                    # 重新获取 iframe
                    zl_frame = None
                    for f in page.query_selector_all("iframe"):
                        if "frame_content-zl" in ((f.get_attribute("id") or "") + (f.get_attribute("name") or "")):
                            zl_frame = f.content_frame()
                            if zl_frame:
                                break
                    if not zl_frame:
                        print("      [WARN] 无法重新获取 iframe，跳过")
                        continue

                # 点击文件夹 — 多策略尝试
                clicked = False
                clicked = zl_frame.evaluate(f"""
                    () => {{
                        const els = document.querySelectorAll('dt[onclick*="{fid}"]');
                        if (els.length) {{ els[0].click(); return true; }}
                        const lis = document.querySelectorAll('li[onclick*="{fid}"]');
                        if (lis.length) {{ lis[0].click(); return true; }}
                        return false;
                    }}
                """)
                if not clicked:
                    # 直接 eval onclick 中的 toOpen 调用
                    clicked = zl_frame.evaluate(f"""
                        () => {{
                            const els = document.querySelectorAll('[onclick*="toOpen"][onclick*="afolder"]');
                            for (const el of els) {{
                                const oc = el.getAttribute('onclick') || '';
                                if (oc.includes('{fid}')) {{
                                    eval(oc); return true;
                                }}
                            }}
                            return false;
                        }}
                    """)
                if not clicked:
                    print(f"      [WARN] 所有点击策略均失败，跳过")
                    continue
                time.sleep(4)

                # 提取文件夹内的文件
                inner_files = _extract_files_from_ziliao(zl_frame, seen_urls)
                for f in inner_files:
                    f["name"] = f"{fname}/{f['name']}"
                zl_files.extend(inner_files)
                print(f"      {len(inner_files)} 个文件")

            all_files.extend(zl_files)
            print(f"   资料区共找到 {len(zl_files)} 个文件（含子文件夹）")
            for zf in zl_files:
                print(f"     -> {zf['name']} ({zf.get('type','?')})")
        else:
            # 兜底：直接从主页面提取
            print("   [WARN] 未找到资料 iframe，从主页面提取")
            zl_files = _extract_files_from_ziliao(page, seen_urls)
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


def _extract_files_from_ziliao(target, seen_urls: set) -> list[dict]:
    """从资料 iframe/页面中提取可下载文件链接

    学习通资料区 DOM 结构（iframe#frame_content-zl）：
      - 文件行：<DT>文件名.doc</DT> + <A href="/coursedata/downloadData?dataId=...">下载</A>
      - 文件夹行：<DT>文件夹名</DT> + onclick=toOpen(...)（不含下载链接）
      - onclick 中也包含 toOpen('文件名','doc',dataId,...) 含文件类型信息
    """
    results = []
    file_ext_map = {
        ".pdf": "pdf", ".doc": "doc", ".docx": "doc",
        ".ppt": "ppt", ".pptx": "ppt", ".xls": "xls", ".xlsx": "xls",
        ".mp4": "video", ".mp3": "audio", ".flv": "video",
        ".zip": "archive", ".rar": "archive",
        ".txt": "text", ".jpg": "image", ".png": "image",
    }

    # ── 方法1：匹配 downloadData 链接 + 文件名 ──
    # 找出所有 /coursedata/downloadData 链接，从同行/附近 DT 提取文件名
    raw_entries = target.evaluate(r"""
        () => {
            const r = [];
            // 找所有 downloadData 链接
            document.querySelectorAll('a[href*="downloadData"]').forEach(a => {
                const href = a.href || '';
                if (!href.includes('downloadData')) return;
                // 在同级或父级找 DT 元素中的文件名
                let row = a.closest('li, tr, .dataBody, dl');
                if (!row) row = a.parentElement;
                let name = '';
                if (row) {
                    const dt = row.querySelector('dt, .dataBody_file, [class*="file"]');
                    if (dt) name = (dt.innerText || '').trim();
                }
                // 如果没找到，尝试从前面兄弟元素找
                if (!name && row) {
                    const prev = row.previousElementSibling;
                    if (prev) name = (prev.innerText || '').trim().substring(0, 100);
                }
                r.push({url: href, name: name});
            });
            return r;
        }
    """)

    for entry in raw_entries:
        url = entry.get("url", "")
        name = entry.get("name", "")
        if not url or url in seen_urls or "javascript:" in url:
            continue
        seen_urls.add(url)

        # 从文件名推断类型
        ftype = "html"
        name_lower = name.lower()
        for ext, t in file_ext_map.items():
            if ext in name_lower or ext in url.lower():
                ftype = t
                break
        # downloadData 通常是 office 文件
        if ftype == "html":
            ftype = "doc"

        if not name:
            name = f"资料文件_{len(results)+1:02d}"
        results.append({"name": name, "url": url, "type": ftype})

    # ── 方法2：从 toOpen() 的 onclick 提取文件信息 ──
    # toOpen('文件名.doc', 'doc', dataId, ...) — 参数2是文件类型
    onclick_entries = target.evaluate(r"""
        () => {
            const r = [];
            document.querySelectorAll('[onclick*="toOpen"]').forEach(el => {
                const oc = el.getAttribute('onclick') || '';
                const m = oc.match(/toOpen\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*(\d+)/);
                if (m) {
                    const fname = decodeURIComponent(m[1]);
                    const ftype = m[2];  // 'doc', 'docx', 'pdf', 'afolder' etc
                    const dataId = m[3];
                    if (ftype && ftype !== 'afolder') {
                        r.push({name: fname, type: ftype, dataId: dataId});
                    }
                }
            });
            return r;
        }
    """)

    # 用 onclick 中的信息补充/修正方法1的结果
    for entry in onclick_entries:
        ftype = entry.get("type", "")
        name = entry.get("name", "")
        data_id = entry.get("dataId", "")

        # 映射类型
        mapped_type = ftype if ftype in ("pdf", "ppt", "doc", "docx") else "doc"
        if ftype in ("mp4", "flv"):
            mapped_type = "video"
        elif ftype in ("mp3",):
            mapped_type = "audio"

        # 检查是否已在结果中
        already = False
        for r in results:
            if data_id and data_id in r.get("url", ""):
                # 用 onclick 中的更准确信息修正
                if not r["name"] or len(name) > len(r["name"]):
                    r["name"] = name
                r["type"] = mapped_type
                already = True
                break
        if already:
            continue

        # 构造下载 URL
        # downloadData 链接格式：/coursedata/downloadData?dataId=X&classId=...&courseId=...&ut=s
        # 如果方法1没找到，说明这个文件可能藏在文件夹里，先跳过
        # （进入文件夹需要再点击，这里先不处理）

    # ── 方法3：兜底 — 抓所有带 /upload/ 或 /doc/ 路径的链接 ──
    extra_links = target.evaluate(r"""
        () => {
            const r = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href || '';
                if (href.startsWith('http') && !href.includes('javascript:')) {
                    const lower = href.toLowerCase();
                    if (lower.includes('/upload/') || lower.includes('/doc/') || lower.includes('download')) {
                        const text = (a.innerText || '').trim().substring(0, 80);
                        if (!r.some(x => x.url === href)) {
                            r.push({url: href, name: text});
                        }
                    }
                }
            });
            return r;
        }
    """)
    for entry in extra_links:
        url = entry.get("url", "")
        name = entry.get("name", "")
        if not url or url in seen_urls or "javascript:" in url:
            continue
        seen_urls.add(url)
        ftype = "html"
        for ext, t in file_ext_map.items():
            if ext in url.lower() or ext in name.lower():
                ftype = t
                break
        if not name:
            name = f"资料文件_{len(results)+1:02d}"
        results.append({"name": name, "url": url, "type": ftype})

    return results
