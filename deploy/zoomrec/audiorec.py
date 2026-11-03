"""Audio-only Zoom-Aufnahme: tritt per zoommtg://-Deeplink bei und schneidet nur den Ton als MP3 mit.

Liest meetings.csv (weekday;time;duration;id;password;description;record;) in Europe/Zurich.
Login, "Automatisch mit Computeraudio verbinden" und "Mikrofon stumm" werden einmalig per VNC im Zoom-Client gesetzt.

On-Demand-Lebenszyklus: Zoom laeuft nur kurz vor und waehrend einer Vorlesung. Im Leerlauf ist der Client beendet, damit
kein 120-Minuten-Inaktivitaets-Timer der HSLU-Kontorichtlinie laeuft. Es werden keine Aktivitaeten vorgetaeuscht.
"""
import csv
import json
import logging
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timedelta

HOME = os.environ.get("HOME", "/home/zoomrec")
CSV_PATH = os.path.join(HOME, "meetings.csv")
REC_PATH = os.path.join(HOME, "recordings")
SOURCE = os.environ.get("AUDIO_SOURCE", "speaker.monitor")   # Null-Sink, auf den Zoom ausgibt
STATUS_FILE = os.path.join(REC_PATH, "zoom_status.json")
LIVE_PNG = os.path.join(REC_PATH, "live.png")              # Bildschirm fuers Dashboard (Live-Ansicht)
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

os.makedirs(REC_PATH, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(REC_PATH, "audiorec.log"))])


def start_client():
    if subprocess.run(["pgrep", "-f", "/opt/zoom/zoom"], capture_output=True).returncode != 0:
        logging.info("Starte Zoom-Client")
        subprocess.Popen(["zoom"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)


_misses = 0
PRECHECK_MINUTES = 3                                        # Zoom startet so lange vor dem Termin (Laden + Anmeldepruefung ca. 1 Min.)
IDLE_CLOSE_SECONDS = 120                                    # angemeldet und kein Termin in Sicht: Client so lange danach beenden
_last_signed_in = None                                      # letzter bekannter Login-Zustand (Zoom ist im Leerlauf aus)
_idle_since = None


def zoom_running():
    return subprocess.run(["pgrep", "-f", "/opt/zoom/zoom"], capture_output=True).returncode == 0


def stop_client():
    if zoom_running():
        logging.info("Beende Zoom-Client")
        subprocess.run(["pkill", "-f", "/opt/zoom/zoom"])
        time.sleep(8)
        subprocess.run(["pkill", "-9", "-f", "/opt/zoom/zoom"], capture_output=True)


def load_last_state():
    global _last_signed_in
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            _last_signed_in = json.load(f).get("signed_in")
    except Exception:
        _last_signed_in = None


def relogin():
    """Klickt Sign in -> SSO -> Domaene "hslu". Kein Passwort: klappt nur, solange Firefox die HSLU-Sitzung noch hat."""
    import pyautogui
    logging.info("Versuche automatische Neuanmeldung (SSO hslu, ohne Passwort)")
    # Nach "signed out for being inactive" zeigt Zoom "Try again"; nach einem Neustart immer die Anmeldekarte
    subprocess.run(["pkill", "-f", "/opt/zoom/zoom"])
    time.sleep(5)
    start_client()
    time.sleep(25)
    subprocess.run(["wmctrl", "-a", "Zoom Workplace"], capture_output=True)
    time.sleep(2)
    pyautogui.click(370, 346)                               # "Sign in" bzw. "You previously signed in as ..."
    time.sleep(6)
    pyautogui.click(370, 304)                               # Feld "company domain"
    pyautogui.hotkey("ctrl", "a")
    pyautogui.write("hslu", interval=0.05)
    time.sleep(1)
    pyautogui.click(370, 366)                               # Continue -> Firefox -> zoommtg:// zurueck an den Client
    time.sleep(15)


def save_status(signed_in, idle=False):
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"signed_in": signed_in, "idle": idle, "checked": datetime.now().isoformat(timespec="seconds")}, f)
    except OSError as e:
        logging.error(f"Status nicht schreibbar: {e}")


def write_status():
    """Login-Zustand aus den Fenstertiteln: angemeldet heisst das Hauptfenster "Zoom Workplace - <Kontotyp>".
    Ist Zoom bewusst aus (Leerlauf), gilt der letzte bekannte Zustand."""
    global _misses, _last_signed_in
    if not zoom_running():
        if _last_signed_in is not None:
            save_status(_last_signed_in, idle=True)
        return _last_signed_in
    titles = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True).stdout.splitlines()
    titles = [t.split(None, 3)[3] if len(t.split(None, 3)) == 4 else "" for t in titles]
    if any(t.startswith("Zoom Workplace - ") for t in titles):
        _misses = 0
        signed_in = True
    elif any(t == "Zoom Workplace" for t in titles):
        _misses += 1                                        # kurz nach dem Start fehlt der Kontotyp noch
        signed_in = False if _misses >= 2 else None
    else:
        signed_in = None                                    # Zoom-Fenster gerade nicht da (Start)
    if signed_in is None:
        return None
    _last_signed_in = signed_in
    save_status(signed_in)
    if not signed_in:
        logging.warning("Zoom ist NICHT angemeldet")
    return signed_in


