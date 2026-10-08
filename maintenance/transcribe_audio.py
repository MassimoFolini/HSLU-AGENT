"""Transkribiert MP3-Dateien per Gemini und legt die .txt neben die MP3. Keine Zusammenfassungen.

  python maintenance/transcribe_audio.py ASTAT          # alle MP3 unter downloads/**/*ASTAT*
  python maintenance/transcribe_audio.py ASTAT --sync   # danach nach Drive hochladen

Aus dem Projektroot starten. Bereits transkribierte Dateien werden uebersprungen.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from transcriber import Transcriber

load_dotenv()


def main():
    keyword = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
    mp3s = []
    for dp, _, fns in os.walk("downloads"):
        if (keyword and keyword not in dp) or dp.endswith("_chunks"):
            continue
        for fn in fns:
            if fn.lower().endswith(".mp3"):
                mp3s.append(os.path.join(dp, fn))
    mp3s.sort()
    print(f"{len(mp3s)} MP3-Datei(en) gefunden.", flush=True)
    t = Transcriber()
    for path in mp3s:
        print(f"\n=== {path}", flush=True)
        try:
            text = t.transcribe(path)
            print(f"   Fertig: {len(text.split())} Woerter", flush=True)
        except Exception as e:
            print(f"   FEHLER: {e}", flush=True)

    if "--sync" in sys.argv:
        from google_integration import GoogleWorkspace
        from main import DriveSync, clean_subject_name, sync_course_to_drive
        sync = DriveSync(GoogleWorkspace())
        seen = set()
        for path in mp3s:
            parts = path.split(os.sep)
            course_dir = os.sep.join(parts[:parts.index("Unterlagen")])
            if course_dir in seen:
                continue
            seen.add(course_dir)
            sync_course_to_drive(sync, {"dir": course_dir}, clean_subject_name(os.path.basename(course_dir)))
    print("\nFertig.")


if __name__ == "__main__":
    main()
