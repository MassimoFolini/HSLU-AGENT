import os
import time
import pyotp
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def test_hslu_login():
    username = os.environ.get("HSLU_USERNAME")
    password = os.environ.get("HSLU_PASSWORD")
    totp_secret = os.environ.get("HSLU_TOTP_SECRET", "").replace(" ", "")

    os.makedirs("screenshots", exist_ok=True)
    
    print("Starte Playwright Browser für HSLU Login-Test...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 1. Startseite aufrufen
        start_url = "https://elearning.hslu.ch/"
        print(f"1. Rufe Startseite auf: {start_url}")
        page.goto(start_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path="screenshots/01_start.png")
        print(f"   Aktuelle URL: {page.url}")
        print(f"   Seitentitel: {page.title()}")

        # Prüfen, ob wir bereits auf Switch edu-ID oder Microsoft SSO weitergeleitet wurden
        # oder ob es einen Login-Button gibt (z.B. AAI / Switch edu-ID Login)
        print("2. Suche nach Login-Elementen...")
        
        # Falls es einen "Login" oder "Switch edu-ID" Button gibt:
        login_btn = page.locator('text=Login').or_(page.locator('text=Anmelden')).or_(page.locator('a[href*="login"]')).first
        if login_btn.is_visible():
            print("   Klicke auf ersten Login-Button...")
            login_btn.click()
            page.wait_for_timeout(3000)
            page.screenshot(path="screenshots/02_after_click_login.png")
            print(f"   Neue URL: {page.url}")

        # Auf der ILIAS Login-Seite gibt es "Bei ILIAS anmelden über OpenID Connect" mit einem Login-Link/Button
        oidc_btn = page.locator('a:has-text("Login")').or_(page.locator('button:has-text("Login")')).or_(page.locator('.ilStartupSection a')).first
        if oidc_btn.is_visible():
            print("   Klicke auf OpenID Connect Login-Button...")
            oidc_btn.click()
            page.wait_for_timeout(4000)
            page.screenshot(path="screenshots/02b_after_oidc_click.png")
            print(f"   URL nach OpenID Connect Klick: {page.url}")

        # Auf Keycloak: SWITCH edu-ID auswählen (Option 1)
        eduid_btn = page.locator('text="SWITCH edu-ID"').or_(page.locator('a:has-text("SWITCH edu-ID")')).or_(page.locator('button:has-text("SWITCH edu-ID")')).first
        if eduid_btn.is_visible():
            print("   Klicke auf 'SWITCH edu-ID'...")
            eduid_btn.click()
            page.wait_for_timeout(4000)
            page.screenshot(path="screenshots/02c_after_eduid_click.png")
            print(f"   URL auf Switch edu-ID: {page.url}")

        # 3. Benutzernameneingabe (auf Switch edu-ID)
        print("3. Versuche Benutzernamen einzugeben...")
        user_input = page.locator('input[type="email"]').or_(page.locator('input[name="username"]')).or_(page.locator('input[id*="username"]')).or_(page.locator('input[name="login"]')).first
        if user_input.is_visible():
            print("   Benutzername-Feld gefunden!")
            user_input.fill(username)
            page.screenshot(path="screenshots/03_username_entered.png")
            
            submit_user = page.locator('button[type="submit"]').or_(page.locator('input[type="submit"]')).or_(page.locator('button:has-text("Weiter")')).or_(page.locator('button:has-text("Login")')).or_(page.locator('button[name="_eventId_proceed"]')).first
            if submit_user.is_visible():
                submit_user.click()
                page.wait_for_timeout(3000)
        else:
            print("   Kein Standard-Benutzernamefeld direkt sichtbar.")

        page.screenshot(path="screenshots/04_after_username.png")
        print(f"   Aktuelle URL nach Username: {page.url}")

        # 4. Passworteingabe auf Switch edu-ID
        print("4. Prüfe auf 'Use password' Button...")
        use_pwd_btn = page.locator('text="Use password"').or_(page.locator('text="Passwort verwenden"')).or_(page.locator('button:has-text("password")')).first
        if use_pwd_btn.is_visible():
            print("   Klicke auf 'Use password'...")
            use_pwd_btn.click()
            page.wait_for_timeout(2000)

        print("   Versuche Passwort einzugeben...")
        pwd_input = page.locator('input[type="password"]').first
        if pwd_input.is_visible():
            print("   Passwort-Feld gefunden!")
            pwd_input.fill(password)
            page.screenshot(path="screenshots/05_password_entered.png")
            
            submit_pwd = page.locator('button[type="submit"]').or_(page.locator('input[type="submit"]')).or_(page.locator('button:has-text("Log in")')).or_(page.locator('button:has-text("Anmelden")')).first
            if submit_pwd.is_visible():
                submit_pwd.click()
                page.wait_for_timeout(4000)
        else:
            print("   Kein Passwortfeld sichtbar.")

        page.screenshot(path="screenshots/06_after_password.png")
        print(f"   Aktuelle URL nach Passwort: {page.url}")

        # 5. 2FA / TOTP Eingabe
        print("5. Prüfe auf 2FA / Code-Abfrage...")
        totp_input = page.locator('input[name*="otp"]').or_(page.locator('input[name*="code"]')).or_(page.locator('input[id*="otp"]')).or_(page.locator('input[type="tel"]')).or_(page.locator('input[maxlength="6"]')).first
        if totp_input.is_visible():
            print("   2FA-Eingabefeld gefunden!")
            totp = pyotp.TOTP(totp_secret)
            current_code = totp.now()
            print(f"   Trage generierten TOTP-Code ein...")
            totp_input.fill(current_code)
            page.screenshot(path="screenshots/07_totp_entered.png")
            
            submit_totp = page.locator('button[type="submit"]').or_(page.locator('input[type="submit"]')).or_(page.locator('button:has-text("Prüfen")')).or_(page.locator('button:has-text("Verify")')).first
            if submit_totp.is_visible():
                submit_totp.click()
                page.wait_for_timeout(5000)
        else:
            print("   Kein offensichtliches 2FA-Feld gefunden (oder noch auf anderer Seite).")

        page.screenshot(path="screenshots/08_final_state.png")
        print(f"6. Endzustand erreicht!")
        print(f"   End-URL: {page.url}")
        print(f"   End-Titel: {page.title()}")

        browser.close()

if __name__ == "__main__":
    test_hslu_login()
