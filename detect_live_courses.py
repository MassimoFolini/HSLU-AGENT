"""Erkennt Faecher mit gelbem Lernfortschritt im ILIAS-Dashboard und ergaenzt live_meetings.json.

Bestehende Eintraege (Meeting-ID, Passcode, Zeiten) bleiben erhalten; es werden nur neue Faecher hinzugefuegt.
"""
import json
import os
import sys

import dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from scraper import HSLUScraper

BASE = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(BASE, ".env"))
MEETINGS_FILE = os.path.join(BASE, "live_meetings.json")
DASH_URL = "https://elearning.hslu.ch/ilias/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems"
ATTEMPTS = 3


def load_dashboard(page):
    """Laedt das Dashboard robust: kein 'networkidle', sondern warten, bis Kurs-Eintraege da sind."""
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            page.goto(DASH_URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_selector(".il-item", timeout=60000)
            page.wait_for_timeout(2000)
            return
        except PlaywrightTimeout as e:
            last = e
            print(f"   Dashboard-Ladeversuch {attempt}/{ATTEMPTS} fehlgeschlagen, neuer Versuch...", flush=True)
    raise RuntimeError(f"Dashboard konnte nicht geladen werden: {last}")


def find_courses(page):
    courses = []
    for container in page.locator(".il-item").all():
        try:
            title_el = container.locator("h4.il-item-title a").first
            if not title_el.is_visible():
                title_el = container.locator("a").first
            if not title_el.is_visible():
                continue
            html = container.inner_html().lower()
            if "lernfortschritt" in html and ("in_progress.svg" in html or "in bearbeitung" in html or "in progress" in html):
                courses.append(title_el.inner_text().strip())
        except Exception as e:
            print("Fehler bei Container:", e)
    return courses


def main():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_context().new_page()
                HSLUScraper().login(page)
                print("Pruefe Dashboard auf Faecher mit gelbem Lernfortschritt...", flush=True)
                load_dashboard(page)
                titles = find_courses(page)
            finally:
                browser.close()
    except Exception as e:
        print("Fehler:", e)
        sys.exit(1)

    try:
        with open(MEETINGS_FILE, "r", encoding="utf-8") as f:
            meetings = json.load(f)
    except Exception:
        meetings = []
    known = {m.get("title") for m in meetings}
    added = 0
    for t in titles:
        if t not in known:
            meetings.append({"title": t, "meeting_id": "", "passcode": "", "day": "1",
                             "time_start": "", "time_end": "", "record": False})
            added += 1
    with open(MEETINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(meetings, f, indent=4, ensure_ascii=False)
    print(f"Erfolgreich {len(titles)} Faecher erkannt, {added} neu hinzugefuegt.")


if __name__ == "__main__":
    main()
