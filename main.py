import os
import json
import subprocess
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv
from pypdf import PdfReader

from scraper import HSLUScraper
from google_integration import GoogleWorkspace

load_dotenv()

# KI (Gemini) nur wenn ausdruecklich eingeschaltet: AI_ENABLED=1 in der .env
AI_ENABLED = os.environ.get("AI_ENABLED", "0").strip() == "1"

DRIVE_SYNC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drive_sync.json")
VIDEO_EXTS = (".mp4", ".m4v", ".mov", ".mkv", ".webm")


def extract_pdf_text(pdf_path, max_pages=30):
    """Liest Text aus einer PDF-Datei für die KI-Analyse aus."""
    try:
        reader = PdfReader(pdf_path)
        text = []
        for i, page in enumerate(reader.pages[:max_pages]):
            p_text = page.extract_text()
            if p_text:
                text.append(f"--- Seite {i+1} ---\n{p_text}")
        return "\n".join(text)
    except Exception as e:
        print(f"   [PDF-Parser] Hinweis zu {os.path.basename(pdf_path)}: {e}")
        return ""


def clean_subject_name(raw_title):
    """Erzeugt einen sauberen, lesbaren Fachnamen (z.B. 'Datenbanksysteme')."""
    mapping = {
        "DBS": "Datenbanksysteme",
        "ASTAT": "Applied_Statistics",
        "KRR": "Logical_Reasoning_in_AI",
        "VSK": "Verteilte_Systeme",
        "PREN1": "Produktentwicklung_PREN1",
        "AEDCIT": "Academic_English"
    }
    for code, name in mapping.items():
        if code in raw_title:
            return name
    parts = raw_title.split(".")
    name = parts[1] if len(parts) > 1 else raw_title
    return name.replace(" ", "_").replace("/", "_")


def video_to_mp3(video_path):
    """Extrahiert die Tonspur als MP3 (lokal mit ffmpeg, kostenlos)."""
    mp3_path = os.path.splitext(video_path)[0] + ".mp3"
    if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
        return mp3_path
    print(f"   [Audio] Erzeuge MP3 aus {os.path.basename(video_path)} ...")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "5", mp3_path],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return mp3_path
    except Exception as e:
        print(f"   [Audio] FEHLER bei ffmpeg: {e}")
        return None


class DriveSync:
    """Spiegelt einen lokalen Ordner nach Google Drive. Merkt sich, was schon oben ist."""

    def __init__(self, gw):
        self.gw = gw
        self.folder_cache = {}
        try:
            with open(DRIVE_SYNC_FILE, "r", encoding="utf-8") as f:
                self.state = json.load(f)
        except Exception:
            self.state = {}

    def save(self):
        with open(DRIVE_SYNC_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def folder(self, name, parent_id):
        key = (parent_id, name)
        if key not in self.folder_cache:
            self.folder_cache[key] = self.gw.get_or_create_folder(name, parent_id=parent_id)
        return self.folder_cache[key]

    def folder_path(self, root_id, rel_dir):
        current = root_id
        if rel_dir and rel_dir != ".":
            for part in rel_dir.replace("\\", "/").split("/"):
                if part:
                    current = self.folder(part, current)
        return current

    def upload(self, local_path, parent_id, key, as_google_doc=False, force=False):
        size = os.path.getsize(local_path)
        known = self.state.get(key)
        if not force and known and known.get("size") == size:
            return False
        file_id = self.gw.upload_file(local_path, parent_id, as_google_doc=as_google_doc)
        if file_id:
            self.state[key] = {"size": size, "id": file_id, "uploaded": datetime.now().isoformat()}
            self.save()
            return True
        return False


def sync_course_to_drive(sync, course, subject_name):
    """Laedt alle lokalen Unterlagen eines Fachs nach Drive: <Fach>/Unterlagen/<ILIAS-Struktur>."""
    subject_id = sync.folder(subject_name, None)
    unterlagen_id = sync.folder("Unterlagen", subject_id)
    local_root = os.path.join(course["dir"], "Unterlagen")
    uploaded = skipped = 0

    for dirpath, _, filenames in os.walk(local_root):
        rel_dir = os.path.relpath(dirpath, local_root)
        for fn in sorted(filenames):
            if fn.endswith(".part"):
                continue
            local_path = os.path.join(dirpath, fn)
            low = fn.lower()

            # Videos: MP4 und MP3 hochladen
            if low.endswith(VIDEO_EXTS):
                mp3 = video_to_mp3(local_path)
                if mp3:
                    key_mp3 = f"{subject_name}/{os.path.relpath(mp3, local_root)}"
                    target_mp3 = sync.folder_path(unterlagen_id, rel_dir)
                    if sync.upload(mp3, target_mp3, key_mp3):
                        uploaded += 1
                    else:
                        skipped += 1
                # KEIN continue, damit das Video (.mp4) unten normal hochgeladen wird!
            # MP3, die aus einem Video erzeugt wurde, wurde oben schon behandelt
            if low.endswith(".mp3") and any(os.path.exists(os.path.splitext(local_path)[0] + e) for e in VIDEO_EXTS):
                continue

            key = f"{subject_name}/{os.path.relpath(local_path, local_root)}"
            target = sync.folder_path(unterlagen_id, rel_dir)
            try:
                if sync.upload(local_path, target, key):
                    uploaded += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"   [Drive] FEHLER bei {fn}: {e}")

    # Modulbeschreibung: eigenes Google Doc, wird bei jedem Lauf ueberschrieben
    desc = course.get("description_file")
    if desc and os.path.exists(desc):
        mb_folder = sync.folder("Modulbeschreibung", unterlagen_id)
        sync.upload(desc, mb_folder, f"{subject_name}/__Modulbeschreibung__", as_google_doc=True, force=True)
        print(" -> [Drive] Modulbeschreibung aktualisiert.")

    print(f" -> [Drive] {uploaded} Dateien neu hochgeladen, {skipped} bereits aktuell.")
    return unterlagen_id


