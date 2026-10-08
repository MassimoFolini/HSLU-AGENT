"""Stundenplan-Scheduler: liest live_meetings.json und startet den Zoom-Bot pünktlich.

Läuft als Dauerprozess (systemd: hslu-scheduler). Jede Minute wird geprüft, ob ein Meeting
(Wochentag + 'Von'-Zeit) beginnt. Der Bot tritt bei, nimmt Audio auf und verlässt das Meeting
zur 'Bis'-Zeit. Danach wird die MP3 nach Google Drive hochgeladen (<Fach>/Live-Aufnahmen).
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime

from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
MEETINGS_FILE = os.path.join(BASE, "live_meetings.json")
STATE_FILE = os.path.join(BASE, "live_scheduler_state.json")
RUN_SCRIPT = os.path.join(BASE, "scripts", "run_live_zoom.sh")
REC_DIR = os.path.join(BASE, "downloads", "live_recordings")
JOIN_LEAD_MIN = 2          # so viele Minuten vor Beginn beitreten
CHECK_INTERVAL_S = 30


def load_meetings():
    try:
        with open(MEETINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Scheduler] live_meetings.json nicht lesbar: {e}", flush=True)
        return []


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def parse_hm(value):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return h * 60 + mi if h < 24 and mi < 60 else None


def due(meeting, now):
    """True, wenn das Meeting jetzt beitreten soll (Zeitfenster Beginn-Lead bis Ende)."""
    if not meeting.get("record") or not meeting.get("meeting_id"):
        return False
    if str(meeting.get("day", "")) != str((now.weekday() + 1) % 7):  # Zoom/Dashboard: 0=So, 1=Mo
        return False
    start, end = parse_hm(meeting.get("time_start")), parse_hm(meeting.get("time_end"))
    if start is None or end is None or end <= start:
        return False
    cur = now.hour * 60 + now.minute
    return start - JOIN_LEAD_MIN <= cur < end


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def upload_recording(title, mp3_path):
    try:
        from google_integration import GoogleWorkspace
        from main import clean_subject_name
        gw = GoogleWorkspace()
        subject = gw.get_or_create_folder(clean_subject_name(title.replace("I.", "", 1)))
        folder = gw.get_or_create_folder("Live-Aufnahmen", parent_id=subject)
        gw.upload_file(mp3_path, folder, as_google_doc=False)
        print(f"[Scheduler] Aufnahme hochgeladen: {os.path.basename(mp3_path)}", flush=True)
    except Exception as e:
        print(f"[Scheduler] Upload fehlgeschlagen ({e}). Datei bleibt lokal: {mp3_path}", flush=True)


def run_meeting(meeting, now):
    title = meeting["title"]
    end = parse_hm(meeting["time_end"])
    end_dt = now.replace(hour=end // 60, minute=end % 60, second=0, microsecond=0)
    out_dir = os.path.join(REC_DIR, safe(title))
    os.makedirs(out_dir, exist_ok=True)
    mp3 = os.path.join(out_dir, f"{now.strftime('%Y-%m-%d')}_{meeting['time_start'].replace(':', '')}.mp3")
    meeting_id = re.sub(r"\D", "", meeting["meeting_id"])
    link = f"https://hslu.zoom.us/j/{meeting_id}"
    print(f"[Scheduler] Starte Aufnahme: {title} -> {mp3} (bis {end_dt:%H:%M})", flush=True)
    res = subprocess.run(["bash", RUN_SCRIPT, link, meeting.get("passcode", ""), mp3, str(int(end_dt.timestamp()))],
                         cwd=BASE)
    if os.path.exists(mp3) and os.path.getsize(mp3) > 10_000:
        upload_recording(title, mp3)
    else:
        print(f"[Scheduler] Keine brauchbare Aufnahme (Exit {res.returncode}).", flush=True)


def main():
    print("[Scheduler] Live-Meeting-Scheduler aktiv.", flush=True)
    state = load_state()
    while True:
        now = datetime.now()
        for m in load_meetings():
            key = f"{m.get('title')}|{now.strftime('%Y-%m-%d')}|{m.get('time_start')}"
            if key in state or not due(m, now):
                continue
            state[key] = now.isoformat()   # vor dem Start markieren: nie doppelt beitreten
            save_state(state)
            try:
                run_meeting(m, now)
            except Exception as e:
                print(f"[Scheduler] FEHLER bei {m.get('title')}: {e}", flush=True)
            now = datetime.now()
        time.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    main()
