import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os
import time
import pyotp
from playwright.sync_api import sync_playwright
import dotenv

dotenv.load_dotenv('/opt/KiAgentHSLU/.env')
email = os.environ.get('HSLU_MS_EMAIL') or os.environ.get('HSLU_USERNAME')
pwd = os.environ.get('HSLU_MS_PASSWORD')
ms_totp = os.environ.get('HSLU_MS_TOTP_SECRET', '').replace(' ', '')
totp_secret = ms_totp or os.environ.get('HSLU_TOTP_SECRET', '').replace(' ', '')

print("="*60)
print(f"TEST: MICROSOFT 365 & ZOOM LOGIN FÜR: {email}")
print(f"Passwort konfiguriert: {'Ja (' + str(len(pwd)) + ' Zeichen)' if pwd else 'NEIN'}")
print(f"MS TOTP Secret konfiguriert: {'Ja' if ms_totp else 'Nein (Fallback auf Standard TOTP)'}")
print("="*60)

os.makedirs("downloads", exist_ok=True)
storage_file = os.path.join(os.path.abspath("downloads"), "zoom_storage_state.json")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    
    # Versuche bestehende Session zu laden falls vorhanden
    context_kwargs = {"viewport": {"width": 1280, "height": 800}, "accept_downloads": True}
    if os.path.exists(storage_file):
        try:
            context_kwargs["storage_state"] = storage_file
            print("Lade gespeicherte Zoom-Browser-Session...")
        except Exception:
            pass
            
    context = browser.new_context(**context_kwargs)
    page = context.new_page()

    media_urls = []
    context.on("response", lambda r: media_urls.append(r.url) if (
        any(x in r.url.lower() for x in [".mp4", "/rec/download", "/rec/play", "videoplayback"])
        and "zoom.us" in r.url
    ) else None)
    
    def do_ms_login():
        if "login.microsoftonline.com" in page.url:
            print("-> Microsoft Login-Maske geladen.")
            # Email
            email_inp = page.locator('input[type="email"]').first
            if email_inp.is_visible():
                page.wait_for_timeout(1000)
                print("2. Gebe Microsoft E-Mail ein...")
                email_inp.fill("")
                page.wait_for_timeout(500)
                email_inp.click()
                email_inp.press_sequentially(email, delay=50)
                page.wait_for_timeout(1000)
                page.locator('input[type="submit"]').click()
                page.wait_for_timeout(3000)

            # Passwort
            pwd_sel = 'input[type="password"]'
            try:
                page.locator(pwd_sel).first.wait_for(timeout=5000)
                page.wait_for_timeout(1500)
                print("3. Gebe Microsoft Passwort ein...")
                pwd_el = page.locator(pwd_sel).first
                pwd_el.fill("")
                page.wait_for_timeout(500)
                pwd_el.click()
                pwd_el.press_sequentially(pwd, delay=50)
                page.wait_for_timeout(1000)
                page.locator('input[type="submit"]').or_(page.locator('button[type="submit"]')).first.click()
                page.wait_for_timeout(4500)
            except Exception:
                print("Kein Passwortfeld gefunden.")

            # Prüfe auf 2FA / TOTP Eingabe
            code_input = page.locator('input[name="otc"]').or_(page.locator('input[type="tel"]')).or_(page.locator('input[id*="idTxtBx_SAOTCC_OTC"]')).first
            if code_input.is_visible():
                print("4. 2FA Authenticator Code wird verlangt...")
                if totp_secret:
                    try:
                        totp = pyotp.TOTP(totp_secret.replace(" ", "").upper())
                        code = totp.now()
                        print(f"-> Generiere Code ({code}) und sende...")
                        code_input.fill(code)
                        page.wait_for_timeout(500)
                        page.locator('input[type="submit"]').or_(page.locator('button:has-text("Verify")')).or_(page.locator('input[value="Verify"]')).first.click()
                        page.wait_for_timeout(4000)
                    except Exception as e:
                        print(f"Fehler bei TOTP-Generierung: {e}")
                else:
                    print("Hinweis: Kein MS TOTP Secret konfiguriert. Bitte im Dashboard eintragen!")

            # 'Angemeldet bleiben' bestätigen
            stay_btn = page.locator('input[value="Yes"]').or_(page.locator('input[value="Ja"]')).first
            try:
                stay_btn.wait_for(timeout=10000)
                print("5. Bestätige 'Angemeldet bleiben'...")
                stay_btn.click()
                page.wait_for_timeout(3000)
            except Exception:
                pass

    print("\n1. Prüfe Zoom SAML Login...")
    page.goto("https://hslu.zoom.us/saml/login", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    
    do_ms_login()

    # Session speichern falls erfolgreich
    if "zoom.us" in page.url or "microsoft" not in page.url:
        print("-> Erfolgreich authentifiziert! Speichere Browser-Session...")
        try:
            context.storage_state(path=storage_file)
            print(f"-> Session-Status gespeichert in {storage_file}")
        except Exception as e:
            print(f"Session-Speicherfehler: {e}")

    # Ziel-Aufzeichnung testen
    target_url = "https://elearning.hslu.ch/ilias/ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=7322433&cmd=calldirectlink"
    print(f"\n6. Rufe Zoom-Aufzeichnung auf: {target_url}")
    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)
    
    print("Aktuelle URL:", page.url)
    print("Seitentitel:", page.title())
    
    if "zoom.us/signin" in page.url:
        print("-> Zoom erfordert separaten Login. Akzeptiere Cookies...")
        cookie_btn = page.locator('button:has-text("Accept Cookies")').or_(page.locator('button[id="onetrust-accept-btn-handler"]')).first
        if cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(1000)
            
        print("-> Klicke auf SSO Button...")
        sso_icon = page.get_by_text("SSO", exact=True).first
        if sso_icon.is_visible():
            sso_icon.click(force=True)
            page.wait_for_timeout(3000)
            print("-> Nach SSO Klick, URL:", page.url)
            
            try:
                domain_inp = page.locator('input[name="domain"]').or_(page.locator('input[type="text"]')).first
                domain_inp.fill("hslu", timeout=10000)
                page.locator('button[type="submit"]').or_(page.locator('button:has-text("Continue")')).first.click()
                page.wait_for_timeout(8000)
            except Exception as e:
                print("Domain Input Fehler/Nicht nötig:", e)
                
            # Warte auf Microsoft Redirect falls nötig
            if "microsoft" in page.url:
                print("Warte auf Abschluss des Microsoft SSO...")
                try:
                    page.wait_for_url("**/rec/share/**", timeout=20000)
                except Exception:
                    print("Timeout beim Warten auf Microsoft SSO. Microsoft verlangt evtl. Eingabe!")
                    page.screenshot(path="downloads/ms_stuck.png")
                    do_ms_login()
                    page.screenshot(path="downloads/ms_after_second_login.png")
                    try:
                        page.wait_for_url("**/rec/share/**", timeout=30000)
                    except Exception as e:
                        print("Timeout nach fallback MS login:", e)
                        page.screenshot(path="downloads/ms_final_stuck.png")
        
        # Falls wir nicht automatisch beim Video gelandet sind, Ziel-URL nochmal aufrufen
        if "zoom.us/rec/share" not in page.url and "zoom.us/rec/play" not in page.url:
            print("-> SAML Flow beendet. Rufe Ziel-URL nochmal auf...")
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        else:
            print("-> SAML Flow hat uns automatisch zur Aufnahme weitergeleitet!")
        
        page.wait_for_timeout(5000)
        print("Neue URL:", page.url)
    
    # Falls Zoom eine Registrierung verlangt
    if "recording-register" in page.url or page.locator('button:has-text("Registrieren")').or_(page.locator('button:has-text("Register")')).is_visible():
        print("-> Zoom verlangt Aufzeichnungsregistrierung. Klicke auf 'Registrieren'...")
        reg_btn = page.locator('button:has-text("Registrieren")').or_(page.locator('button:has-text("Register")')).first
        if reg_btn.is_visible():
            reg_btn.click()
            page.wait_for_timeout(5000)

    dl_btn = page.locator('button:has-text("Download")').or_(page.locator('a:has-text("Download")')).or_(page.locator('button:has-text("Herunterladen")')).first
    has_dl = dl_btn.is_visible()
    print(f"Download-Button sichtbar: {'JA' if has_dl else 'Nein'}")
    print(f"Gefundene Media-Streams: {len(media_urls)}")
    
    page.screenshot(path="downloads/current_view.png")
    page.screenshot(path="downloads/zoom_test_result.png")
    
    if has_dl or media_urls or ("zoom.us/rec/" in page.url and "signin" not in page.url):
        print("\n=== TEST ERFOLGREICH: ZOOM-AUFZEICHNUNG IST ZUGÄNGLICH! ===")
    else:
        print("\n=== STATUS: Authentifizierung noch unvollständig (2FA erforderlich) ===")
        
    browser.close()
