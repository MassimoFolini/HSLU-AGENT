"""Nimmt den Systemton des Laptops auf (z. B. Zoom-Vorlesung) und legt ihn in den Drive-Eingang.

Der Server macht daraus Transkript, saubere Fassung und Dossier (siehe maintenance/process_inbox.py).
Es nimmt nur auf, was auf diesem Laptop abgespielt wird, also dein eigener Zoom-Client. Kein Bot.
Windows, Python 3.10+, ffmpeg im PATH, pip install -r laptop/requirements-laptop.txt

  python laptop/record_system_audio.py --subject Applied_Statistics
  python laptop/record_system_audio.py --subject Datenbanksysteme --at 12:50 --minutes 140
  python laptop/record_system_audio.py --list-devices

Beenden: Ctrl+C oder --minutes. Danach wird die MP3 nach Drive (HSLU Agent/_Eingang/<Fach>/) hochgeladen.
--no-upload speichert nur lokal (recordings/<Fach>/). Zu leise Aufnahmen werden nicht hochgeladen.
Nur aufnehmen, wenn der Dozent die Aufnahme erlaubt.
"""
import argparse
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
SILENCE_DB = -55.0


def loopback_device(p, pyaudio):
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if not speakers.get("isLoopbackDevice"):
        for lb in p.get_loopback_device_info_generator():
            if speakers["name"] in lb["name"]:
                return lb
        raise RuntimeError("Kein Loopback-Geraet zum Standard-Lautsprecher gefunden.")
    return speakers


def mean_volume_db(path):
    r = subprocess.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


def wait_until(hhmm):
    h, m = map(int, hhmm.split(":"))
    now = datetime.now()
    start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if start < now:
        start += timedelta(days=1)
    print(f"Warte bis {start:%H:%M} ...", flush=True)
    while datetime.now() < start:
        time.sleep(5)


def record(out_mp3, minutes):
    import pyaudiowpatch as pyaudio
    p = pyaudio.PyAudio()
    dev = loopback_device(p, pyaudio)
    rate, channels = int(dev["defaultSampleRate"]), int(dev["maxInputChannels"])
    print(f"Nehme auf: {dev['name']} ({rate} Hz, {channels} Kanaele). Beenden mit Ctrl+C.", flush=True)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", str(channels), "-i", "-",
                           "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", out_mp3], stdin=subprocess.PIPE)
    q = queue.Queue()

    def writer():
        while True:
            chunk = q.get()
            if chunk is None:
                break
            ff.stdin.write(chunk)

    t = threading.Thread(target=writer, daemon=True)
    t.start()

    def cb(in_data, frame_count, time_info, status):
        q.put(in_data)
        return (None, pyaudio.paContinue)

    stream = p.open(format=pyaudio.paInt16, channels=channels, rate=rate, frames_per_buffer=1024, input=True,
                    input_device_index=dev["index"], stream_callback=cb)
    end = time.time() + minutes * 60 if minutes else None
    try:
        while end is None or time.time() < end:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nAufnahme beendet.", flush=True)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        q.put(None)
        t.join()
        ff.stdin.close()
        ff.wait()


def upload(mp3, subject):
    from google_integration import GoogleWorkspace
    gw = GoogleWorkspace()
    inbox = gw.get_or_create_folder("_Eingang")
    folder = gw.get_or_create_folder(subject, parent_id=inbox)
    gw.upload_file(mp3, folder, as_google_doc=False)
    print(f"Hochgeladen nach _Eingang/{subject}.", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", help="Fachname wie im Drive, z. B. Applied_Statistics")
    ap.add_argument("--minutes", type=float, help="nach so vielen Minuten automatisch beenden")
    ap.add_argument("--at", help="Startzeit HH:MM (Ortszeit), sonst sofort")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--list-devices", action="store_true")
    a = ap.parse_args()
    if a.list_devices:
        import pyaudiowpatch as pyaudio
        p = pyaudio.PyAudio()
        print("Aufnahmegeraet:", loopback_device(p, pyaudio)["name"])
        return
    if not a.subject:
        ap.error("--subject ist erforderlich")
    if a.at:
        wait_until(a.at)
    out_dir = os.path.join(BASE, "recordings", a.subject)
    os.makedirs(out_dir, exist_ok=True)
    mp3 = os.path.join(out_dir, f"{datetime.now():%Y-%m-%d_%H%M}_{a.subject}.mp3")
    record(mp3, a.minutes)
    if not os.path.exists(mp3) or os.path.getsize(mp3) < 10_000:
        sys.exit("Keine brauchbare Aufnahme entstanden.")
    level = mean_volume_db(mp3)
    if level is not None and level < SILENCE_DB:
        sys.exit(f"Aufnahme ist still ({level:.0f} dB), wird nicht hochgeladen: {mp3}. Lief der Ton ueber den Standard-Lautsprecher?")
    print(f"Datei: {mp3} ({os.path.getsize(mp3) / 1e6:.1f} MB, {level:.0f} dB)")
    if not a.no_upload:
        upload(mp3, a.subject)


if __name__ == "__main__":
    main()
