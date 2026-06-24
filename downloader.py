"""
下载模块 — 课件下载到本地，图片按章节合成PDF

流程：
  1. 下载所有图片到临时目录（跳过已存在的）
  2. 按章节分组 → 每组图片合成为一个PDF
  3. 删除临时图片
"""
import os, time, random, re
from pathlib import Path
from collections import defaultdict
import requests

COURSES_DIR = Path(__file__).parent / "courses"


def _requests_session(cookies: list[dict]) -> requests.Session:
    session = requests.Session()
    for c in cookies:
        session.cookies.set(
            name=c.get("name", ""), value=c.get("value", ""),
            domain=c.get("domain", ""), path=c.get("path", "/")
        )
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://mooc1.chaoxing.com/",
        "Accept": "*/*",
    })
    return session


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name.strip()[:120]


def download_coursewares(cookies: list[dict], course_name: str, coursewares: list[dict]):
    """下载课件：图片→按章节合成PDF，PDF/PPT直接下载"""
    course_dir = COURSES_DIR / sanitize_filename(course_name)
    course_dir.mkdir(parents=True, exist_ok=True)

    session = _requests_session(cookies)
    success = 0
    skipped = 0
    failed = 0
    image_groups = defaultdict(list)  # {chapter_name: [(local_path, url), ...]}

    for i, cw in enumerate(coursewares, 1):
        name = sanitize_filename(cw.get("name", f"课件{i}"))
        url = cw.get("url", "")
        cw_type = cw.get("type", "html")

        # 提取章节名（去掉 _XX 后缀）
        chapter_name = re.sub(r'_\d+$', '', name)

        print(f"  [{i}/{len(coursewares)}] {name} ({cw_type})")

        if not url:
            print(f"    ⚠️ 无下载链接，跳过")
            failed += 1
            continue

        # 文件类型 → 扩展名映射
        type_ext = {
            "pdf": ".pdf", "ppt": ".pptx", "doc": ".doc", "docx": ".docx",
            "xls": ".xls", "xlsx": ".xlsx",
            "video": ".mp4", "audio": ".mp3", "archive": ".zip", "text": ".txt",
            "image": ".png",
        }
        # 如果文件名已包含正确的扩展名，去掉它以避免重复
        name_lower = name.lower()
        for ext in [".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls",
                     ".mp4", ".mp3", ".flv", ".zip", ".rar", ".txt", ".png", ".jpg"]:
            if name_lower.endswith(ext) and len(name) > len(ext):
                name = name[:-len(ext)]
                break
        # 直接用 URL 推断扩展名（处理 type 为 html 但实际是文件的链接）
        actual_ext = ""
        url_lower = url.lower()
        for ext in [".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls",
                     ".mp4", ".mp3", ".flv", ".zip", ".rar", ".txt", ".png", ".jpg", ".jpeg"]:
            if ext in url_lower:
                actual_ext = ext
                break
        # 用 URL 扩展名修正类型
        if actual_ext and cw_type in ("html", "", None):
            mapped = {".pdf":"pdf",".pptx":"ppt",".ppt":"ppt",".doc":"doc",".docx":"doc",
                      ".xls":"xls",".xlsx":"xls",".mp4":"video",".mp3":"audio",
                      ".flv":"video",".zip":"archive",".rar":"archive",".txt":"text",
                      ".png":"image",".jpg":"image",".jpeg":"image"}
            cw_type = mapped.get(actual_ext, cw_type)

        try:
            if cw_type == "image":
                # 先下载为临时PNG，稍后合成PDF
                tmp_path = course_dir / f"_tmp_{name}.png"
                if tmp_path.exists():
                    print(f"    ⏭️ 已存在，跳过")
                    skipped += 1
                    image_groups[chapter_name].append((tmp_path, url))
                else:
                    _download_image(session, url, tmp_path)
                    image_groups[chapter_name].append((tmp_path, url))
                    success += 1

            elif cw_type in type_ext:
                ext = type_ext[cw_type]
                fpath = course_dir / f"{name}{ext}"
                if fpath.exists():
                    print(f"    ⏭️ 已存在，跳过")
                    skipped += 1
                else:
                    _download_file(session, url, fpath)
                    success += 1

            else:
                # 真正的 HTML 文本类课件
                fpath = course_dir / f"{name}.txt"
                if fpath.exists():
                    print(f"    ⏭️ 已存在，跳过")
                    skipped += 1
                else:
                    _download_html(session, url, course_dir, name)
                    success += 1

        except Exception as e:
            print(f"    ❌ 下载失败：{e}")
            failed += 1

        if i < len(coursewares):
            time.sleep(random.uniform(1.0, 3.0))

    # ── OCR + 合成PDF ──
    pdf_count = 0
    ocr_count = 0
    if image_groups:
        print(f"\n📦 处理课件（{len(image_groups)} 个章节）...")
        # 初始化 OCR（延迟加载）
        ocr = _get_ocr()

        for chapter_name, img_list in sorted(image_groups.items()):
            pdf_path = course_dir / f"{chapter_name}.pdf"
            txt_path = course_dir / f"{chapter_name}.txt"

            # 去重排序
            unique_imgs = []
            seen = set()
            for tmp_path, img_url in img_list:
                if img_url not in seen:
                    seen.add(img_url)
                    unique_imgs.append(tmp_path)
            unique_imgs.sort(key=lambda p: p.stem)

            if not unique_imgs:
                continue

            # ── OCR（如果 txt 不存在） ──
            if not txt_path.exists():
                print(f"  🔍 OCR: {chapter_name}（{len(unique_imgs)} 页）...")
                try:
                    all_text = []
                    for j, img_path in enumerate(unique_imgs):
                        text = _ocr_image(ocr, img_path)
                        if text:
                            all_text.append(f"[第{j+1}页]\n{text}")
                        if (j + 1) % 5 == 0:
                            print(f"     {j+1}/{len(unique_imgs)} 页完成")
                    if all_text:
                        txt_path.write_text("\n\n".join(all_text), encoding="utf-8")
                        print(f"  ✅ {chapter_name}.txt ({len(all_text)} 页文字)")
                        ocr_count += 1
                    else:
                        print(f"  ⚠️ {chapter_name} 未识别到文字")
                except Exception as e:
                    print(f"  ⚠️ OCR 失败 {chapter_name}: {e}")
            else:
                print(f"  ⏭️ {chapter_name}.txt 已存在")

            # ── 合成 PDF ──
            if not pdf_path.exists():
                try:
                    _images_to_pdf(unique_imgs, pdf_path)
                    print(f"  ✅ {chapter_name}.pdf ({len(unique_imgs)} 页)")
                    pdf_count += 1
                except Exception as e:
                    print(f"  ❌ 合成失败 {chapter_name}: {e}")
            else:
                print(f"  ⏭️ {chapter_name}.pdf 已存在")

            # 删除临时图片
            for tmp_path in unique_imgs:
                if tmp_path.exists():
                    tmp_path.unlink()

    print(f"\n📊 下载完成：成功 {success}，跳过 {skipped}，失败 {failed}，PDF {pdf_count}")
    print(f"📁 {course_dir}")


