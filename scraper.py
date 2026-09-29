import os
import time
import pyotp
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

class HSLUScraper:
    def __init__(self, download_dir="downloads"):
        self.download_dir = os.path.abspath(download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        self.username = os.environ.get("HSLU_USERNAME")
        self.password = os.environ.get("HSLU_PASSWORD")
        self.totp_secret = os.environ.get("HSLU_TOTP_SECRET", "").replace(" ", "")

    def login(self, page):
        """Führt den vollständigen Login- und 2FA-Prozess bei HSLU / Switch edu-ID durch."""
        print("1. Rufe HSLU ILIAS auf...")
        page.goto("https://elearning.hslu.ch/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 1. Startseiten-Login Button
        login_btn = page.locator('text=Login').or_(page.locator('text=Anmelden')).or_(page.locator('a[href*="login"]')).first
        if login_btn.is_visible():
            print("2. Klicke auf Login...")
            login_btn.click()
            page.wait_for_timeout(2000)

        # 2. OpenID Connect Button
        oidc_btn = page.locator('a:has-text("Login")').or_(page.locator('button:has-text("Login")')).or_(page.locator('.ilStartupSection a')).first
        if oidc_btn.is_visible():
            print("3. Klicke auf OpenID Connect...")
            oidc_btn.click()
            page.wait_for_timeout(3000)

        # 3. SWITCH edu-ID Auswahl
        eduid_btn = page.locator('text="SWITCH edu-ID"').or_(page.locator('a:has-text("SWITCH edu-ID")')).or_(page.locator('button:has-text("SWITCH edu-ID")')).first
        if eduid_btn.is_visible():
            print("4. Wähle SWITCH edu-ID...")
            eduid_btn.click()
            page.wait_for_timeout(3000)

        # 4. Benutzernameneingabe
        print("5. Gebe Benutzernamen ein...")
        user_input = page.locator('input[type="email"]').or_(page.locator('input[name="username"]')).or_(page.locator('input[id*="username"]')).or_(page.locator('input[name="login"]')).first
        if user_input.is_visible():
            user_input.fill(self.username)
            submit_user = page.locator('button[type="submit"]').or_(page.locator('input[type="submit"]')).or_(page.locator('button:has-text("Weiter")')).or_(page.locator('button:has-text("Login")')).or_(page.locator('button[name="_eventId_proceed"]')).first
            if submit_user.is_visible():
                submit_user.click()
                page.wait_for_timeout(2000)

        # 5. Passworteingabe (Passkey-Überspringen falls nötig)
        use_pwd_btn = page.locator('text="Use password"').or_(page.locator('text="Passwort verwenden"')).or_(page.locator('button:has-text("password")')).first
        if use_pwd_btn.is_visible():
            use_pwd_btn.click()
            page.wait_for_timeout(1500)

        print("6. Gebe Passwort ein...")
        pwd_input = page.locator('input[type="password"]').first
        if pwd_input.is_visible():
            pwd_input.fill(self.password)
            submit_pwd = page.locator('button[type="submit"]').or_(page.locator('input[type="submit"]')).or_(page.locator('button:has-text("Log in")')).or_(page.locator('button:has-text("Anmelden")')).first
            if submit_pwd.is_visible():
                submit_pwd.click()
                page.wait_for_timeout(3000)

        # 6. 2FA / TOTP Code eingeben
        totp_input = page.locator('input[name*="otp"]').or_(page.locator('input[name*="code"]')).or_(page.locator('input[id*="otp"]')).or_(page.locator('input[type="tel"]')).or_(page.locator('input[maxlength="6"]')).first
        if totp_input.is_visible():
            print("7. Generiere und sende 2FA-Code (TOTP)...")
            totp = pyotp.TOTP(self.totp_secret)
            current_code = totp.now()
            totp_input.fill(current_code)
            submit_totp = page.locator('button[type="submit"]').or_(page.locator('input[type="submit"]')).or_(page.locator('button:has-text("Prüfen")')).or_(page.locator('button:has-text("Verify")')).first
            if submit_totp.is_visible():
                submit_totp.click()
                page.wait_for_timeout(4000)

        print("8. Login abgeschlossen! Warte auf Dashboard...")
        page.wait_for_selector('text="Dashboard"', timeout=30000)
        print("-> Dashboard erfolgreich geladen!")

    def get_enrolled_courses(self, page, current_semester_only=True):
        """Liest die belegten Kurse und deren Links aus dem Dashboard aus."""
        courses = []
        seen_urls = set()
        
        # In ILIAS 10 sind alle Kurse über goto.php/crs/ verlinkt
        links = page.locator('a[href*="goto.php/crs/"]').all()
        for link in links:
            try:
                title = link.inner_text().strip()
                href = link.get_attribute("href")
                if title and href and href not in seen_urls:
                    seen_urls.add(href)
                    # Falls gewünscht, nur aktuelles Semester (z.B. Herbst 2026 = H26) filtern
                    if current_semester_only and not ("H26" in title or "H26" in href):
                        continue
                    courses.append({"title": title, "url": href})
            except Exception:
                pass
        return courses

    def login_and_download(self, week_identifier):
        """Hauptmethode für das wöchentliche Scraping."""
        print(f"Starte wöchentliches Scraping für: {week_identifier}")
        downloaded = {"pdfs": [], "videos": [], "todos": []}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            # 1. Login
            self.login(page)

            # 2. Belegte Module auslesen
            courses = self.get_enrolled_courses(page)
            print(f"Gefundene Kurse auf dem Dashboard: {len(courses)}")
            downloaded["courses"] = courses
            for c in courses:
                print(f" - {c['title']}")

            # 3. To-Dos auslesen (z.B. Abgaben auf der rechten Seite)
            todo_elements = page.locator('.il-block-todo, div:has-text("Abgabe zur Übungseinheit")').all()
            for td in todo_elements:
                text = td.inner_text().strip()
                if text:
                    downloaded["todos"].append(text)

            browser.close()

        return downloaded
