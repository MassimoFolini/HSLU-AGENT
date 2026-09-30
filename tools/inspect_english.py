from scraper import HSLUScraper
from playwright.sync_api import sync_playwright

scraper = HSLUScraper()
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    scraper.login(page)
    
    page.goto('https://elearning.hslu.ch/ilias/goto.php/crs/7206078')
    page.wait_for_timeout(2000)
    
    page.locator('a:has-text("Course Documents")').first.click()
    page.wait_for_timeout(2000)
    
    page.locator('a:has-text("SW01 - CW38")').first.click()
    page.wait_for_timeout(2000)
    
    links = page.locator('a').all()
    print('--- Links in SW01 ---')
    for l in links:
        try:
            text = l.inner_text().strip()
            href = l.get_attribute('href')
            if text and href:
                print(f'Text: {text[:30]} | Href: {href}')
        except: pass
    browser.close()
