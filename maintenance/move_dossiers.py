"""Sammelt alle bestehenden Dossiers (Google Docs 'Dossier_*') eines Fachs in <Fach>/Dossiers/.

Verschiebt nur (nichts wird geloescht) und passt drive_sync.json an, damit nichts doppelt hochgeladen wird.

  python maintenance/move_dossiers.py            # Trockenlauf: zeigt, was verschoben wuerde
  python maintenance/move_dossiers.py --apply    # verschiebt

Aus dem Projektroot starten.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import warnings

warnings.filterwarnings("ignore")
from google_integration import GoogleWorkspace

DOC = "application/vnd.google-apps.document"
FOLDER = "application/vnd.google-apps.folder"
SKIP = {"Dossiers", "_Eingang"}
JUNK = {".venv", "venv", "__pycache__", ".ipynb_checkpoints", "node_modules", ".git", "site-packages"}


def kids(gw, pid):
    out, page = [], None
    while True:
        r = gw.drive_service.files().list(q=f"'{pid}' in parents and trashed = false", pageToken=page, pageSize=200,
                                          fields="nextPageToken, files(id,name,mimeType,parents)").execute()
        out += r.get("files", [])
        page = r.get("nextPageToken")
        if not page:
            return out


def find_dossiers(gw, folder_id, hits):
    for f in kids(gw, folder_id):
        if f["mimeType"] == FOLDER:
            if f["name"] not in JUNK:
                find_dossiers(gw, f["id"], hits)
        elif f["mimeType"] == DOC and f["name"].startswith("Dossier_"):
            hits.append(f)


def main():
    apply = "--apply" in sys.argv
    gw = GoogleWorkspace()
    try:
        with open("drive_sync.json", "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except FileNotFoundError:
        state = {}
    moved = 0
    for subj in kids(gw, gw.root_folder_id):
        if subj["mimeType"] != FOLDER or subj["name"] in SKIP or subj["name"].startswith("_"):
            continue
        hits = []
        for sub in kids(gw, subj["id"]):
            if sub["mimeType"] == FOLDER and sub["name"] != "Dossiers":
                find_dossiers(gw, sub["id"], hits)
        if not hits:
            continue
        target = gw.get_or_create_folder("Dossiers", parent_id=subj["id"]) if apply else None
        print(f"\n{subj['name']}: {len(hits)} Dossier(s)")
        for f in hits:
            print("   ", f["name"])
            if not apply:
                continue
            gw.drive_service.files().update(fileId=f["id"], addParents=target, removeParents=",".join(f["parents"]), fields="id").execute()
            for k in [k for k, v in state.items() if v.get("id") == f["id"]]:
                state[f"{subj['name']}/Dossiers/{f['name']}.md"] = state.pop(k)
            moved += 1
    if apply:
        with open("drive_sync.json", "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
        print(f"\n{moved} Dossier(s) verschoben.")
    else:
        print("\nTrockenlauf. Mit --apply verschieben.")


if __name__ == "__main__":
    main()
