from scraper import HSLUScraper
from playwright.sync_api import sync_playwright

scraper = HSLUScraper()
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    scraper.login(page)
    courses = scraper.get_enrolled_courses(page)
    dbs_course = next(c for c in courses if 'DBS' in c['title'])
    page.goto(dbs_course['url'])
    page.wait_for_timeout(2000)
    
    # Klicke auf Unterlagen zum Unterricht
    page.locator('a:has-text("Unterlagen zum Unterricht")').first.click()
    page.wait_for_timeout(2000)
    
    # Klicke auf SW01
    page.locator('a:has-text("SW01")').first.click()
    page.wait_for_timeout(2000)
    
    links = page.locator('a').all()
    print('--- Links in SW01 DBS ---')
    for l in links:
        try:
            text = l.inner_text().strip()
            href = l.get_attribute('href')
            if text and href and ('goto.php' in href or 'download' in href.lower()):
                print(f'Text: {text[:40]} | Href: {href}')
        except: pass
    browser.close()
