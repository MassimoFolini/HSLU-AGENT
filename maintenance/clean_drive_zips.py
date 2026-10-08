"""Findet alte .zip-Dateien und Junk-Ordner (.venv, __pycache__ ...) im Google-Drive-Zielordner. Standard: nur anzeigen (Trockenlauf).

  python maintenance/clean_drive_zips.py            # listet nur auf
  python maintenance/clean_drive_zips.py --apply    # verschiebt sie in den Drive-Papierkorb (30 Tage wiederherstellbar)

Aus dem Projektroot starten.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from google_integration import GoogleWorkspace

SYNC_FILE = "drive_sync.json"
JUNK_DIRS = {".venv", "venv", "__pycache__", ".ipynb_checkpoints", "node_modules", ".git", "site-packages"}


def walk(gw, folder_id, prefix, hits):
    page = None
    while True:
        res = gw.drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)", pageSize=200, pageToken=page).execute()
        for f in res.get("files", []):
            path = f"{prefix}/{f['name']}"
            if f["mimeType"] == "application/vnd.google-apps.folder":
                if f["name"] in JUNK_DIRS:
                    hits.append((f["id"], path + "/"))  # ganzer Ordner in den Papierkorb, kein Abstieg
                else:
                    walk(gw, f["id"], path, hits)
            elif f["name"].lower().endswith(".zip"):
                hits.append((f["id"], path))
        page = res.get("nextPageToken")
        if not page:
            return


def main():
    apply = "--apply" in sys.argv
    gw = GoogleWorkspace()
    hits = []
    walk(gw, gw.root_folder_id, "", hits)
    print(f"{len(hits)} Treffer (ZIP-Dateien und Junk-Ordner):")
    for _, path in hits:
        print("  ", path)
    if not apply or not hits:
        if hits:
            print("\nTrockenlauf. Mit --apply in den Papierkorb verschieben.")
        return
    ids = {fid for fid, _ in hits}
    for fid, path in hits:
        gw.drive_service.files().update(fileId=fid, body={"trashed": True}).execute()
        print("Papierkorb:", path)
    try:
        with open(SYNC_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        state = {k: v for k, v in state.items() if v.get("id") not in ids and not any(f"/{d}/" in "/" + k for d in JUNK_DIRS)}
        with open(SYNC_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    main()
