import os
import re
import json
import pyotp
import requests
from urllib.parse import urljoin, unquote
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BASE_URL = "https://elearning.hslu.ch/ilias/"

# ILIAS-Objekttypen, in die der Crawler hineingeht (Container)
CONTAINER_TYPES = {"fold", "grp", "cat", "mcst"}
# Externe Medien-Plattformen (keine direkten Dateien) -> nur als Referenz merken
STREAM_HINTS = ["panopto", "mediaspace", "xlti_", "/xlti/", "kaltura", "switch.tube", "tube.switch.ch"]


def safe_name(name):
    """Erlaubt Umlaute, entfernt nur Zeichen, die im Dateisystem/Drive Probleme machen."""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', '_', name or "").strip().strip('.')
    return name[:150] or "unbenannt"


def parse_ilias_object(href):
    """Liefert (typ, ref_id) fuer ILIAS-Links in allen bekannten Formaten, sonst (None, None)."""
    if not href:
        return None, None
    # ILIAS 10 Permalink: goto.php/fold/123
    m = re.search(r'goto\.php/([a-z]+)/(\d+)', href)
    if m:
        return m.group(1), m.group(2)
    # Alter Permalink: goto.php?target=fold_123 bzw. goto_elearning_fold_123.html
    m = re.search(r'target=([a-z]+)_(\d+)', href) or re.search(r'goto_[a-z]+_([a-z]+)_(\d+)', href)
    if m:
        return m.group(1), m.group(2)
    # ilias.php?...cmdClass=ilObjFileGUI...ref_id=123
    m = re.search(r'ref_id=(\d+)', href)
    if m:
        low = href.lower()
        if "ilobjmediacastgui" in low:
            item = re.search(r'item_id=(\d+)', href)
            if "cmd=downloaditem" in low and item:
                return "file", "mc" + item.group(1)      # Mediacast-Video: wie eine Datei behandeln
            if "cmd=showcontent" in low:
                return "mcst", m.group(1)                # Mediacast-Seite: wie ein Ordner behandeln
        if "illinkresourcehandlergui" in low or "calldirectlink" in low:
            return "webr", m.group(1)
        if "ilobjfilegui" in low or "cmd=sendfile" in low:
            return "file", m.group(1)
        if "ilobjfoldergui" in low:
            return "fold", m.group(1)
        if "ilobjgroupgui" in low:
            return "grp", m.group(1)
        if "ilobjcategorygui" in low:
            return "cat", m.group(1)
    return None, None


