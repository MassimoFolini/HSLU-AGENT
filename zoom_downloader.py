import os
import subprocess
import time
import pyotp
from playwright.sync_api import sync_playwright

class ZoomDownloader:
    def __init__(self, download_dir):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)
        self.storage_file = os.path.join(self.download_dir, "zoom_storage_state.json")
        self.email = os.environ.get('HSLU_MS_EMAIL') or os.environ.get('HSLU_USERNAME')
        self.password = os.environ.get('HSLU_MS_PASSWORD')
        ms_totp = os.environ.get('HSLU_MS_TOTP_SECRET', '').replace(' ', '')
        self.totp_secret = ms_totp or os.environ.get('HSLU_TOTP_SECRET', '').replace(' ', '')

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

                if "zoom.us/signin" in page.url:
                    print("   [Zoom] Zoom erfordert SSO-Bestätigung...")
                    cookie_btn = page.locator('button:has-text("Accept Cookies")').or_(page.locator('button[id="onetrust-accept-btn-handler"]')).first
                    if cookie_btn.is_visible():
                        cookie_btn.click()
                        page.wait_for_timeout(1000)
                    
                    sso_icon = page.get_by_text("SSO", exact=True).first
                    if sso_icon.is_visible():
                        sso_icon.click(force=True)
                        page.wait_for_timeout(3000)
                        try:
                            page.locator('input[name="domain"]').or_(page.locator('input[type="text"]')).first.fill("hslu")
                            page.wait_for_timeout(500)
                            page.locator('button[type="submit"]').or_(page.locator('button:has-text("Continue")')).first.click()
                            page.wait_for_timeout(8000)
                        except Exception:
                            pass
                        
                        if "microsoft" in page.url:
                            try:
                                page.wait_for_url("**/rec/share/**", timeout=20000)
                            except Exception:
                                self.do_ms_login(page, context)
                                try:
                                    page.wait_for_url("**/rec/share/**", timeout=30000)
                                except Exception:
                                    pass

                    if "zoom.us/rec/share" not in page.url and "zoom.us/rec/play" not in page.url:
                        page.goto(recording_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(5000)

                if "recording-register" in page.url or page.locator('button:has-text("Registrieren")').or_(page.locator('button:has-text("Register")')).is_visible():
                    print("   [Zoom] Registrierung verlangt. Klicke auf 'Registrieren'...")
                    reg_btn = page.locator('button:has-text("Registrieren")').or_(page.locator('button:has-text("Register")')).first
                    if reg_btn.is_visible():
                        reg_btn.click()
                        page.wait_for_timeout(5000)

                dl_btn = page.locator('button:has-text("Download")').or_(page.locator('a:has-text("Download")')).or_(page.locator('button:has-text("Herunterladen")')).first
                if dl_btn.is_visible():
                    print("   [Zoom] Download-Button gefunden, starte Download...")
                    with page.expect_download(timeout=60000) as download_info:
                        dl_btn.click()
                    download = download_info.value
                    download.save_as(dest_mp4)
                    print(f"   [Zoom] MP4 erfolgreich gespeichert: {dest_mp4}")
                elif found_media_url:
                    import requests
                    cookies = {c["name"]: c["value"] for c in context.cookies()}
                    with requests.get(found_media_url[0], cookies=cookies, stream=True, timeout=120) as r:
                        if r.status_code == 200:
                            with open(dest_mp4, "wb") as f:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk: f.write(chunk)
                            print(f"   [Zoom] MP4 gestreamt: {dest_mp4}")
                else:
                    cookie_path = os.path.join(self.download_dir, "zoom_cookies.txt")
                    cookies = context.cookies()
                    with open(cookie_path, "w", encoding="utf-8") as f:
                        f.write("# Netscape HTTP Cookie File\n")
                        for c in cookies:
                            domain = c.get("domain", "")
                            sub = "TRUE" if domain.startswith(".") else "FALSE"
                            secure = "TRUE" if c.get("secure", False) else "FALSE"
                            expires = int(c.get("expires", 0))
                            f.write(f"{domain}\t{sub}\t{c.get('path', '/')}\t{secure}\t{expires}\t{c.get('name', '')}\t{c.get('value', '')}\n")
                    
                    cmd = ["/opt/KiAgentHSLU/venv/bin/yt-dlp", "--cookies", cookie_path, "-o", dest_mp4, recording_url]
                    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if res.returncode == 0 and os.path.exists(dest_mp4):
                        print(f"   [Zoom] Per yt-dlp heruntergeladen: {dest_mp4}")
            except Exception as e:
                print(f"   [Zoom] Fehler: {e}")
            finally:
                browser.close()

        if os.path.exists(dest_mp4) and os.path.getsize(dest_mp4) > 1000:
            print(f"   [Audio] Erzeuge MP3 aus Zoom-Aufzeichnung...")
            subprocess.run(["ffmpeg", "-y", "-i", dest_mp4, "-vn", "-acodec", "libmp3lame", "-q:a", "5", dest_mp3],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return dest_mp3
        return None
