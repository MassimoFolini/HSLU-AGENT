import os
import time
import re
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
                    if current_semester_only and not ("H26" in title or "H26" in href):
                        continue
                    courses.append({"title": title, "url": href})
            except Exception:
                pass
        return courses

    def scrape_single_course(self, page, course, week_dir, sync_state):
        """Scannt einen einzelnen Kurs nach Unterlagen, PDFs und Videos und lädt diese herunter."""
        course_title = course["title"]
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', course_title.split('.')[1] if '.' in course_title else course_title)
        course_dir = os.path.join(week_dir, clean_name)
        files_dir = os.path.join(course_dir, "unterlagen")
        os.makedirs(files_dir, exist_ok=True)
        
        print(f"\n[Scraping] Betrete Kurs: {course_title}")
        page.goto(course["url"], wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        
        # 1. Textinhalte der Kursseite erfassen
        course_text = ""
        try:
            course_text = page.locator('main').first.inner_text()
        except Exception:
            pass
            
        downloaded_files = []
        video_links = []
        
        # 2. Suche nach Videos / Streams (Panopto, Zoom, MP4)
        all_links = page.locator('a').all()
        for l in all_links:
            try:
                href = l.get_attribute("href") or ""
                text = l.inner_text().strip()
                if any(v in href.lower() for v in ["panopto", "zoom.us", "mediaspace", ".mp4", ".m4a"]) or any(v in text.lower() for v in ["aufzeichnung", "aufnahme", "recording", "video"]):
                    video_links.append({"text": text, "url": href})
            except Exception:
                pass
                
        # 3. Suche und navigiere in Unterlagen-Ordner (z.B. Modulunterlagen, Vorlesungen, Inputs)
        subfolder_candidates = page.locator('a:has-text("Modulunterlagen"), a:has-text("Course Documents"), a:has-text("Inputs"), a:has-text("Vorlesung"), a:has-text("Folien"), a:has-text("Unterlagen"), a:has-text("Material")').all()
        target_folder_urls = []
        for sf in subfolder_candidates:
            try:
                h = sf.get_attribute("href")
                if h and h not in target_folder_urls and "goto.php" in h:
                    target_folder_urls.append(h)
            except Exception:
                pass

        # 4. Dateien auf der Hauptseite herunterladen
        self._download_files_on_page(page, files_dir, downloaded_files, clean_name, sync_state)

        # 5. In Unterordner gehen und dort ebenfalls herunterladen
        # Alle identifizierten Ordner abscannen (anstatt nur 3), um sicher alles zu haben
        for folder_url in target_folder_urls: 
            try:
                print(f" -> Öffne Kursordner...")
                page.goto(folder_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                self._download_files_on_page(page, files_dir, downloaded_files, clean_name, sync_state)
            except Exception as e:
                print(f" -> Fehler beim Öffnen des Ordners: {e}")

        print(f" -> Kurs '{clean_name}': {len(downloaded_files)} NEUE Unterlagen heruntergeladen, {len(video_links)} Video-Referenzen gefunden.")
        
        return {
            "title": course_title,
            "clean_name": clean_name,
            "dir": course_dir,
            "files": downloaded_files,
            "videos": video_links,
            "text": course_text
        }

    def _load_sync_state(self):
        state_file = os.path.join(self.download_dir, "sync_state.json")
        if os.path.exists(state_file):
            import json
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_sync_state(self, state):
        state_file = os.path.join(self.download_dir, "sync_state.json")
        import json
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)

    def _download_files_on_page(self, page, target_dir, downloaded_files, course_id, sync_state):
        """Sucht nach Dateien auf der aktuellen Seite und lädt sie herunter, wenn sie neu sind."""
        file_locators = page.locator('a[href*="goto.php/file/"], a[href*="target=file_"], a[href*="cmd=download"], a[href*="cmd=sendfile"], a[href*="ilObjFileGUI"], a[href*=".pdf"], a[href*=".pptx"], a[href*=".zip"], a[href*=".docx"]').all()
        if course_id not in sync_state:
            sync_state[course_id] = []
            
        new_files_this_page = []
        for fl in file_locators:
            try:
                fname = fl.inner_text().strip().replace('\n', ' ')
                href = fl.get_attribute("href")
                if not href:
                    continue
                    
                file_id = registry.generate_id(href, fname)
                if not registry.needs_processing(course_id, file_id) or any(fname in existing for existing in downloaded_files):
                    continue
                registry.register_item(course_id, file_id, "pdf", fname, href)
                    
                print(f"   [NEU] Lade herunter: {fname[:40]}...")
                
                # Datei direkt über den Browser-Kontext als Stream/Buffer abrufen (verhindert Inline-PDF-Probleme)
                response = page.context.request.get(href)
                if response.ok:
                    # Versuche einen vernünftigen Dateinamen zu finden
                    content_disp = response.headers.get('content-disposition', '')
                    import re
                    file_name_match = re.search(r'filename="([^"]+)"', content_disp)
                    if file_name_match:
                        safe_filename = file_name_match.group(1)
                    else:
                        safe_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', fname)
                        if not safe_filename.lower().endswith(('.pdf', '.zip', '.pptx', '.docx', '.xlsx')):
                            safe_filename += '.pdf' # Fallback
                            
                    dest_path = os.path.join(target_dir, safe_filename)
                    with open(dest_path, 'wb') as f:
                        f.write(response.body())
                        
                    downloaded_files.append(dest_path)
                    # registry.mark_processed is called in main.py after processing, but we can mark it downloaded here
                    sync_state[course_id].append(file_id)
                    new_files_this_page.append(dest_path)
                    print(f"   [OK] Gespeichert: {safe_filename}")
                else:
                    print(f"   [FEHLER] HTTP {response.status} bei {href}")
            except Exception as e:
                print(f"   [FEHLER] Konnte nicht herunterladen.")
        return new_files_this_page

    def _crawl_folder_recursive(self, page, current_url, current_path, base_dir, downloaded_files, video_links, sync_state, course_id, visited):
        """Kriecht rekursiv durch ILIAS-Ordner und ÃƒÂ¼bernimmt die exakte Struktur!"""
        if current_url in visited:
            return
        visited.add(current_url)
        
        try:
            page.goto(current_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            try:
                page.screenshot(path="downloads/current_view.png")
            except:
                pass
        except Exception:
            return

        # 1. Lokalen Ordner erstellen
        current_local_dir = os.path.join(base_dir, *current_path) if current_path else base_dir
        os.makedirs(current_local_dir, exist_ok=True)
        
        # 2. Dateien herunterladen in diesen spezifischen Unterordner
        self._download_files_on_page(page, current_local_dir, downloaded_files, course_id, sync_state)
        
        # NEU: 2.5 Videos/Streams auf dieser Ebene erfassen!
        all_links = page.locator('a').all()
        for l in all_links:
            try:
                href = l.get_attribute("href") or ""
                text = l.inner_text().strip()
                if any(v in href.lower() for v in ["panopto", "zoom.us", "mediaspace", ".mp4", ".m4a"]) or any(v in text.lower() for v in ["aufzeichnung", "aufnahme", "recording", "video"]):
                    if not any(v["url"] == href for v in video_links):
                        video_links.append({"text": text, "url": href})
                        v_id = registry.generate_id(href, text)
                        registry.register_item(course_id, v_id, "video", text, href)
            except Exception:
                pass
        
        # 3. Unterordner finden und rekursiv besuchen
        folder_links = page.locator('a[href*="target=fold_"], a[href*="/fold/"], a.il_ContainerItemTitle[href*="goto.php"]').all()
        subfolders = []
        for fl in folder_links:
            try:
                href = fl.get_attribute("href")
                name = fl.inner_text().strip()
                if href and name and ("target=fold_" in href or "/fold/" in href):
                    clean_folder_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', name).strip()
                    subfolders.append((clean_folder_name, href))
            except:
                pass
                
        # Deduplizieren und rekursiv aufrufen
        seen_hrefs = set()
        for folder_name, href in subfolders:
            if href not in seen_hrefs:
                seen_hrefs.add(href)
                print(f" -> Betrete Unterordner: {'/'.join(current_path + [folder_name])}")
                self._crawl_folder_recursive(
                    page, href, current_path + [folder_name], 
                    base_dir, downloaded_files, video_links, sync_state, course_id, visited
                )

    def scrape_single_course(self, page, course, week_dir, sync_state):
        """Scannt einen einzelnen Kurs rekursiv und übernimmt die Ordnerstruktur."""
        course_title = course["title"]
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', course_title.split('.')[1] if '.' in course_title else course_title)
        course_dir = os.path.join(week_dir, clean_name)
        files_dir = os.path.join(course_dir, "Unterlagen")
        os.makedirs(files_dir, exist_ok=True)
        
        print(f"\n[Scraping] Betrete Kurs: {course_title}")
        page.goto(course["url"], wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        try:
            page.screenshot(path="downloads/current_view.png")
        except:
            pass
            
        course_text = ""
        try:
            course_text = page.locator('main').first.inner_text()
        except Exception:
            pass
            
        downloaded_files = []
        video_links = []
        
        # 1. Videos / Streams erfassen (bleibt flach)
        all_links = page.locator('a').all()
        for l in all_links:
            try:
                href = l.get_attribute("href") or ""
                text = l.inner_text().strip()
                if any(v in href.lower() for v in ["panopto", "zoom.us", "mediaspace", ".mp4", ".m4a"]) or any(v in text.lower() for v in ["aufzeichnung", "aufnahme", "recording", "video"]):
                    video_links.append({"text": text, "url": href})
            except Exception:
                pass
                
        # 2. Rekursives Crawling für Ordnerstruktur starten!
        visited = set()
        self._crawl_folder_recursive(
            page=page, 
            current_url=course["url"], 
            current_path=[], 
            base_dir=files_dir, 
            downloaded_files=downloaded_files, 
            video_links=video_links,
            sync_state=sync_state, 
            course_id=clean_name, 
            visited=visited
        )

        print(f" -> Kurs '{clean_name}': {len(downloaded_files)} NEUE Unterlagen heruntergeladen, Struktur übernommen.")
        
        return {
            "title": course_title,
            "clean_name": clean_name,
            "dir": course_dir,
            "files": downloaded_files,
            "videos": video_links,
            "text": course_text
        }

    def login_and_download(self, week_identifier):
        """Hauptmethode für das wöchentliche Scraping aller Fächer."""
        print(f"Starte wöchentliches Scraping für: {week_identifier}")
        week_dir = os.path.join(self.download_dir, week_identifier)
        os.makedirs(week_dir, exist_ok=True)
        
        sync_state = self._load_sync_state()
        
        results = {
            "courses_data": [],
            "todos": []
        }

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            # 1. Login
            self.login(page)
            try:
                page.screenshot(path="downloads/current_view.png")
            except:
                pass

            # 2. Belegte Module auslesen
            courses = self.get_enrolled_courses(page)
            print(f"\nGefundene aktive Kurse ({len(courses)}):")
            for c in courses:
                print(f" - {c['title']}")

            # 3. To-Dos auslesen
            todo_elements = page.locator('.il-block-todo, div:has-text("Abgabe zur Übungseinheit")').all()
            for td in todo_elements:
                text = td.inner_text().strip()
                if text and text not in results["todos"]:
                    results["todos"].append(text)

            # 4. JEDEN Kurs einzeln scrapen & Unterlagen herunterladen!
            for course in courses:
                try:
                    c_data = self.scrape_single_course(page, course, week_dir, sync_state)
                    results["courses_data"].append(c_data)
                except Exception as e:
                    print(f"Fehler beim Scrapen von {course['title']}: {e}")

            # 5. Cookies exportieren fÃƒÂ¼r yt-dlp (Panopto/Zoom Downloads)
            cookies = context.cookies()
            cookie_path = os.path.join(self.download_dir, "cookies.txt")
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\\n")
                for c in cookies:
                    domain = c.get("domain", "")
                    include_subdomain = "TRUE" if domain.startswith(".") else "FALSE"
                    path = c.get("path", "/")
                    secure = "TRUE" if c.get("secure", False) else "FALSE"
                    expires = int(c.get("expires", 0))
                    if expires == -1: expires = 0
                    name = c.get("name", "")
                    value = c.get("value", "")
                    f.write(f"{domain}\\t{include_subdomain}\\t{path}\\t{secure}\\t{expires}\\t{name}\\t{value}\\n")
            
            results["cookie_file"] = cookie_path
            browser.close()
            
        self._save_sync_state(sync_state)
        return results



