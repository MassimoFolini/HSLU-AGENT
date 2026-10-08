"""Holt alle Zoom-Aufzeichnungen (ILIAS-Weblinks) nach und laedt sie nach Drive.

  python maintenance/fetch_zoom_recordings.py            # alle Kurse
  python maintenance/fetch_zoom_recordings.py ASTAT      # nur Kurse, deren Titel das Stichwort enthaelt

Aus dem Projektroot starten. Bereits vorhandene Dateien werden uebersprungen.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from google_integration import GoogleWorkspace
from main import DriveSync, clean_subject_name, sync_course_to_drive
from scraper import HSLUScraper, safe_name
from zoom_downloader import ZoomDownloader

load_dotenv()
WEEK_DIR = os.path.join("downloads", "Woche_02")


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""
    scraper = HSLUScraper()
    courses_data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1280, "height": 800})
        page = context.new_page()
        scraper.login(page)
        scraper._build_http_session(context)
        for course in scraper.get_enrolled_courses(page):
            if keyword and keyword not in course["title"]:
                continue
            courses_data.append(scraper.scrape_single_course(page, course, WEEK_DIR))
        browser.close()

    zoom = ZoomDownloader()
    if not zoom.is_configured():
        print("HSLU_MS_EMAIL/HSLU_MS_PASSWORD fehlen in .env")
        return
    sync = DriveSync(GoogleWorkspace())
    for c in courses_data:
        for v in c["videos"]:
            url = v.get("resolved_url") or v["url"]
            if "zoom.us/rec/" not in url:
                continue
            out_dir = v.get("local_dir") or os.path.join(c["dir"], "Unterlagen")
            print(f"[Zoom] {c['title']}: {v['text']}", flush=True)
            zoom.download_recording(url, output_dir=out_dir, file_basename=safe_name(v["text"] or "Aufzeichnung"))
        sync_course_to_drive(sync, c, clean_subject_name(c["title"]))
    print("Fertig.")


if __name__ == "__main__":
    main()
