"""Audio-only Zoom-Aufnahme: tritt per zoommtg://-Deeplink bei und schneidet nur den Ton als MP3 mit.

Liest meetings.csv (weekday;time;duration;id;password;description;record;) in Europe/Zurich.
Lebenszyklus:
  - Ausserhalb der Vorlesungen ist Zoom im Standby geschlossen (kein 120-Minuten-Inaktivitaets-Logout).
  - 10 Minuten vor jeder Vorlesung startet Zoom automatisch und meldet sich bei Bedarf per SSO (hslu) an.
  - Jederzeit steuerbar ueber zoom_cmd.json / Dashboard ("login" / "logout") oder CLI (--login / --logout / --status).
"""
import csv
import fcntl
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta

HOME = os.environ.get("HOME", "/home/zoomrec")
CSV_PATH = os.path.join(HOME, "meetings.csv")
REC_PATH = os.path.join(HOME, "recordings")
SOURCE = os.environ.get("AUDIO_SOURCE", "speaker.monitor")   # Null-Sink, auf den Zoom ausgibt
STATUS_FILE = os.path.join(REC_PATH, "zoom_status.json")
CMD_FILE = os.path.join(REC_PATH, "zoom_cmd.json")
LIVE_PNG = os.path.join(REC_PATH, "live.png")                # Bildschirm fuers Dashboard (Live-Ansicht)
ZOOM_CONF = os.path.join(HOME, ".config", "zoomus.conf")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

PRECHECK_MINUTES = 10                                        # 10 Min. vor Vorlesung starten & Login sicherstellen
IDLE_CLOSE_SECONDS = 60                                      # angemeldet & kein Termin in Sicht -> nach 60 s in Standby
KEEPALIVE_SECONDS = 600                                      # X11-Wachhalter alle 10 Min.

_misses = 0
_last_signed_in = None
_idle_since = None
_manual_logout = False
_last_relogin_try = 0


