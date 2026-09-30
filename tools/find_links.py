from scraper import HSLUScraper
from playwright.sync_api import sync_playwright

def inspect_links():
    scraper = HSLUScraper()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        scraper.login(page)
        
        # Gehe zur Hauptseite von Academic English
        page.goto("https://elearning.hslu.ch/ilias/goto.php/crs/7206078")
        page.wait_for_timeout(3000)
        
        links = page.locator("a").all()
        print("--- ALLE LINKS AUF DER ENGLISCH HAUPTSEITE ---")
        for l in links:
            try:
                href = l.get_attribute("href")
                text = l.inner_text().strip()
                if href and ("goto.php" in href or "http" in href):
                    print(f"TEXT: {text[:40]} | HREF: {href}")
            except:
                pass
                
        # Gehe zu Course Documents
        try:
            page.locator("a:has-text('Course Documents')").first.click()
            page.wait_for_timeout(3000)
            
            # Gehe zu SW01 - CW38
            page.locator("a:has-text('SW01')").first.click()
            page.wait_for_timeout(3000)
            
            links2 = page.locator("a").all()
            print("\n--- ALLE LINKS IN SW01 ---")
            for l in links2:
                try:
                    href = l.get_attribute("href")
                    text = l.inner_text().strip()
                    if href and ("goto.php" in href or "http" in href):
                        print(f"TEXT: {text[:40]} | HREF: {href}")
                except:
                    pass
        except Exception as e:
            print("Fehler beim Navigieren:", e)
            
        browser.close()

if __name__ == "__main__":
    inspect_links()
