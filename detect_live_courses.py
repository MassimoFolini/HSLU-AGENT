import os
import json
import dotenv
from playwright.sync_api import sync_playwright
from scraper import HSLUScraper

dotenv.load_dotenv('/opt/KiAgentHSLU/.env')
username = os.environ.get('HSLU_USERNAME')
password = os.environ.get('HSLU_PASSWORD')

def main():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            scraper = HSLUScraper()
            scraper.login(page)
                
            print("Prüfe Dashboard auf Fächer mit gelbem Lernfortschritt...")
            page.goto("https://elearning.hslu.ch/ilias/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems", wait_until="networkidle", timeout=60000)
            
            with open("/tmp/ilias_dash.html", "w", encoding="utf-8") as f:
                f.write(page.content())

            
            # Suche alle Kurs-Container
            courses = []
            containers = page.locator('.il-item').all()
            for container in containers:
                try:
                    title_el = container.locator('h4.il-item-title a').first
                    if not title_el.is_visible():
                        title_el = container.locator('a').first
                    
                    if title_el.is_visible():
                        title = title_el.inner_text().strip()
                        # Prüfe auf "Lernfortschritt" in text oder gelbes icon
                        html = container.inner_html().lower()
                        # Meistens "inprogress" im Bild-Namen oder "lernfortschritt"
                        if "lernfortschritt" in html:
                            if "in_progress.svg" in html or "in bearbeitung" in html or "in progress" in html:
                                courses.append({
                                    "title": title,
                                    "meeting_id": "",
                                    "passcode": "",
                                    "day": "1",
                                    "time_start": "",
                                    "time_end": "",
                                    "record": False
                                })
                except Exception as e:
                    print("Fehler bei Container:", e)

            # Speichern in live_meetings.json
            with open("/opt/KiAgentHSLU/live_meetings.json", "w", encoding="utf-8") as f:
                json.dump(courses, f, indent=4, ensure_ascii=False)
            
            print(f"Erfolgreich {len(courses)} Fächer erkannt.")
            browser.close()
    except Exception as e:
        print("Fehler:", e)
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
