from scraper import HSLUScraper
from playwright.sync_api import sync_playwright
import os

s = HSLUScraper()
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1280, "height": 1200})
    page = ctx.new_page()
    s.login(page)
    
    # Navigiere direkt in DBS
    page.goto("https://elearning.hslu.ch/ilias/goto.php/crs/7206169", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Scrolle nach unten
    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    page.wait_for_timeout(1000)
    page.screenshot(path="screenshots/course_scroll1.png")
    
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    page.screenshot(path="screenshots/course_scroll2.png")
    
    # Liste alle Links im Inhaltsbereich
    items = page.locator('.il-item, .ilContainerListItem, a[href*="goto.php"]').all()
    print(f"Gefundene Elemente: {len(items)}")
    for it in items[:15]:
        try:
            txt = it.inner_text().strip().replace("\n", " ")
            href = it.get_attribute("href") or ""
            if len(txt) > 2:
                print(f"Item: {txt[:60]}... -> {href}")
        except Exception:
            pass
            
    b.close()
