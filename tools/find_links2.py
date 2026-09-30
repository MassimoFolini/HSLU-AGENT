from scraper import HSLUScraper
from playwright.sync_api import sync_playwright
import json

def inspect_links():
    scraper = HSLUScraper()
    output = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        scraper.login(page)
        
        page.goto("https://elearning.hslu.ch/ilias/goto.php/crs/7206078")
        page.wait_for_timeout(3000)
        
        try:
            page.locator("a:has-text('Course Documents')").first.click()
            page.wait_for_timeout(3000)
            
            page.locator("a:has-text('SW01')").first.click()
            page.wait_for_timeout(3000)
            
            links2 = page.locator("a").all()
            for l in links2:
                try:
                    href = l.get_attribute("href")
                    text = l.inner_text().strip()
                    if href and ("goto.php" in href or "http" in href or "target=" in href):
                        output.append({"text": text, "href": href})
                except:
                    pass
        except Exception as e:
            output.append({"error": str(e)})
            
        browser.close()
    
    with open("links_clean.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

if __name__ == "__main__":
    inspect_links()
