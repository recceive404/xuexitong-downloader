"""诊断 v14 — 直接访问 knowledge/cards iframe URL"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

COOKIE_FILE = Path(__file__).parent / "cookies.json"

def main():
    cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        # The knowledge card iframe src from v13
        kurl = "https://mooc2-ans.chaoxing.com/mooc-ans/knowledge/cards?clazzid=142720356&courseid=261802842&knowledgeid=1150611442&num=0&ut=s&cpi=405508640&v=2025-0424-1038-3&mooc2=1"
        print(f"Navigating to knowledge card...")
        page.goto(kurl, wait_until="networkidle", timeout=20000)
        time.sleep(3)

        print(f"URL: {page.url[:150]}")
        body = page.inner_text("body")[:500]
        print(f"Body: {body}")

        # Find ALL images
        imgs = page.evaluate("""
            () => {
                const r=[];
                document.querySelectorAll('img[src]').forEach(img=>{
                    const s=img.src||''; const w=img.naturalWidth||0; const h=img.naturalHeight||0;
                    if(s.startsWith('http')) r.push({src:s, w, h});
                });
                return r;
            }
        """)
        print(f"\nAll images ({len(imgs)}):")
        for img in imgs:
            print(f"  {img['w']}x{img['h']} {img['src'][:200]}")

        # Check any iframes
        iframes = page.query_selector_all("iframe")
        print(f"\nIframes: {len(iframes)}")

        page.screenshot(path=str(Path(__file__).parent / "diag_v14.png"))
        print("\nScreenshot: diag_v14.png")

        browser.close()

if __name__ == "__main__":
    main()
