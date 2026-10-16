"""Drive-Eingang: eigene Aufnahmen ablegen, der Server macht Transkript, saubere Fassung und Dossier.

So benutzt du es:
  1. Lege eine Audio- oder Videodatei (mp3, mp4, m4a, wav ...) in Drive unter
        HSLU Agent/_Eingang/<Fach>/
     (die Fachordner legt dieses Skript beim ersten Lauf selbst an).
  2. Alle 15 Minuten prueft der Server den Eingang (systemd-Timer hslu-inbox.timer).
  3. Ergebnis im Drive, jeweils im Fachordner:
        Live-Aufnahmen/   MP3 und Rohtranskript (.txt)
        Dossiers/         Dossier (Google Doc), alle Dossiers des Fachs in einem Ordner
        Transkripte/      saubere Lesefassung (Google Doc)
     Die Originaldatei wandert nach _Eingang/_Verarbeitet.

Manuell: python maintenance/process_inbox.py          (aus dem Projektroot)
Stille Aufnahmen (z. B. Mikrofon statt Systemton aufgenommen) werden abgelehnt und bleiben im Eingang liegen.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import subprocess
import time
import traceback
import warnings
from datetime import datetime

from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE, "inbox_state.json")
OUT_ROOT = os.path.join(BASE, "downloads", "live_recordings")   # 'live_recordings' wird von den Skripten als Vorlesung erkannt
INBOX, DONE = "_Eingang", "_Verarbeitet"
COURSE_TITLES = ["I.BA_ASTAT_MM.H26", "I.BA_AEDCIT.H2601", "I.BA_DBS.H2601", "I.BA_KRR.H2601", "I.BA_VSK_MM.H2601", "TA.BA_PREN1.H2601"]
MEDIA_Q = "(mimeType contains 'audio/' or mimeType contains 'video/')"
MIN_SIZE = 50_000          # kleinere Dateien sind kein Vorlesungston
MAX_ATTEMPTS = 3


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def safe(name):
    return re.sub(r"[^\w.\- ]+", "_", name).strip(" ._") or "aufnahme"


def children(gw, parent_id, extra=""):
    q = f"'{parent_id}' in parents and trashed = false" + (f" and {extra}" if extra else "")
    out, page = [], None
    while True:
        res = gw.drive_service.files().list(q=q, fields="nextPageToken, files(id,name,mimeType,size,createdTime,modifiedTime)",
                                            pageSize=200, pageToken=page).execute()
        out += res.get("files", [])
        page = res.get("nextPageToken")
        if not page:
            return out


def ensure_structure(gw, subjects):
    inbox = gw.get_or_create_folder(INBOX)
    for s in subjects:
        gw.get_or_create_folder(s, parent_id=inbox)
    done = gw.get_or_create_folder(DONE, parent_id=inbox)
    return inbox, done


def download(gw, file_id, dest):
    from googleapiclient.http import MediaIoBaseDownload
    req = gw.drive_service.files().get_media(fileId=file_id)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        dl = MediaIoBaseDownload(f, req, chunksize=32 * 1024 * 1024)
        finished = False
        while not finished:
            _, finished = dl.next_chunk()
    os.replace(tmp, dest)


def to_mp3(src, dst):
    if src.lower().endswith(".mp3"):
        os.replace(src, dst)
        return
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "32000",
                    "-c:a", "libmp3lame", "-b:a", "64k", dst], check=True)
    os.remove(src)


def process_file(gw, f, subject, sub_id, done_id):
    stem = safe(os.path.splitext(f["name"])[0])
    base = f"{f['createdTime'][:10]}_{stem}"
    out_dir = os.path.join(OUT_ROOT, subject)
    os.makedirs(out_dir, exist_ok=True)
    mp3 = os.path.join(out_dir, base + ".mp3")
    txt = os.path.join(out_dir, base + ".txt")
    clean_md = os.path.join(out_dir, f"Transkript_{base}.md")
    dossier_md = os.path.join(out_dir, f"Dossier_{base}.md")

    if not os.path.exists(mp3):
        raw = os.path.join(out_dir, base + os.path.splitext(f["name"])[1].lower())
        print(f"   Lade herunter: {f['name']} ({int(f.get('size', 0)) / 1e6:.0f} MB)", flush=True)
        download(gw, f["id"], raw)
        print("   Wandle in MP3 um ...", flush=True)
        to_mp3(raw, mp3)

    from transcriber import Transcriber
    transcript = Transcriber().transcribe(mp3)          # wirft bei Stille
    if len(transcript.split()) < 30:
        raise RuntimeError("Transkript praktisch leer, vermutlich keine Sprache")

    import google.generativeai as genai
    import clean_transcripts
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel(os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-3.5-flash"))
    if not (os.path.exists(clean_md) and os.path.getsize(clean_md) > 500):
        clean_transcripts.build_clean_doc(model, txt, subject, base, clean_md)

    from llm_processor import LLMProcessor
    if not (os.path.exists(dossier_md) and os.path.getsize(dossier_md) > 500):
        dossier = LLMProcessor().generate_dossier(week_title=f"{subject} - {stem}", transcript_text=transcript,
                                                  pdf_text_content="", subject_code=subject)
        if dossier.startswith("# Dossier konnte nicht erstellt werden"):
            raise RuntimeError(dossier[:200])
        with open(dossier_md, "w", encoding="utf-8") as fh:
            fh.write(dossier)

    subject_folder = gw.get_or_create_folder(subject)
    rec_folder = gw.get_or_create_folder("Live-Aufnahmen", parent_id=subject_folder)
    tr_folder = gw.get_or_create_folder("Transkripte", parent_id=subject_folder)
    gw.upload_file(mp3, rec_folder, as_google_doc=False)
    gw.upload_file(txt, rec_folder, as_google_doc=False)
    gw.upload_file(dossier_md, gw.get_or_create_folder("Dossiers", parent_id=subject_folder), as_google_doc=True)
    gw.upload_file(clean_md, tr_folder, as_google_doc=True)

    gw.drive_service.files().update(fileId=f["id"], addParents=done_id, removeParents=sub_id, fields="id").execute()
    print(f"   Fertig: {f['name']} -> {subject}/Live-Aufnahmen und {subject}/Transkripte", flush=True)


def main():
    from google_integration import GoogleWorkspace
    from main import clean_subject_name
    gw = GoogleWorkspace()
    known = [clean_subject_name(t) for t in COURSE_TITLES]
    inbox, done = ensure_structure(gw, known)
    state = load_state()
    todo = 0
    for sub in children(gw, inbox, "mimeType = 'application/vnd.google-apps.folder'"):
        if sub["name"] == DONE:
            continue
        subject = safe(sub["name"])
        for f in children(gw, sub["id"], MEDIA_Q):
            if int(f.get("size", 0) or 0) < MIN_SIZE:
                continue
            st = state.get(f["id"], {})
            if st.get("status") == "fertig" or st.get("attempts", 0) >= MAX_ATTEMPTS or st.get("status") == "still":
                continue
            if st.get("modified") not in (None, f["modifiedTime"]):
                st = {}                                   # Datei wurde ersetzt: neu versuchen
            todo += 1
            print(f"\n=== {subject}: {f['name']}", flush=True)
            try:
                process_file(gw, f, subject, sub["id"], done)
                state[f["id"]] = {"status": "fertig", "name": f["name"], "subject": subject, "at": datetime.now().isoformat()}
            except RuntimeError as e:
                still = "still" in str(e).lower()
                print(f"   ABGELEHNT: {e}", flush=True)
                state[f["id"]] = {"status": "still" if still else "fehler", "attempts": st.get("attempts", 0) + (3 if still else 1),
                                  "error": str(e)[:300], "modified": f["modifiedTime"], "name": f["name"]}
            except Exception as e:
                traceback.print_exc()
                state[f["id"]] = {"status": "fehler", "attempts": st.get("attempts", 0) + 1,
                                  "error": str(e)[:300], "modified": f["modifiedTime"], "name": f["name"]}
            save_state(state)
    print(f"\nEingang geprueft: {todo} Datei(en) bearbeitet.", flush=True)


if __name__ == "__main__":
    main()