def snapshot():
    tmp = LIVE_PNG + ".tmp.png"
    if subprocess.run(["scrot", "-o", tmp], capture_output=True).returncode == 0:
        os.replace(tmp, LIVE_PNG)


def join_uri(meet_id, pw):
    if meet_id.startswith("http"):                          # komplette Join-URL in der CSV
        m = re.search(r"/j/(\d+)", meet_id)
        q = re.search(r"pwd=([^&]+)", meet_id)
        meet_id, pw = (m.group(1) if m else meet_id), (q.group(1) if q else pw)
    uri = f"zoommtg://zoom.us/join?action=join&confno={meet_id}"
    return uri + (f"&pwd={pw}" if pw else "")


def meetings():
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            return [r for r in csv.DictReader(f, delimiter=";") if (r.get("weekday") or "").strip()]
    except Exception as e:
        logging.error(f"meetings.csv nicht lesbar: {e}")
        return []


def window(row, now):
    day = WEEKDAYS.index(row["weekday"].strip().lower())
    h, m = map(int, row["time"].split(":"))
    start = (now - timedelta(days=(now.weekday() - day) % 7)).replace(hour=h, minute=m, second=0, microsecond=0)
    return start, start + timedelta(minutes=int(row["duration"]))


def leave_meeting():
    # Zoom 7 nennt das Fenster nur "Meeting"; sauberstes Verlassen ist den Client zu beenden. Im Leerlauf bleibt er aus.
    stop_client()


def record(row, end):
    name = re.sub(r"[^\w.-]+", "_", row["description"].strip()) or "Meeting"
    mp3 = os.path.join(REC_PATH, f"{datetime.now():%Y-%m-%d_%H-%M}_{name}.mp3")
    uri = join_uri(row["id"].strip(), row["password"].strip())
    logging.info(f"Trete bei: {name} (bis {end:%H:%M})")
    if not zoom_running():                                  # Container wurde mitten im Termin gestartet
        start_client()
        time.sleep(30)
    subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ffmpeg = subprocess.Popen(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "pulse", "-i", SOURCE, "-vn",
                               "-acodec", "libmp3lame", "-b:a", "128k", mp3], stdin=subprocess.DEVNULL)
    logging.info(f"Aufnahme laeuft: {mp3}")
    while datetime.now() < end and ffmpeg.poll() is None:
        time.sleep(10)
        if int(time.time()) % 30 < 10:
            snapshot()
        if int(time.time()) % 120 < 10:
            write_status()
    if ffmpeg.poll() is None:
        ffmpeg.send_signal(signal.SIGINT)
        try:
            ffmpeg.wait(30)
        except subprocess.TimeoutExpired:
            ffmpeg.kill()
    else:
        logging.error(f"ffmpeg vorzeitig beendet (Exit {ffmpeg.returncode})")
    logging.info(f"Aufnahme beendet: {mp3}")
    leave_meeting()


def next_window(now):
    """True, wenn gerade ein aufzunehmender Termin laeuft oder in PRECHECK_MINUTES + 3 Minuten beginnt."""
    for row in meetings():
        if (row.get("record") or "").strip().lower() != "true":
            continue
        try:
            start, end = window(row, now)
        except Exception:
            continue
        if start - timedelta(minutes=PRECHECK_MINUTES + 3) <= now < end:
            return True
    return False


def main():
    global _idle_since
    load_last_state()
    done, prechecked = set(), set()
    logging.info(f"audiorec bereit (letzter Login-Zustand: {_last_signed_in})")
    last_check = 0
    while True:
        now = datetime.now()
        if time.time() - last_check >= 120:
            write_status()
            last_check = time.time()
        snapshot()
        # Angemeldet und kein Termin in Sicht: Client beenden, damit der 120-Minuten-Leerlauf-Timer nicht laeuft
        if zoom_running() and _last_signed_in and not next_window(now):
            _idle_since = _idle_since or time.time()
            if time.time() - _idle_since >= IDLE_CLOSE_SECONDS:
                stop_client()
                write_status()
                _idle_since = None
        else:
            _idle_since = None
        for row in meetings():
            if (row.get("record") or "").strip().lower() != "true":
                continue
            try:
                start, end = window(row, now)
            except Exception as e:
                logging.error(f"Ungueltige Zeile {row}: {e}")
                continue
            key = (row["description"], start)
            if start - timedelta(minutes=PRECHECK_MINUTES) <= now < start and key not in prechecked:
                if not zoom_running():
                    start_client()
                    time.sleep(30)
                st = write_status()                       # None = noch unklar, im naechsten Durchlauf (20 s) erneut
                if st is not None:
                    prechecked.add(key)                   # einmal pro Termin: angemeldet? sonst passwortlos neu anmelden
                if st is False:
                    relogin()
                    logging.info(f"Nach Neuanmeldung angemeldet: {bool(write_status())}")
            if start <= now < end - timedelta(minutes=2) and key not in done:
                done.add(key)
                record(row, end)
        time.sleep(20)


if __name__ == "__main__":
    main()
