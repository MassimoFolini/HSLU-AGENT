import os
import re
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

def dismiss_cookies(page):
    """Zoom-Cookie-Banner ablehnen (verdeckt sonst Knoepfe wie 'Join')."""
    for sel in ('#onetrust-reject-all-handler', 'button:has-text("Decline Cookies")', 'button:has-text("Cookies ablehnen")',
                '#onetrust-accept-btn-handler'):
        try:
            el = page.locator(sel).first
            if el.is_visible():
                el.click(timeout=3000)
                page.wait_for_timeout(800)
                return
        except Exception:
            pass


LEAVE_SEL = ('button:has-text("Leave")', 'button[aria-label*="Leave"]', 'button:has-text("Verlassen")')


def join_meeting(page, context, ilias_link, passcode, email, password, totp_secret, storage_file):
    """Ein Beitritts-Versuch. Gibt True zurück, wenn wir im Meeting sind."""
    print("1. Rufe ILIAS / Zoom Link auf...")
    page.goto(ilias_link, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    if "login.microsoftonline.com" in page.url or "zoom.us/signin" in page.url:
        if "zoom.us/signin" in page.url:
            cookie_btn = page.locator('button:has-text("Accept Cookies")').or_(page.locator('button[id="onetrust-accept-btn-handler"]')).first
            if cookie_btn.is_visible():
                cookie_btn.click()
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
        except Exception:
            pass
        page.goto(ilias_link, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

    print("2. Oeffne den Zoom Web Client direkt...")
    current = page.url.split("#")[0]
    if "/j/" in current:
        page.goto(current.replace("/j/", "/wc/join/"), wait_until="domcontentloaded", timeout=60000)
    elif "/wc/" not in current:
        dismiss_cookies(page)
        join_browser = page.get_by_text(re.compile(r"Join from (your )?browser", re.I)).or_(page.locator('a:has-text("Browser")')).first
        if join_browser.is_visible():
            join_browser.click()
        else:
            print("URL Format unbekannt:", current)
            page.screenshot(path="downloads/live_error.png")
            return False
    page.wait_for_timeout(8000)

    # Beitrittsformular: erst Passcode und Name ausfuellen, dann "Join" (sonst ist der Knopf gesperrt)
    dismiss_cookies(page)
    name_input = page.locator('input[name="inputname"]').or_(page.locator('input#input-for-name')).first
    pass_input = page.locator('input#input-for-pwd').or_(page.locator('input[type="password"]')).first
    try:
        pass_input.or_(name_input).first.wait_for(timeout=20000)
    except Exception:
        pass
    if pass_input.is_visible() and pass_input.input_value():
        print("Passcode ist durch den Link schon ausgefuellt.")
    elif pass_input.is_visible():
        if passcode:
            print("Passcode verlangt, gebe ein...")
            pass_input.fill(passcode)
        else:
            print("Passcode verlangt, aber keiner hinterlegt.")
            page.screenshot(path="downloads/live_error_passcode.png")
            return False
    if name_input.is_visible():
        name_input.fill("KiAgent Bot")
    join_btn = page.locator('button:has-text("Join")').or_(page.locator('button:has-text("Beitreten")')).first
    dismiss_cookies(page)
    if join_btn.is_visible():
        join_btn.click()
        page.wait_for_timeout(8000)

    dismiss_cookies(page)
    print("3. Im Meeting? Klicke auf Computer Audio...")
    page.screenshot(path="downloads/live_meeting_join.png")
    audio_btn = page.locator('button:has-text("Computer Audio")').or_(page.locator('button:has-text("Join Audio by Computer")')).or_(page.locator('button:has-text("Per Computer dem Audio beitreten")')).first
    try:
        audio_btn.wait_for(timeout=20000)
        audio_btn.click()
    except Exception:
        pass
    # Erfolgskriterium: Leave-Button sichtbar
    leave = page.locator(LEAVE_SEL[0]).or_(page.locator(LEAVE_SEL[1])).or_(page.locator(LEAVE_SEL[2])).first
    try:
        leave.wait_for(timeout=15000)
        ensure_silent(page)
        return True
    except Exception:
        return False


MUTE_BTN = re.compile(r"^(Mute|Stummschalten)", re.I)          # Button zeigt "Mute" = Mikrofon ist AN
STOP_VIDEO_BTN = re.compile(r"^(Stop Video|Video beenden|Video stoppen)", re.I)


def ensure_silent(page):
    """Mikrofon stumm und Kamera aus, auch wenn Zoom sie von selbst einschaltet."""
    for pattern in (MUTE_BTN, STOP_VIDEO_BTN):
        try:
            btn = page.get_by_role("button", name=pattern).first
            if btn.is_visible():
                btn.click()
                print("   Mikrofon/Kamera war an, jetzt aus.", flush=True)
                page.wait_for_timeout(500)
        except Exception:
            pass


def meeting_ended(page):
    try:
        txt = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        return False
    return any(k in txt for k in ("meeting has been ended", "meeting has ended", "host has ended",
                                  "meeting wurde beendet", "this meeting is not in progress"))


def leave_meeting(page):
    try:
        leave = page.locator(LEAVE_SEL[0]).or_(page.locator(LEAVE_SEL[2])).first
        if leave.is_visible():
            leave.click()
            page.wait_for_timeout(1500)
            confirm = page.locator('button:has-text("Leave Meeting")').or_(page.locator('button:has-text("Meeting verlassen")')).first
            if confirm.is_visible():
                confirm.click()
    except Exception:
        pass


def main():
    if len(sys.argv) < 3:
        print("Usage: python live_zoom_bot.py <ILIAS_LINK> <MEETING_PASSCODE> [END_UNIX_TS]")
        sys.exit(1)

    ilias_link = sys.argv[1]
    passcode = sys.argv[2]
    end_ts = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else time.time() + 60

    email = os.environ.get('HSLU_MS_EMAIL')
    password = os.environ.get('HSLU_MS_PASSWORD')
    totp_secret = os.environ.get('HSLU_MS_TOTP_SECRET', '').replace(' ', '')
    storage_file = "zoom_storage_state.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Wichtig für Xvfb Audio!
            args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--disable-gpu']
        )
        context = browser.new_context(
            permissions=["microphone"],  # kein Kamera-Zugriff; Mikrofon ist eine stumme virtuelle Quelle
            viewport={"width": 1280, "height": 800},
            storage_state=storage_file if os.path.exists(storage_file) else None
        )
        page = context.new_page()

        joined = False
        MAX_ATTEMPTS = 15   # ca. 15 Minuten: Dozent startet spaeter oder Warteraum
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if time.time() >= end_ts:
                break
            print(f"Beitritts-Versuch {attempt}/{MAX_ATTEMPTS}")
            try:
                joined = join_meeting(page, context, ilias_link, passcode, email, password, totp_secret, storage_file)
            except Exception as e:
                print(f"   Fehler beim Beitritt: {e}")
                page.screenshot(path=f"downloads/live_error_{attempt}.png")
            if joined:
                break
            page.wait_for_timeout(45000)

        if not joined:
            print("FEHLER: Meeting konnte nicht betreten werden.")
            browser.close()
            sys.exit(2)

        print("Erfolgreich beigetreten. Nehme auf bis zur Endzeit...")
        page.screenshot(path="downloads/live_meeting_active.png")
        while time.time() < end_ts:
            if meeting_ended(page):
                print("Meeting wurde vom Host beendet.")
                break
            ensure_silent(page)
            time.sleep(15)

        leave_meeting(page)
        print("Meeting verlassen.")
        browser.close()


if __name__ == "__main__":
    main()
