"""Drive-Eingang: eigene Aufnahmen ablegen, der Server macht Transkript, saubere Fassung und Dossier.

So benutzt du es:
  1. Lege eine Audio- oder Videodatei (mp3, mp4, m4a, wav ...) oder ein fertiges Texttranskript (.txt, .vtt, .md,
     z. B. der Zoom-Download "Herunterladen") in Drive unter
        HSLU Agent/_Eingang/<Fach>/SWnn/
     SWnn ist die Schulwoche (SW01 = Woche ab 14.09.2026). Die Fach- und Wochenordner legt dieses Skript selbst an.
     Dateien direkt im Fachordner gehen auch: die Woche kommt dann aus dem Dateinamen oder dem Datum.
  2. Alle 15 Minuten prueft der Server den Eingang (systemd-Timer hslu-inbox.timer).
  3. Ergebnis im Drive, jeweils im Fachordner (nur Text, keine Audio- oder Videodateien):
        Transkripte/      Rohtranskript mit Zeitmarken (.txt) und saubere Lesefassung (Google Doc)
        Dossiers/         Dossier (Google Doc), alle Dossiers des Fachs in einem Ordner
     Audio/Video wandert nach dem Transkribieren in den Drive-Papierkorb und wird lokal geloescht.
     Texttranskripte wandern nach _Eingang/_Verarbeitet.
  Zusaetzlich: fertige Aufnahmen des Zoom-Rekorders (/opt/zoomrec/recordings) laufen denselben Weg, die MP3 wird danach geloescht.

Manuell: python maintenance/process_inbox.py          (aus dem Projektroot)
Stille Aufnahmen (z. B. Mikrofon statt Systemton aufgenommen) werden abgelehnt und bleiben im Eingang liegen.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import shutil
import subprocess
import time
import traceback
import warnings
from datetime import datetime

from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

import weeks

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE, "inbox_state.json")
OUT_ROOT = os.path.join(BASE, "downloads", "live_recordings")   # 'live_recordings' wird von den Skripten als Vorlesung erkannt
INBOX, DONE = "_Eingang", "_Verarbeitet"
COURSE_TITLES = ["I.BA_ASTAT_MM.H26", "I.BA_AEDCIT.H2601", "I.BA_DBS.H2601", "I.BA_KRR.H2601", "I.BA_VSK_MM.H2601", "TA.BA_PREN1.H2601"]
MEDIA_Q = ("(mimeType contains 'audio/' or mimeType contains 'video/' or mimeType = 'text/plain' "
           "or mimeType = 'text/markdown' or name contains '.vtt' or name contains '.txt' or name contains '.md')")
TEXT_EXT = (".txt", ".vtt", ".md")
MIN_SIZE = 50_000          # kleinere Dateien sind kein Vorlesungston
MIN_TEXT = 2_000           # kuerzere Texte sind kein Transkript
WEEK_FOLDERS = range(1, 15)
SEGMENT_SECONDS = 120      # Texttranskript wird in Abschnitte dieser Laenge gegliedert
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
        sid = gw.get_or_create_folder(s, parent_id=inbox)
        for wk in WEEK_FOLDERS:
            gw.get_or_create_folder(weeks.label(wk), parent_id=sid)
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


def is_text(f):
    return f["name"].lower().endswith(TEXT_EXT) or f.get("mimeType") in ("text/plain", "text/markdown")


def date_of(f):
    m = re.search(r"(20\d\d-\d\d-\d\d)", f["name"])
    return m.group(1) if m else f["createdTime"][:10]


def week_of(f, folder_week):
    """Schulwoche: Wochenordner, sonst Name, sonst Datum im Namen, sonst Upload-Datum."""
    return (folder_week or weeks.week_of_text(f["name"]) or weeks.week_of_file(f["name"])
            or weeks.week_of_date(datetime.fromisoformat(f["createdTime"][:10])))


def zoom_to_raw(text):
    """Zoom-Transkript ("HH:MM:SS --> HH:MM:SS" und "Sprecher: Text") in das Rohformat mit [HH:MM:SS]-Abschnitten."""
    out, seg_start, last_speaker, t = [], None, None, None
    time_re = re.compile(r"^(\d\d):(\d\d):(\d\d)\s*-->")
    for line in text.splitlines():
        line = line.strip()
        m = time_re.match(line)
        if m:
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            continue
        if not line:
            continue
        speaker, _, body = line.partition(": ")
        if not body:
            speaker, body = None, line
        if t is not None and (seg_start is None or t - seg_start >= SEGMENT_SECONDS):
            seg_start = t
            out.append(f"\n[{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}]")
            last_speaker = None
        if speaker and speaker != last_speaker:
            out.append(f"{speaker}: {body}")
            last_speaker = speaker
        else:
            out.append(body)
    return "\n".join(out).strip() + "\n"


def process_file(gw, f, subject, sub_id, done_id, folder_week=None):
    stem = safe(os.path.splitext(f["name"])[0])
    label = weeks.label(week_of(f, folder_week))
    base = f"{label}_{date_of(f)}_{stem}"
    out_dir = os.path.join(OUT_ROOT, subject, label)
    os.makedirs(out_dir, exist_ok=True)
    mp3 = os.path.join(out_dir, base + ".mp3")
    txt = os.path.join(out_dir, base + ".txt")

    text_input = is_text(f)
    if text_input:
        if not os.path.exists(txt):
            raw = os.path.join(out_dir, base + ".src" + os.path.splitext(f["name"])[1].lower())
            download(gw, f["id"], raw)
            with open(raw, "r", encoding="utf-8", errors="replace") as fh:
                raw_text = fh.read()
            os.remove(raw)
            with open(txt, "w", encoding="utf-8") as fh:
                fh.write(zoom_to_raw(raw_text) if "-->" in raw_text else raw_text)
        with open(txt, "r", encoding="utf-8") as fh:
            transcript = fh.read()
    else:
        if not os.path.exists(txt) and not os.path.exists(mp3):
            raw = os.path.join(out_dir, base + os.path.splitext(f["name"])[1].lower())
            print(f"   Lade herunter: {f['name']} ({int(f.get('size', 0)) / 1e6:.0f} MB)", flush=True)
            download(gw, f["id"], raw)
            print("   Wandle in MP3 um ...", flush=True)
            to_mp3(raw, mp3)
        transcript = transcribe_checked(mp3)
    publish(gw, subject, stem, base, out_dir, txt, transcript)
    if os.path.exists(mp3):
        os.remove(mp3)                                    # erst nach erfolgreichem Upload: nur der Text bleibt
    if text_input:
        gw.drive_service.files().update(fileId=f["id"], addParents=done_id, removeParents=sub_id, fields="id").execute()
    else:
        # Nur der Text wird gebraucht: Audio/Video in den Drive-Papierkorb (30 Tage wiederherstellbar)
        gw.drive_service.files().update(fileId=f["id"], body={"trashed": True}).execute()
    print(f"   Fertig: {f['name']} -> {subject}/Transkripte und {subject}/Dossiers", flush=True)


def transcribe_checked(mp3):
    """Transkribiert (Ergebnis .txt neben der MP3, dient auch als Cache fuer Wiederholungen)."""
    from transcriber import Transcriber
    transcript = Transcriber().transcribe(mp3)              # wirft bei Stille
    if len(transcript.split()) < 30:
        raise RuntimeError("Transkript praktisch leer, vermutlich keine Sprache")
    return transcript


def publish(gw, subject, stem, base, out_dir, txt, transcript):
    """Saubere Lesefassung und Dossier erzeugen und mit dem Rohtranskript nach Drive laden."""
    clean_md = os.path.join(out_dir, f"Transkript_{base}.md")
    dossier_md = os.path.join(out_dir, f"Dossier_{base}.md")
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
    tr_folder = gw.get_or_create_folder("Transkripte", parent_id=subject_folder)
    gw.upload_file(txt, tr_folder, as_google_doc=False)                  # Rohtranskript mit Zeitmarken
    gw.upload_file(clean_md, tr_folder, as_google_doc=True)
    gw.upload_file(dossier_md, gw.get_or_create_folder("Dossiers", parent_id=subject_folder), as_google_doc=True)


ZOOMREC_DIR = "/opt/zoomrec/recordings"
ZOOMREC_SUBJECTS = {"ASTAT": "Applied_Statistics", "DBS": "Datenbanksysteme", "VSK": "Verteilte_Systeme",
                    "AEDCIT": "Academic_English", "KRR": "Logical_Reasoning_in_AI", "PREN": "Produktentwicklung_PREN1"}


def process_zoomrec(gw, state):
    """Fertige zoomrec-Aufnahmen (YYYY-MM-DD_HH-MM_<Kurz>.mp3) transkribieren, Text ablegen, MP3 loeschen."""
    if not os.path.isdir(ZOOMREC_DIR):
        return 0
    done = 0
    for name in sorted(os.listdir(ZOOMREC_DIR)):
        m = re.match(r"(\d{4}-\d\d-\d\d)_(\d\d-\d\d)_([A-Za-z]+)", name)
        path = os.path.join(ZOOMREC_DIR, name)
        if not (m and name.endswith(".mp3")) or time.time() - os.path.getmtime(path) < 300:
            continue                                      # laeuft noch (ffmpeg schreibt) oder kein zoomrec-Name
        key = "zoomrec:" + name
        st = state.get(key, {})
        if st.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        subject = ZOOMREC_SUBJECTS.get(m.group(3).upper())
        if not subject:
            print(f"   zoomrec: unbekanntes Fach in {name}, uebersprungen", flush=True)
            continue
        label = weeks.label(weeks.week_of_date(datetime.fromisoformat(m.group(1))) or 0)
        base = f"{label}_{m.group(1)}_Vorlesung_{m.group(2)}"
        out_dir = os.path.join(OUT_ROOT, subject, label)
        os.makedirs(out_dir, exist_ok=True)
        mp3, txt = os.path.join(out_dir, base + ".mp3"), os.path.join(out_dir, base + ".txt")
        print(f"\n=== zoomrec {subject}: {name}", flush=True)
        try:
            if os.path.getsize(path) < MIN_SIZE:
                raise RuntimeError("Aufnahme zu klein, vermutlich still")
            shutil.move(path, mp3)                         # andere Platte als /opt/zoomrec: kein os.replace
            transcript = transcribe_checked(mp3)
            publish(gw, subject, f"Vorlesung {m.group(1)} {m.group(2)}", base, out_dir, txt, transcript)
            os.remove(mp3)                                # nur der Text wird gebraucht
            state[key] = {"status": "fertig", "subject": subject, "at": datetime.now().isoformat()}
            done += 1
        except Exception as e:
            print(f"   FEHLER: {e}", flush=True)
            if os.path.exists(mp3) and not os.path.exists(path):
                shutil.move(mp3, path)                     # fuer den naechsten Versuch zurueck
            still = "still" in str(e).lower()
            state[key] = {"status": "still" if still else "fehler", "error": str(e)[:300],
                          "attempts": st.get("attempts", 0) + (MAX_ATTEMPTS if still else 1)}
        save_state(state)
    return done


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
        inputs = [(f, sub["id"], None) for f in children(gw, sub["id"], MEDIA_Q)]
        for wf in children(gw, sub["id"], "mimeType = 'application/vnd.google-apps.folder'"):
            wk = weeks.week_of_text(wf["name"])
            if wk:
                inputs += [(f, wf["id"], wk) for f in children(gw, wf["id"], MEDIA_Q)]
        for f, parent_id, folder_week in inputs:
            if int(f.get("size", 0) or 0) < (MIN_TEXT if is_text(f) else MIN_SIZE):
                continue
            st = state.get(f["id"], {})
            if st.get("status") == "fertig" or st.get("attempts", 0) >= MAX_ATTEMPTS or st.get("status") == "still":
                continue
            if st.get("modified") not in (None, f["modifiedTime"]):
                st = {}                                   # Datei wurde ersetzt: neu versuchen
            todo += 1
            print(f"\n=== {subject}: {f['name']}", flush=True)
            try:
                process_file(gw, f, subject, parent_id, done, folder_week)
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
    todo += process_zoomrec(gw, state)
    print(f"\nEingang geprueft: {todo} Datei(en) bearbeitet.", flush=True)


if __name__ == "__main__":
    main()
