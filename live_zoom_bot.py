import os
import sys
import time
import pyotp
from playwright.sync_api import sync_playwright

def do_ms_login(page, email, password, totp_secret):
    print("Prüfe MS Login...")
    if "login.microsoftonline.com" in page.url:
        print("   [Zoom SSO] Microsoft Login-Maske aktiv.")
        email_inp = page.locator('input[type="email"]').first
        if email_inp.is_visible():
            page.wait_for_timeout(1000)
            email_inp.fill("")
            page.wait_for_timeout(500)
            email_inp.click()
            email_inp.press_sequentially(email, delay=50)
            page.wait_for_timeout(1000)
            page.locator('input[type="submit"]').click()
            page.wait_for_timeout(3000)

        pwd_sel = 'input[type="password"]'
        try:
            page.locator(pwd_sel).first.wait_for(timeout=5000)
            page.wait_for_timeout(1500)
            pwd_el = page.locator(pwd_sel).first
            pwd_el.fill("")
            page.wait_for_timeout(500)
            pwd_el.click()
            pwd_el.press_sequentially(password, delay=50)
            page.wait_for_timeout(1000)
            page.locator('input[type="submit"]').or_(page.locator('button[type="submit"]')).first.click()
            page.wait_for_timeout(4500)
        except Exception:
            pass

        code_input = page.locator('input[name="otc"]').or_(page.locator('input[type="tel"]')).or_(page.locator('input[id*="idTxtBx_SAOTCC_OTC"]')).first
        if code_input.is_visible() and totp_secret:
            print("   [Zoom SSO] 2FA Authenticator-Code wird verlangt...")
            try:
                totp = pyotp.TOTP(totp_secret.replace(" ", "").upper())
                code = totp.now()
                code_input.fill(code)
                page.wait_for_timeout(500)
                page.locator('input[type="submit"]').or_(page.locator('button:has-text("Verify")')).or_(page.locator('input[value="Verify"]')).first.click()
                page.wait_for_timeout(4000)
            except Exception as e:
                print(f"   [Zoom SSO] Fehler bei TOTP: {e}")

        stay_btn = page.locator('input[value="Yes"]').or_(page.locator('input[value="Ja"]')).first
        try:
            stay_btn.wait_for(timeout=10000)
            stay_btn.click()
            page.wait_for_timeout(3000)
        except Exception:
            pass

def main():
    if len(sys.argv) < 3:
        print("Usage: python live_zoom_bot.py <ILIAS_LINK> <MEETING_PASSCODE>")
        sys.exit(1)
        
    ilias_link = sys.argv[1]
    passcode = sys.argv[2]
    
    email = os.environ.get('HSLU_MS_EMAIL')
    password = os.environ.get('HSLU_MS_PASSWORD')
    totp_secret = os.environ.get('HSLU_MS_TOTP_SECRET', '').replace(' ', '')

    storage_file = "zoom_storage_state.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False, # Wichtig für Xvfb Audio!
            args=[
                '--no-sandbox',
                '--autoplay-policy=no-user-gesture-required',
                '--disable-gpu'
            ]
        )
        context = browser.new_context(
            permissions=["microphone", "camera"],
            viewport={"width": 1280, "height": 800},
            storage_state=storage_file if os.path.exists(storage_file) else None
        )
        page = context.new_page()

        print("1. Rufe ILIAS / Zoom Link auf...")
        page.goto(ilias_link, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # Login falls nötig
        if "login.microsoftonline.com" in page.url or "zoom.us/signin" in page.url:
            if "zoom.us/signin" in page.url:
                cookie_btn = page.locator('button:has-text("Accept Cookies")').or_(page.locator('button[id="onetrust-accept-btn-handler"]')).first
                if cookie_btn.is_visible(): cookie_btn.click()
                sso_icon = page.get_by_text("SSO", exact=True).first
                if sso_icon.is_visible():
                    sso_icon.click(force=True)
                    page.wait_for_timeout(2000)
                    page.locator('input[name="domain"]').first.fill("hslu")
                    page.locator('button[type="submit"]').first.click()
                    page.wait_for_timeout(5000)

            do_ms_login(page, email, password, totp_secret)
            
            try:
                context.storage_state(path=storage_file)
            except:
                pass
            
            page.goto(ilias_link, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

        print("2. Auf Zoom-Launch Seite. Suche 'Join from Browser'...")
        # Zoom Launch Page hat oft einen "Launch Meeting" Knopf oder "Join from Your Browser"
        join_browser = page.locator('a:has-text("Browser")').or_(page.locator('a:has-text("Browser")')).first
        if join_browser.is_visible():
            print("Klicke auf 'Join from Browser'...")
            join_browser.click()
        else:
            print("Kein direkter Browser-Link gefunden, baue Web Client URL zusammen...")
            # Falls URL https://hslu.zoom.us/j/123456789...
            # Zu https://hslu.zoom.us/wc/join/123456789 umbauen
            current = page.url
            if "/j/" in current:
                web_url = current.replace("/j/", "/wc/join/")
                page.goto(web_url)
            else:
                print("URL Format unbekannt:", current)
                page.screenshot(path="downloads/live_error.png")

        page.wait_for_timeout(10000)
        
        # Falls Zoom nochmal nach dem Namen fragt (obwohl SSO)
        name_input = page.locator('input[name="inputname"]').first
        if name_input.is_visible():
            name_input.fill("KiAgent Bot")
            page.locator('button:has-text("Join")').or_(page.locator('button:has-text("Beitreten")')).first.click()
            page.wait_for_timeout(5000)

        # Falls Passcode verlangt wird
        pass_input = page.locator('input[type="password"]').first
        if pass_input.is_visible():
            print("Passcode verlangt, gebe ein...")
            pass_input.fill(passcode)
            page.locator('button:has-text("Join")').or_(page.locator('button:has-text("Beitreten")')).first.click()
            page.wait_for_timeout(8000)

        print("3. Im Meeting? Klicke auf Computer Audio...")
        page.screenshot(path="downloads/live_meeting_join.png")
        audio_btn = page.locator('button:has-text("Computer Audio")').or_(page.locator('button:has-text("Join Audio by Computer")')).or_(page.locator('button:has-text("Per Computer dem Audio beitreten")')).first
        if audio_btn.is_visible():
            audio_btn.click()
        
        print("Erfolgreich beigetreten. Höre zu für 60 Sekunden zum Test...")
        page.screenshot(path="downloads/live_meeting_active.png")
        
        # Wir warten kurz für den Test. In Echt würde er hier laufen, bis das Meeting endet.
        time.sleep(60)
        
        print("Test beendet.")
        browser.close()

if __name__ == "__main__":
    main()
