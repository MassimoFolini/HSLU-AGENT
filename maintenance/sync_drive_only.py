"""Synchronisiert alle bereits heruntergeladenen Unterlagen nach Google Drive, ohne ILIAS neu zu scrapen.

Nutzt denselben Zustand (drive_sync.json) wie main.py: schon hochgeladene Dateien werden uebersprungen,
fehlende MP3/MP4 werden nachgeholt. Aus dem Projektroot starten: python maintenance/sync_drive_only.py
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import DriveSync, clean_subject_name, sync_course_to_drive
from google_integration import GoogleWorkspace

DOWNLOADS = "downloads"


def main():
    gw = GoogleWorkspace()
    sync = DriveSync(gw)
    for week in sorted(os.listdir(DOWNLOADS)):
        week_dir = os.path.join(DOWNLOADS, week)
        if not os.path.isdir(week_dir) or week == "live_recordings":
            continue
        for course in sorted(os.listdir(week_dir)):
            course_dir = os.path.join(week_dir, course)
            if not os.path.isdir(os.path.join(course_dir, "Unterlagen")):
                continue
            subject = clean_subject_name(course)
            print(f"\n=== {week} / {subject} ===", flush=True)
            try:
                sync_course_to_drive(sync, {"dir": course_dir, "title": course}, subject)
            except Exception as e:
                print(f" -> FEHLER: {e}", flush=True)
    print("\nDrive-Sync abgeschlossen.")


if __name__ == "__main__":
    main()
