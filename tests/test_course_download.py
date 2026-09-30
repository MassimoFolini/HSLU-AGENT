from scraper import HSLUScraper
from playwright.sync_api import sync_playwright
import os

s = HSLUScraper()
os.makedirs("downloads", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(accept_downloads=True)
    page = ctx.new_page()
    
    # 1. Login
    s.login(page)
    
    # 2. Kurse holen
    courses = s.get_enrolled_courses(page)
    print(f"Gefundene aktive Kurse: {[c['title'] for c in courses]}")
    
    # Navigiere in den ersten Kurs (z.B. DBS oder KRR)
    target_course = None
    for c in courses:
        if "DBS" in c["title"] or "KRR" in c["title"]:
            target_course = c
            break
    if not target_course and courses:
        target_course = courses[0]
        
    if target_course:
        print(f"Navigiere in Kurs: {target_course['title']} ({target_course['url']})")
        page.goto(target_course['url'], wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path="screenshots/course_view.png")
        
        # Finde Datei-Links (z.B. goto.php/file/ oder .pdf)
        file_links = page.locator('a[href*="goto.php/file/"], a[href*="download"], a[href*=".pdf"]').all()
        print(f"Gefundene Dateilinks im Kurs: {len(file_links)}")
        for fl in file_links[:5]:
            try:
                print(f"Datei: {fl.inner_text().strip()} -> {fl.get_attribute('href')}")
            except Exception:
                pass
                
    b.close()