def filename_from_headers(headers, fallback):
    cd = headers.get("content-disposition", "") or headers.get("Content-Disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.IGNORECASE)
    if m:
        return safe_name(unquote(m.group(1)))
    m = re.search(r'filename="([^"]+)"', cd) or re.search(r'filename=([^;]+)', cd)
    if m:
        return safe_name(m.group(1).strip())
    return safe_name(fallback)


class HSLUScraper:
    def __init__(self, download_dir="downloads"):
        self.download_dir = os.path.abspath(download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        self.username = os.environ.get("HSLU_USERNAME")
        self.password = os.environ.get("HSLU_PASSWORD")
        self.totp_secret = os.environ.get("HSLU_TOTP_SECRET", "").replace(" ", "")
        self.http = None  # requests.Session mit den Browser-Cookies

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

    # ------------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------------
    def _build_http_session(self, context):
        """Uebernimmt die Login-Cookies des Browsers in eine requests-Session (fuer Streaming-Downloads)."""
        s = requests.Session()
        s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) HSLU-Study-Agent"
        for c in context.cookies():
            s.cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
        self.http = s

    def _collect_links(self, page):
        """Alle Links der Seite inkl. Info, ob sie in Navigation/Breadcrumbs liegen."""
        try:
            return page.evaluate("""() => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                href: a.href,
                text: (a.innerText || a.getAttribute('aria-label') || a.title || '').trim(),
                nav: !!a.closest('nav, header, footer, .breadcrumb, .il-breadcrumbs, .il-mainbar, .il-metabar, .il-maincontrols')
            }))""")
        except Exception:
            return []

    def _download_file(self, url, title, target_dir):
        """Streamt eine Datei auf die Platte. Ueberspringt sie, wenn sie lokal schon in gleicher Groesse existiert."""
        try:
            with self.http.get(url, stream=True, timeout=(20, 120), allow_redirects=True) as r:
                if r.status_code != 200:
                    print(f"   [FEHLER] HTTP {r.status_code}: {title}")
                    return None
                ctype = r.headers.get("content-type", "")
                if "text/html" in ctype:
                    print(f"   [SKIP] Keine Datei (HTML-Seite): {title}")
                    return None
                fname = filename_from_headers(r.headers, title)
                dest = os.path.join(target_dir, fname)
                size = int(r.headers.get("content-length", "0") or 0)
                if os.path.exists(dest) and size and os.path.getsize(dest) == size:
                    print(f"   [OK, vorhanden] {fname}")
                    return dest
                os.makedirs(target_dir, exist_ok=True)
                tmp = dest + ".part"
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                os.replace(tmp, dest)
                mb = os.path.getsize(dest) / (1024 * 1024)
                print(f"   [NEU] {fname} ({mb:.1f} MB)")
                
                # ZIP Entpacken
                if fname.lower().endswith(".zip"):
                    import zipfile
                    print(f"   [ZIP] Entpacke {fname}...")
                    try:
                        skip = {".venv", "venv", "__pycache__", ".ipynb_checkpoints", "node_modules", ".git", "site-packages"}
                        with zipfile.ZipFile(dest, 'r') as zip_ref:
                            members = [m for m in zip_ref.namelist() if not skip.intersection(m.replace("\\", "/").split("/"))]
                            zip_ref.extractall(target_dir, members=members)
                        os.remove(dest)
                        print(f"   [ZIP] Erfolgreich entpackt und geloescht.")
                        return None # Datei ist weg, stattdessen liegen nun die entpackten Dateien da
                    except Exception as e:
                        print(f"   [ZIP FEHLER] Konnte {fname} nicht entpacken: {e}")
                
                return dest
        except Exception as e:
            print(f"   [FEHLER] Download fehlgeschlagen ({title}): {e}")
            return None

    # ------------------------------------------------------------------
    # Crawler
    # ------------------------------------------------------------------
    def _crawl(self, page, url, path_parts, base_dir, state, depth=0):
        if depth > 8:
            return
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f"   [FEHLER] Seite nicht erreichbar: {e}")
            return

        local_dir = os.path.join(base_dir, *path_parts) if path_parts else base_dir
        links = self._collect_links(page)

        files, containers = {}, []
        for l in links:
            href, text = l["href"], l["text"]
            if not href or href.startswith("javascript"):
                continue
            otype, ref = parse_ilias_object(href)

            if otype == "file" and ref:
                if ref in state["seen_files"]:
                    continue
                entry = files.setdefault(ref, {"title": "", "href": href})
                # Bevorzugt den echten Download-Link (sendfile), Titel vom Text-Link
                if "sendfile" in href.lower():
                    entry["href"] = href
                if text and text.lower() != "download" and not entry["title"]:
                    entry["title"] = text
            elif otype in CONTAINER_TYPES and ref and not l["nav"]:
                if ref in state["visited"]:
                    continue
                containers.append((ref, text, href))
            elif (otype == "webr" or any(h in href.lower() for h in STREAM_HINTS)) and not l["nav"]:
                if href not in state["stream_urls"]:
                    state["stream_urls"].add(href)
                    state["videos"].append({"text": text, "url": href, "local_dir": local_dir})

        # Dateien dieser Ebene
        for ref, entry in files.items():
            state["seen_files"].add(ref)
            title = entry["title"] or f"datei_{ref}"
            dest = self._download_file(entry["href"], title, local_dir)
            if dest:
                state["files"].append(dest)

        # Unterordner rekursiv
        for ref, text, href in containers:
            if ref in state["visited"]:
                continue
            state["visited"].add(ref)
            name = safe_name(text) if text else f"ordner_{ref}"
            print(f" -> Ordner: {'/'.join(path_parts + [name])}")
            self._crawl(page, href, path_parts + [name], base_dir, state, depth + 1)

    @staticmethod
    def _resolve_weblink(page, url):
        """Folgt einem ILIAS-Weblink (calldirectlink) und liefert die Ziel-URL (z.B. Zoom-Aufzeichnung mit Passcode)."""
        hits = []

        def on_resp(r):
            if r.request.is_navigation_request() and r.status < 400 and "elearning.hslu.ch" not in r.url:
                hits.append(r.url)

        page.on("response", on_resp)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
        except Exception as e:
            print(f"   [Weblink] Aufloesen fehlgeschlagen: {e}")
        finally:
            page.remove_listener("response", on_resp)
        for h in hits:
            if "zoom.us/rec/share" in h or "zoom.us/rec/play" in h:
                return h
        return hits[0] if hits else None

    def _capture_module_description(self, page, course_url):
        """Text der Kursseite + (falls vorhanden) Info-Reiter als Modulbeschreibung."""
        parts = []
        try:
            page.goto(course_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            parts.append(page.locator('main').first.inner_text())
        except Exception:
            pass
        try:
            info_tab = page.get_by_role("link", name="Info", exact=True).first
            if info_tab.count() > 0 and info_tab.is_visible():
                info_tab.click()
                page.wait_for_timeout(1500)
                parts.append("\n\n## Info\n\n" + page.locator('main').first.inner_text())
        except Exception:
            pass
        return "\n".join(p for p in parts if p).strip()

    def scrape_single_course(self, page, course, week_dir):
        """Scannt einen Kurs rekursiv und spiegelt die Ordnerstruktur lokal."""
        course_title = course["title"]
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', course_title.split('.')[1] if '.' in course_title else course_title)
        course_dir = os.path.join(week_dir, clean_name)
        files_dir = os.path.join(course_dir, "Unterlagen")
        os.makedirs(files_dir, exist_ok=True)

        print(f"\n[Scraping] Betrete Kurs: {course_title}")
        _, course_ref = parse_ilias_object(course["url"])
        state = {
            "visited": {course_ref} if course_ref else set(),
            "seen_files": set(),
            "stream_urls": set(),
            "files": [],
            "videos": [],
        }
        self._crawl(page, course["url"], [], files_dir, state)

        for v in state["videos"]:
            v["resolved_url"] = self._resolve_weblink(page, v["url"])
            print(f"   [Stream] {v['text'] or 'Weblink'} -> {(v['resolved_url'] or 'nicht aufloesbar')[:90]}")

        description = self._capture_module_description(page, course["url"])
        desc_path = os.path.join(course_dir, "Modulbeschreibung.md")
        with open(desc_path, "w", encoding="utf-8") as f:
            f.write(f"# Modulbeschreibung: {course_title}\n\n{description}\n")

        print(f" -> Kurs '{clean_name}': {len(state['files'])} Dateien lokal, "
              f"{len(state['visited']) - 1} Ordner, {len(state['videos'])} externe Streams.")
        return {
            "title": course_title,
            "clean_name": clean_name,
            "dir": course_dir,
            "files": state["files"],
            "videos": state["videos"],
            "text": description,
            "description_file": desc_path,
        }

    def login_and_download(self, week_identifier):
        """Hauptmethode für das wöchentliche Scraping aller Fächer."""
        print(f"Starte Scraping für: {week_identifier}")
        week_dir = os.path.join(self.download_dir, week_identifier)
        os.makedirs(week_dir, exist_ok=True)

        results = {"courses_data": [], "todos": []}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True, viewport={"width": 1280, "height": 800})
            page = context.new_page()

            # 1. Login
            self.login(page)
            self._build_http_session(context)

            # 2. Belegte Module auslesen
            courses = self.get_enrolled_courses(page)
            print(f"\nGefundene aktive Kurse ({len(courses)}):")
            for c in courses:
                print(f" - {c['title']}")

            # 3. To-Dos auslesen
            todo_elements = page.locator('.il-block-todo, div:has-text("Abgabe zur Übungseinheit")').all()
            for td in todo_elements:
                try:
                    text = td.inner_text().strip()
                    if text and text not in results["todos"]:
                        results["todos"].append(text)
                except Exception:
                    pass

            # 4. Jeden Kurs einzeln scrapen
            for course in courses:
                try:
                    results["courses_data"].append(self.scrape_single_course(page, course, week_dir))
                except Exception as e:
                    print(f"Fehler beim Scrapen von {course['title']}: {e}")

            # 5. Cookies exportieren (Netscape-Format, z.B. fuer yt-dlp)
            cookie_path = os.path.join(self.download_dir, "cookies.txt")
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                for c in context.cookies():
                    domain = c.get("domain", "")
                    sub = "TRUE" if domain.startswith(".") else "FALSE"
                    secure = "TRUE" if c.get("secure", False) else "FALSE"
                    expires = int(c.get("expires", 0))
                    if expires < 0:
                        expires = 0
                    f.write(f"{domain}\t{sub}\t{c.get('path', '/')}\t{secure}\t{expires}\t{c.get('name', '')}\t{c.get('value', '')}\n")
            results["cookie_file"] = cookie_path
            browser.close()

        return results