def weekly_job(force_week_str=None):
    now = datetime.now()
    week_str = force_week_str or f"KW {now.strftime('%W')} ({now.strftime('%d.%m.%Y')})"

    print("\n" + "=" * 75)
    print(f"STARTE HSLU-STUDIENASSISTENT: {week_str}")
    print(f"KI-Funktionen (Gemini): {'AN' if AI_ENABLED else 'AUS (nur Download + Drive-Sync, keine Kosten)'}")
    print(f"Zeitstempel: {now.strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 75)

    scraper = HSLUScraper()
    gworkspace = None
    try:
        gworkspace = GoogleWorkspace()
        print("[Google Drive] Verbindung erfolgreich hergestellt!")
    except Exception as e:
        print(f"[Google Drive] FEHLER: {e}")

    try:
        results = scraper.login_and_download(week_str.replace(" ", "_").replace("(", "").replace(")", ""))
    except Exception as e:
        print(f"[Scraper] FEHLER, Durchlauf abgebrochen: {e}")
        return
    courses_data = results.get("courses_data", [])
    todos = results.get("todos", [])
    print(f"\n[Scraping fertig] {len(courses_data)} Kurse gescannt.")

    sync = DriveSync(gworkspace) if gworkspace else None
    llm = None
    if AI_ENABLED:
        from llm_processor import LLMProcessor
        llm = LLMProcessor()

    for c in courses_data:
        subject_name = clean_subject_name(c["title"])
        print("\n" + "=" * 60)
        print(f"FACH: {subject_name} ({c['title']}) | Dateien: {len(c.get('files', []))} | externe Streams: {len(c.get('videos', []))}")
        print("=" * 60)

        # Externe Streams / Zoom-Aufzeichnungen herunterladen (falls konfiguriert)
        if c.get("videos"):
            from zoom_downloader import ZoomDownloader
            from scraper import safe_name
            z_down = ZoomDownloader()
            if z_down.is_configured():
                for v in c["videos"]:
                    v_url = v.get("url", "")
                    v_text = v.get("text", "Aufzeichnung")
                    out_dir = v.get("local_dir") or os.path.join(c["dir"], "Unterlagen")
                    print(f"   [Zoom] Starte automatischen Download: {v_text}...")
                    mp3_path = z_down.download_recording(v_url, output_dir=out_dir, file_basename=safe_name(v_text))
                    if mp3_path:
                        print(f"   [Zoom] Erfolgreich gesichert: {os.path.basename(mp3_path)}")
            else:
                for v in c["videos"]:
                    print(f"   [Hinweis] Externer Stream (HSLU_MS_PASSWORD nicht gesetzt): {v.get('text') or ''} -> {v.get('url')}")

        unterlagen_id = None
        if sync:
            try:
                unterlagen_id = sync_course_to_drive(sync, c, subject_name)
            except Exception as e:
                print(f" -> [Drive] FEHLER beim Sync: {e}")

        # KI-Dossier nur wenn eingeschaltet
        if AI_ENABLED and llm:
            pdf_corpus = ""
            for pdf in c.get("files", []):
                if pdf.lower().endswith(".pdf"):
                    t = extract_pdf_text(pdf)
                    if t:
                        pdf_corpus += f"\n\n=== DOKUMENT: {os.path.basename(pdf)} ===\n{t}"
            todo_text = "\n".join(f"- {t}" for t in todos if subject_name.lower() in t.lower())
            source = f"Modul-Informationen:\n{c.get('text', '')[:4000]}\n\nUnterlagen:\n{pdf_corpus[:15000]}\n\nOffene Abgaben:\n{todo_text}"
            dossier = llm.generate_dossier(week_title=f"{subject_name} - {week_str}", transcript_text="",
                                           pdf_text_content=source, subject_code=c["title"])
            path = os.path.join(c["dir"], "Wochen-Dossier.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(dossier)
            if sync and unterlagen_id:
                gworkspace.upload_file(path, unterlagen_id, as_google_doc=True)
            time.sleep(15)  # Gemini-Ratenlimit

    print("\n" + "=" * 75)
    print(f"DURCHLAUF FÜR {week_str} BEENDET.")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    print("HSLU KI-Studienassistent ist aktiv.")
    print("Schedule: Jeden Sonntag um 18:00 Uhr automatisch.")
    schedule.every().sunday.at("18:00").do(weekly_job)
    print("Warteschleife aktiv. Drücke Strg + C zum Beenden.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("Beendet.")