def ensure_zoom_conf():
    """Stellt sicher, dass PulseAudio auf 'speaker' zeigt und Zoom Audio automatisch & stumm verbindet."""
    subprocess.run(["pactl", "set-default-sink", "speaker"], capture_output=True)
    if zoom_running():
        return
    os.makedirs(os.path.dirname(ZOOM_CONF), exist_ok=True)
    lines = []
    if os.path.exists(ZOOM_CONF):
        try:
            with open(ZOOM_CONF, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
    want = {"autoConnectAudio": "true", "MuteVoipWhenJoin": "true"}
    seen = set()
    out = []
    for line in lines:
        k = line.split("=", 1)[0].strip() if "=" in line else ""
        if k in want:
            out.append(f"{k}={want[k]}")
            seen.add(k)
        else:
            out.append(line)
    if not any(l.strip() == "[General]" for l in out):
        out.insert(0, "[General]")
    idx = next((i + 1 for i, l in enumerate(out) if l.strip() == "[General]"), 1)
    for k, v in want.items():
        if k not in seen:
            out.insert(idx, f"{k}={v}")
    try:
        with open(ZOOM_CONF, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
    except OSError as e:
        logging.warning(f"zoomus.conf nicht schreibbar: {e}")


def zoom_running():
    return subprocess.run(["pgrep", "-f", "/opt/zoom/[z]oom"], capture_output=True).returncode == 0


def start_client():
    if not zoom_running():
        ensure_zoom_conf()
        logging.info("Starte Zoom-Client")
        subprocess.Popen(["zoom"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)


def stop_client():
    if zoom_running():
        logging.info("Beende Zoom-Client (Standby)")
        subprocess.run(["pkill", "-f", "/opt/zoom/[z]oom"], capture_output=True)
        for _ in range(16):
            if not zoom_running():
                return
            time.sleep(0.5)
        subprocess.run(["pkill", "-9", "-f", "/opt/zoom/[z]oom"], capture_output=True)


def wmctrl_windows():
    res = subprocess.run(["wmctrl", "-lG"], capture_output=True, text=True)
    wins = []
    for line in res.stdout.splitlines():
        parts = line.split(None, 7)
        if len(parts) >= 8:
            try:
                wins.append({
                    "id": parts[0],
                    "desk": parts[1],
                    "x": int(parts[2]),
                    "y": int(parts[3]),
                    "w": int(parts[4]),
                    "h": int(parts[5]),
                    "title": parts[7],
                })
            except ValueError:
                continue
    return wins


def zoom_state():
    """True = angemeldet (oder im Meeting), False = Anmeldefenster offen, None = Client aus oder startet noch."""
    if not zoom_running():
        return None
    titles = [w["title"] for w in wmctrl_windows()]
    if any(t.startswith("Zoom Workplace - ") or t in ("Meeting", "Zoom Meeting") for t in titles):
        return True
    if any(t == "Zoom Workplace" for t in titles):
        return False
    return None


def wait_zoom_ready(timeout=28):
    """Startet Zoom falls noetig und wartet bis der Anmeldezustand eindeutig feststeht."""
    start_client()
    saw_unsigned = 0
    for _ in range(timeout):
        st = zoom_state()
        if st is True:
            return True
        if st is False:
            saw_unsigned += 1
            if saw_unsigned >= 4:
                return False
        time.sleep(1)
    return zoom_state()


def snapshot():
    tmp = LIVE_PNG + ".tmp.png"
    if subprocess.run(["scrot", "-o", tmp], capture_output=True).returncode == 0:
        try:
            os.replace(tmp, LIVE_PNG)
        except OSError:
            pass


def keep_awake():
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.moveRel(10, 10)
        time.sleep(0.2)
        pyautogui.moveRel(-10, -10)
    except Exception:
        pass


def load_last_state():
    global _last_signed_in
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            _last_signed_in = json.load(f).get("signed_in")
    except Exception:
        _last_signed_in = None


def save_status(signed_in, idle=False):
    try:
        tmp = STATUS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "signed_in": signed_in,
                "idle": idle,
                "checked": datetime.now().isoformat(timespec="seconds"),
            }, f)
        os.replace(tmp, STATUS_FILE)
    except OSError as e:
        logging.error(f"Status nicht schreibbar: {e}")


def write_status():
    """Aktualisiert zoom_status.json anhand der offenen Fenster oder des Standby-Zustands."""
    global _misses, _last_signed_in
    if not zoom_running():
        if _last_signed_in is not None:
            save_status(_last_signed_in, idle=bool(_last_signed_in))
        return _last_signed_in
    st = zoom_state()
    if st is True:
        _misses = 0
        signed_in = True
    elif st is False:
        _misses += 1
        signed_in = False if _misses >= 2 else None
    else:
        signed_in = None
    if signed_in is None:
        return None
    prev = _last_signed_in
    _last_signed_in = signed_in
    save_status(signed_in, idle=False)
    if signed_in and prev is not True:
        logging.info("Zoom ist angemeldet")
    elif not signed_in and not _manual_logout:
        logging.warning("Zoom ist NICHT angemeldet")
    return signed_in


def _has_left_sidebar():
    """Erkennt den Bildschirm direkt nach 'Sign out' (graue linke Seitenleiste um x=40, y=300)."""
    snapshot()
    try:
        from PIL import Image
        with Image.open(LIVE_PNG) as im:
            r, g, b = im.convert("RGB").getpixel((40, 300))
        return 195 <= min(r, g, b) and max(r, g, b) <= 245
    except Exception:
        return False


def _click_firefox_sso_if_needed():
    """Falls Firefox Microsoft-Login ('Sign in to your account' / 'Stay signed in?') zeigt, bestaetigen."""
    import pyautogui
    pyautogui.FAILSAFE = False
    for w in wmctrl_windows():
        t = w["title"]
        if "Mozilla Firefox" in t and ("Sign in to your account" in t or "Anmelden" in t):
            logging.info(f"Bestaetige Microsoft-SSO im Browser ({t})")
            subprocess.run(["wmctrl", "-i", "-a", w["id"]], capture_output=True)
            time.sleep(1.0)
            pyautogui.click(616, 406)
            time.sleep(0.4)
            pyautogui.press("enter")
            return True
    return False


def relogin():
    """Meldet Zoom automatisch per SSO (hslu) an — funktioniert sowohl vom 'Sign out'-Screen (SSO-Icon)
    als auch von der 'Previously signed in'-Karte nach einem Neustart."""
    global _last_signed_in, _misses, _last_relogin_try
    import pyautogui
    pyautogui.FAILSAFE = False
    _last_relogin_try = time.time()

    st = wait_zoom_ready(timeout=25)
    if st is True:
        _misses = 0
        _last_signed_in = True
        save_status(True, idle=False)
        snapshot()
        logging.info("Zoom ist angemeldet")
        return True

    for attempt in range(2):
        if attempt == 1:
            logging.info("Zweiter Anmeldeversuch nach frischem Zoom-Neustart ...")
            stop_client()
            time.sleep(3)
            if wait_zoom_ready(timeout=25) is True:
                _misses = 0
                _last_signed_in = True
                save_status(True, idle=False)
                snapshot()
                logging.info("Zoom ist angemeldet")
                return True

        zwin = next((w for w in wmctrl_windows() if w["title"] == "Zoom Workplace"), None)
        if not zwin:
            continue

        subprocess.run(["wmctrl", "-i", "-a", zwin["id"]], capture_output=True)
        time.sleep(1.5)
        wx, wy = zwin["x"], zwin["y"]

        if _has_left_sidebar():
            # Screen direkt nach 'Sign out' (mit grauer linker Leiste + 'SSO'-Schluessel-Button unten links)
            logging.info("Versuche automatische Anmeldung ueber SSO-Button (Post-Sign-out-Ansicht)")
            pyautogui.click(wx + 320, wy + 480)             # (320, 507) bei wx=0, wy=27
            time.sleep(4)
            if zoom_state() is False and not _click_firefox_sso_if_needed():
                z2 = next((w for w in wmctrl_windows() if w["title"] == "Zoom Workplace"), zwin)
                subprocess.run(["wmctrl", "-i", "-a", z2["id"]], capture_output=True)
                time.sleep(0.8)
                pyautogui.click(z2["x"] + 465, z2["y"] + 364)
                pyautogui.hotkey("ctrl", "a")
                pyautogui.write("hslu", interval=0.05)
                time.sleep(0.5)
                pyautogui.press("enter")
        else:
            # Frischer Start: 'You previously signed in as ...'-Karte -> 'Sign in with SSO' -> 'hslu'
            logging.info("Versuche automatische Anmeldung ueber gespeicherte Karte / SSO hslu")
            pyautogui.click(wx + 465, wy + 406)             # (362, 346) bei wx=-103, wy=-60
            time.sleep(4)
            if zoom_state() is False and not _click_firefox_sso_if_needed():
                z2 = next((w for w in wmctrl_windows() if w["title"] == "Zoom Workplace"), zwin)
                subprocess.run(["wmctrl", "-i", "-a", z2["id"]], capture_output=True)
                time.sleep(0.8)
                pyautogui.click(z2["x"] + 465, z2["y"] + 364)   # Feld 'Enter your company domain'
                pyautogui.hotkey("ctrl", "a")
                pyautogui.write("hslu", interval=0.05)
                time.sleep(0.5)
                pyautogui.press("enter")
                time.sleep(1.0)
                if zoom_state() is False:
                    pyautogui.click(z2["x"] + 465, z2["y"] + 426)  # 'Continue'-Button

        for _ in range(22):
            time.sleep(1)
            if zoom_state() is True:
                _misses = 0
                _last_signed_in = True
                save_status(True, idle=False)
                snapshot()
                logging.info("Zoom ist angemeldet (automatischer SSO-Login erfolgreich)")
                return True
            if _click_firefox_sso_if_needed():
                time.sleep(2)

    _last_signed_in = False
    save_status(False, idle=False)
    snapshot()
    logging.warning("Automatische Zoom-Anmeldung fehlgeschlagen")
    return False


def signout():
    """Meldet den Zoom-Client sauber ueber das Profilmenue ('Sign out') ab."""
    global _last_signed_in, _misses
    import pyautogui
    pyautogui.FAILSAFE = False
    logging.info("Melde Zoom-Client ab ...")

    st = wait_zoom_ready(timeout=25)
    if st is False:
        _misses = 2
        _last_signed_in = False
        save_status(False, idle=False)
        snapshot()
        logging.info("Zoom ist bereits abgemeldet")
        return True

    zwin = next((w for w in wmctrl_windows() if w["title"].startswith("Zoom Workplace - ")), None)
    if not zwin:
        logging.warning("Kein angemeldetes Zoom-Fenster zum Abmelden gefunden")
        return False

    subprocess.run(["wmctrl", "-i", "-a", zwin["id"]], capture_output=True)
    time.sleep(1.0)
    if zwin["w"] < 800:
        pyautogui.click(zwin["x"] + zwin["w"] - 89, zwin["y"] + 28)   # Fenster maximieren
        time.sleep(1.5)
        zwin = next((w for w in wmctrl_windows() if w["id"] == zwin["id"]), zwin)

    pyautogui.click(zwin["x"] + zwin["w"] - 206, zwin["y"] + 28)      # Profilbild oben rechts (818, 55)
    time.sleep(1.5)
    pyautogui.click(zwin["x"] + zwin["w"] - 409, zwin["y"] + 493)     # 'Sign out' im Menue (615, 520)

    for _ in range(12):
        time.sleep(1)
        if zoom_state() is False:
            _misses = 2
            _last_signed_in = False
            save_status(False, idle=False)
            snapshot()
            logging.info("Zoom wurde sauber abgemeldet")
            return True

    snapshot()
    logging.warning("Abmeldung konnte nicht bestaetigt werden")
    return False


def ensure_signed_in(reason=""):
    """Stellt sicher, dass Zoom laeuft und angemeldet ist."""
    global _last_signed_in, _misses, _manual_logout
    _manual_logout = False
    st = wait_zoom_ready(timeout=25)
    if st is True:
        _misses = 0
        _last_signed_in = True
        save_status(True, idle=False)
        snapshot()
        logging.info(f"Zoom ist angemeldet{f' ({reason})' if reason else ''}")
        return True
    return relogin()


def join_uri(meet_id, pw):
    tk = ""
    if meet_id.startswith("http"):
        m = re.search(r"/j/(\d+)", meet_id)
        q = re.search(r"pwd=([^&#]+)", meet_id)
        t = re.search(r"tk=([^&#]+)", meet_id)
        meet_id = m.group(1) if m else meet_id
        pw = q.group(1) if q else pw
        tk = t.group(1) if t else ""
    uri = f"zoommtg://zoom.us/join?action=join&confno={meet_id}"
    if pw:
        uri += f"&pwd={pw}"
    if tk:
        uri += f"&tk={tk}"
    uri += "&zc=0&uname=Massimo%20Folini"
    return uri


def meetings():
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            return [r for r in csv.DictReader(f, delimiter=";") if (r.get("weekday") or "").strip()]
    except Exception as e:
        logging.error(f"meetings.csv nicht lesbar: {e}")
        return []


def window(row, now):
    day = WEEKDAYS.index(row["weekday"].strip().lower())
    h, m = map(int, row["time"].strip().split(":"))
    dur = timedelta(minutes=int(row["duration"]))
    candidates = []
    for delta_days in range(-1, 8):
        cand_date = (now + timedelta(days=delta_days)).date()
        if cand_date.weekday() == day:
            s = datetime(cand_date.year, cand_date.month, cand_date.day, h, m, 0)
            candidates.append((s, s + dur))
    for s, e in candidates:
        if s - timedelta(minutes=PRECHECK_MINUTES + 5) <= now < e:
            return s, e
    return candidates[0]


def leave_meeting():
    stop_client()
    if _last_signed_in is not None:
        save_status(_last_signed_in, idle=bool(_last_signed_in))
    snapshot()


def _in_meeting_window():
    wins = wmctrl_windows()
    titles = [w["title"] for w in wins]
    if any(t in ("Meeting", "Zoom Meeting") or "meeting" in t.lower() for t in titles):
        return True
    zoom_wins = [t for t in titles if "zoom" in t.lower()]
    return len(zoom_wins) >= 2


def record(row, end):
    name = re.sub(r"[^\w.-]+", "_", row["description"].strip()) or "Meeting"
    mp3 = os.path.join(REC_PATH, f"{datetime.now():%Y-%m-%d_%H-%M}_{name}.mp3")
    part_mp3 = mp3 + ".part"
    uri = join_uri(row["id"].strip(), (row.get("password") or "").strip())

    logging.info(f"Vorbereitung Beitritt: {name} (bis {end:%H:%M})")
    ensure_signed_in(reason=f"Vorlesung {name}")
    subprocess.run(["pactl", "set-default-sink", "speaker"], capture_output=True)

    logging.info(f"Trete bei: {name} (bis {end:%H:%M})")
    subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    joined = False
    for _ in range(20):
        time.sleep(1)
        if _in_meeting_window():
            joined = True
            break
    if not joined:
        logging.warning(f"Kein Meeting-Fenster nach 20s erkannt — sende Beitrittslink erneut ({name})")
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)

    snapshot()
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "pulse", "-i", SOURCE,
         "-vn", "-acodec", "libmp3lame", "-b:a", "128k", "-f", "mp3", part_mp3],
        stdin=subprocess.DEVNULL,
    )
    logging.info(f"Aufnahme laeuft: {mp3}")
    last_awake = time.time()
    while datetime.now() < end and ffmpeg.poll() is None:
        time.sleep(10)
        if int(time.time()) % 30 < 10:
            snapshot()
        if int(time.time()) % 120 < 10:
            write_status()
        if time.time() - last_awake >= KEEPALIVE_SECONDS:
            keep_awake()
            last_awake = time.time()

    if ffmpeg.poll() is None:
        ffmpeg.send_signal(signal.SIGINT)
        try:
            ffmpeg.wait(30)
        except subprocess.TimeoutExpired:
            ffmpeg.kill()
    else:
        logging.error(f"ffmpeg vorzeitig beendet (Exit {ffmpeg.returncode})")

    if os.path.exists(part_mp3):
        os.replace(part_mp3, mp3)
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


