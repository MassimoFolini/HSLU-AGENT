import os
import re
import subprocess
import time
import pyotp
from playwright.sync_api import sync_playwright

class ZoomDownloader:
    def __init__(self, download_dir="downloads"):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        self.storage_file = os.path.join(self.download_dir, "zoom_storage_state.json")
        self.email = os.environ.get('HSLU_MS_EMAIL') or os.environ.get('HSLU_USERNAME')
        self.password = os.environ.get('HSLU_MS_PASSWORD')
        ms_totp = os.environ.get('HSLU_MS_TOTP_SECRET', '').replace(' ', '')
        self.totp_secret = ms_totp or os.environ.get('HSLU_TOTP_SECRET', '').replace(' ', '')

    @staticmethod
    def _accept_cookies(page):
        for sel in ('button:has-text("Cookies akzeptieren")', 'button:has-text("Accept Cookies")', '#onetrust-accept-btn-handler'):
            el = page.locator(sel).first
            if el.is_visible():
                el.click()
                page.wait_for_timeout(1000)
                return

    def is_configured(self):
        return bool(self.email and self.password)

    def do_ms_login(self, page, context):
        if "login.microsoftonline.com" in page.url:
            print("   [Zoom SSO] Microsoft Login-Maske aktiv.")
            # Email
            email_inp = page.locator('input[type="email"]').first
            if email_inp.is_visible():
                page.wait_for_timeout(1000)
                email_inp.fill("")
                page.wait_for_timeout(500)
                email_inp.click()
                email_inp.press_sequentially(self.email, delay=50)
                page.wait_for_timeout(1000)
                page.locator('input[type="submit"]').click()
                page.wait_for_timeout(3000)

            # Passwort
            pwd_sel = 'input[type="password"]'
            try:
                page.locator(pwd_sel).first.wait_for(timeout=5000)
                page.wait_for_timeout(1500)
                pwd_el = page.locator(pwd_sel).first
                pwd_el.fill("")
                page.wait_for_timeout(500)
                pwd_el.click()
                pwd_el.press_sequentially(self.password, delay=50)
                page.wait_for_timeout(1000)
                page.locator('input[type="submit"]').or_(page.locator('button[type="submit"]')).first.click()
                page.wait_for_timeout(4500)
            except Exception:
                pass

            # 3. 2FA Code falls verlangt
            code_input = page.locator('input[name="otc"]').or_(page.locator('input[type="tel"]')).or_(page.locator('input[id*="idTxtBx_SAOTCC_OTC"]')).first
            if code_input.is_visible():
                print("   [Zoom SSO] 2FA Authenticator-Code wird verlangt...")
                if self.totp_secret:
                    try:
                        totp = pyotp.TOTP(self.totp_secret.replace(" ", "").upper())
                        code = totp.now()
                        code_input.fill(code)
                        page.wait_for_timeout(500)
                        page.locator('input[type="submit"]').or_(page.locator('button:has-text("Verify")')).or_(page.locator('input[value="Verify"]')).first.click()
                        page.wait_for_timeout(4000)
                    except Exception as e:
                        print(f"   [Zoom SSO] Fehler bei TOTP: {e}")

            # 4. 'Angemeldet bleiben?' / 'Stay signed in?' Bestätigen
            stay_btn = page.locator('input[value="Yes"]').or_(page.locator('input[value="Ja"]')).first
            try:
                stay_btn.wait_for(timeout=10000)
                stay_btn.click()
                page.wait_for_timeout(3000)
            except Exception:
                pass

    def login_zoom_sso(self, page, context):
        try:
            page.goto("https://hslu.zoom.us/saml/login", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            self.do_ms_login(page, context)
            if "zoom.us" in page.url or "microsoft" not in page.url:
                try:
                    context.storage_state(path=self.storage_file)
                except Exception:
                    pass
                return True
            return True
        except Exception as e:
            print(f"   [Zoom SSO] Fehler beim Login: {e}")
            return False

    def download_recording(self, recording_url, output_dir, file_basename="Aufzeichnung"):
        os.makedirs(output_dir, exist_ok=True)
        dest_mp4 = os.path.join(output_dir, f"{file_basename}.mp4")
        dest_mp3 = os.path.join(output_dir, f"{file_basename}.mp3")
        dest_audio = os.path.join(output_dir, f"{file_basename}.m4a")

        if os.path.exists(dest_mp3) and os.path.getsize(dest_mp3) > 1000:
            print(f"   [Zoom] Bereits vorhanden: {os.path.basename(dest_mp3)}")
            return dest_mp3

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context_kwargs = {"viewport": {"width": 1280, "height": 800}, "accept_downloads": True}
            if os.path.exists(self.storage_file):
                try:
                    context_kwargs["storage_state"] = self.storage_file
                except Exception:
                    pass
            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            if self.is_configured():
                self.login_zoom_sso(page, context)

            found_media_url = []
            context.on("response", lambda r: found_media_url.append(r.url) if (
                any(x in r.url.lower() for x in [".mp4", "/rec/download", "/rec/play", "videoplayback"])
                and "zoom.us" in r.url
            ) else None)

            try:
                page.goto(recording_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)
                self._accept_cookies(page)

                if "zoom.us/signin" in page.url:
                    print("   [Zoom] Zoom erfordert Anmeldung, versuche SSO erneut...")
                    self.login_zoom_sso(page, context)
                    page.goto(recording_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(8000)
                    self._accept_cookies(page)

                # Registrierungsformular (Name/Mail sind vorausgefuellt)
                reg_btn = page.locator('button:has-text("Register")').or_(page.locator('button:has-text("Registrieren")')).first
                if reg_btn.is_visible():
                    print("   [Zoom] Registrierung verlangt. Klicke auf 'Registrieren'...")
                    reg_btn.click()
                    page.wait_for_timeout(8000)
                    self._accept_cookies(page)

                saved = []

                def on_download(d):
                    name = d.suggested_filename.lower()
                    try:
                        if name.endswith(".mp4") and "mp4" not in saved_kinds:
                            d.save_as(dest_mp4)
                            saved_kinds.add("mp4")
                        elif name.endswith((".m4a", ".mp3")) and "audio" not in saved_kinds:
                            d.save_as(dest_audio)
                            saved_kinds.add("audio")
                        else:
                            d.cancel()
                            return
                        saved.append(name)
                        print(f"   [Zoom] Gespeichert: {d.suggested_filename}")
                    except Exception as e:
                        print(f"   [Zoom] Download-Fehler: {e}")

                saved_kinds = set()
                page.on("download", on_download)

                dl_btn = page.get_by_text(re.compile(r"(Download|Herunterladen)\s*\(\d+")).first
                try:
                    dl_btn.wait_for(timeout=30000)
                except Exception:
                    dl_btn = page.locator('button:has-text("Herunterladen")').or_(page.locator('button:has-text("Download")')).first
                if dl_btn.is_visible():
                    print("   [Zoom] Download-Button gefunden, starte Download...")
                    dl_btn.click()
                    deadline = time.time() + 600
                    while time.time() < deadline and len(saved_kinds) < 2:
                        page.wait_for_timeout(2000)
                    # Dateien muessen vollstaendig auf der Platte liegen
                    page.wait_for_timeout(3000)
                else:
                    print("   [Zoom] Kein Download-Button gefunden. Aufzeichnung evtl. nicht freigegeben.")
                    page.screenshot(path=os.path.join(self.download_dir, "zoom_no_download.png"))
            except Exception as e:
                print(f"   [Zoom] Fehler: {e}")
            finally:
                browser.close()

        source = next((f for f in (dest_audio, dest_mp4) if os.path.exists(f) and os.path.getsize(f) > 1000), None)
        if source:
            print(f"   [Audio] Erzeuge MP3 aus {os.path.basename(source)}...")
            subprocess.run(["ffmpeg", "-y", "-i", source, "-vn", "-acodec", "libmp3lame", "-q:a", "5", dest_mp3],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(dest_audio):
                os.remove(dest_audio)  # nur MP4 + MP3 behalten
            if os.path.exists(dest_mp3) and os.path.getsize(dest_mp3) > 1000:
                return dest_mp3
        return None