def _download_file(session, url, filepath: Path):
    resp = session.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"    ✅ {filepath.name} ({_fmt(filepath.stat().st_size)})")


def _download_image(session, url, filepath: Path):
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    with open(filepath, "wb") as f:
        f.write(resp.content)
    print(f"    ✅ {filepath.name} ({_fmt(len(resp.content))})")


def _download_html(session, url, dest_dir: Path, name: str):
    resp = session.get(url, timeout=30)
    resp.encoding = "utf-8"
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    body = soup.find("body")
    text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    cleaned = "\n".join(lines)
    if not cleaned:
        raise Exception("页面无文本内容")
    filepath = dest_dir / f"{name}.txt"
    filepath.write_text(cleaned, encoding="utf-8")
    print(f"    ✅ {name}.txt ({len(cleaned)} 字符)")


_ocr_instance = None

def _get_ocr():
    """延迟初始化 OCR（首次调用时加载模型，约 100MB）"""
    global _ocr_instance
    if _ocr_instance is None:
        import easyocr
        print("  ⏳ 加载 OCR 模型（首次较慢，约30秒）...")
        _ocr_instance = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
        print("  ✅ OCR 就绪")
    return _ocr_instance


def _ocr_image(ocr, img_path: Path) -> str:
    """对单张图片 OCR，返回识别文字"""
    try:
        results = ocr.readtext(str(img_path), detail=0)
        return "\n".join(results) if results else ""
    except Exception:
        return ""


def _images_to_pdf(image_paths: list[Path], output_path: Path):
    """将多张图片合成为一个PDF"""
    from PIL import Image

    images = []
    for p in image_paths:
        img = Image.open(p).convert("RGB")
        images.append(img)

    if images:
        images[0].save(
            str(output_path), "PDF",
            save_all=True,
            append_images=images[1:] if len(images) > 1 else []
        )


def _fmt(size: int) -> str:
    for u in ["B", "KB", "MB"]:
        if size < 1024:
            return f"{size:.1f} {u}"
        size /= 1024
    return f"{size:.1f} GB"