def process_pending_cmd(now):
    """Verarbeitet Steuerbefehle aus zoom_cmd.json ('login' / 'logout') atomar."""
    global _manual_logout, _idle_since
    if not os.path.exists(CMD_FILE):
        return
    busy_file = CMD_FILE + ".busy"
    try:
        os.replace(CMD_FILE, busy_file)
    except OSError:
        return
    try:
        with open(busy_file, "r", encoding="utf-8") as f:
            cmd = json.load(f)
    except Exception:
        cmd = {}

    try:
        action = (cmd.get("action") or "").strip().lower()
        if action == "login":
            logging.info("Steuerbefehl erhalten: Zoom-Anmeldung pruefen / einloggen")
            ok = ensure_signed_in(reason="Manuelle Anforderung")
            if ok and not next_window(now):
                time.sleep(2)
                stop_client()
                save_status(True, idle=True)
                snapshot()
                logging.info("Zoom ist angemeldet (Standby aktiv — Start erfolgt 10 Min. vor Vorlesung)")
            _idle_since = None
        elif action == "logout":
            logging.info("Steuerbefehl erhalten: Zoom abmelden")
            _manual_logout = True
            signout()
            _idle_since = None
    finally:
        try:
            os.remove(busy_file)
        except OSError:
            pass


def send_cli_cmd(action):
    """Hilfsmodus fuer CLI: python3 audiorec.py --login | --logout | --status."""
    os.makedirs(REC_PATH, exist_ok=True)
    if action == "status":
        try:
            with open(STATUS_FILE, encoding="utf-8") as f:
                print(f.read().strip())
        except Exception as e:
            print(json.dumps({"error": str(e)}))
        return 0

    before = ""
    try:
        before = open(STATUS_FILE, encoding="utf-8").read()
    except Exception:
        pass
    req_time = datetime.now().isoformat(timespec="seconds")
    tmp = CMD_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"action": action, "requested_at": req_time}, f)
    os.replace(tmp, CMD_FILE)
    print(f"Befehl '{action}' gesendet, warte auf Ausfuehrung ...", flush=True)

    busy_file = CMD_FILE + ".busy"
    for _ in range(75):
        time.sleep(1)
        if not os.path.exists(CMD_FILE) and not os.path.exists(busy_file):
            try:
                cur = json.load(open(STATUS_FILE, encoding="utf-8"))
                if cur.get("checked", "") >= req_time or json.dumps(cur) != before:
                    expected = (action == "login")
                    if cur.get("signed_in") == expected:
                        print(json.dumps(cur))
                        return 0
            except Exception:
                pass
    try:
        print(open(STATUS_FILE, encoding="utf-8").read().strip())
    except Exception:
        pass
    return 1


def main():
    global _idle_since, _manual_logout
    lock_fp = open("/tmp/audiorec.lock", "w")
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("audiorec.py laeuft bereits — beende doppelte Instanz.", flush=True)
        return
    os.makedirs(REC_PATH, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(REC_PATH, "audiorec.log"))],
    )
    ensure_zoom_conf()
    load_last_state()
    done, prechecked = set(), set()
    logging.info(f"audiorec bereit (letzter Login-Zustand: {_last_signed_in}, Vorlauf: {PRECHECK_MINUTES} Min.)")

    now = datetime.now()
    if _last_signed_in is True and not zoom_running():
        save_status(True, idle=True)
        logging.info("Zoom ist angemeldet (Standby aktiv — Anmeldung/Start 10 Min. vor Vorlesung)")
    elif _last_signed_in is not True:
        if ensure_signed_in(reason="Startpruefung") and not next_window(now):
            stop_client()
            save_status(True, idle=True)
            logging.info("Zoom ist angemeldet (Standby aktiv — Anmeldung/Start 10 Min. vor Vorlesung)")

    last_check = time.time()
    last_awake = time.time()

    while True:
        now = datetime.now()
        process_pending_cmd(now)

        if time.time() - last_awake >= KEEPALIVE_SECONDS:
            keep_awake()
            last_awake = time.time()

        if time.time() - last_check >= 120:
            st = write_status()
            # Falls Zoom unerwartet offen & abgemeldet ist (ohne manuelles Logout), automatisch heilen
            if st is False and not _manual_logout and time.time() - _last_relogin_try >= 180:
                ensure_signed_in(reason="Auto-Heilung")
            last_check = time.time()

        snapshot()

        # Angemeldet und kein Termin in Sicht: Client beenden (Standby gegen 120-Min.-Inaktivitaets-Timer)
        if zoom_running() and _last_signed_in and not next_window(now):
            _idle_since = _idle_since or time.time()
            if time.time() - _idle_since >= IDLE_CLOSE_SECONDS:
                stop_client()
                save_status(True, idle=True)
                snapshot()
                logging.info("Zoom ist angemeldet (Standby aktiv — naechster Start 10 Min. vor Vorlesung)")
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
            key = (row["description"].strip(), start)

            # 10 Minuten vor Vorlesung: Zoom starten & sicherstellen, dass angemeldet (auch nach manuellem Logout!)
            if start - timedelta(minutes=PRECHECK_MINUTES) <= now < start and key not in prechecked:
                if time.time() - _last_relogin_try >= 45 or zoom_state() is not False:
                    logging.info(f"Vorab-Check ({PRECHECK_MINUTES} Min. vor {row['description'].strip()}): pruefe Zoom-Login ...")
                    if ensure_signed_in(reason=f"Vorab-Check {row['description'].strip()}"):
                        prechecked.add(key)

            if start <= now < end - timedelta(minutes=1) and key not in done:
                done.add(key)
                record(row, end)

        for _ in range(10):
            if os.path.exists(CMD_FILE):
                break
            time.sleep(2)


if __name__ == "__main__":
    if "--login" in sys.argv:
        sys.exit(send_cli_cmd("login"))
    if "--logout" in sys.argv:
        sys.exit(send_cli_cmd("logout"))
    if "--status" in sys.argv:
        sys.exit(send_cli_cmd("status"))
    main()
