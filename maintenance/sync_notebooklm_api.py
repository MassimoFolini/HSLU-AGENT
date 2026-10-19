"""Synchronisiert Dossiers, saubere Transkripte und Folien in NotebookLM Enterprise (offizielle API).

Pro Fach gibt es ein Notebook "HSLU - <Fach>". Neue und geaenderte Dateien werden hinzugefuegt,
unveraenderte uebersprungen. Authentifizierung: OAuth-Token des Gelso-Kontos (token_gelso.json,
braucht eine zugewiesene Gemini-Enterprise-Lizenz).

  python maintenance/sync_notebooklm_api.py                       # alle Faecher
  python maintenance/sync_notebooklm_api.py --subject Applied     # nur Faecher, deren Name das Stichwort enthaelt
  python maintenance/sync_notebooklm_api.py --dry-run             # nur anzeigen

Aus dem Projektroot starten. Zustand: notebooklm_api_state.json
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import mimetypes
import time
import warnings

import requests

import weeks

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(BASE, "token_gelso.json")
STATE_FILE = os.path.join(BASE, "notebooklm_api_state.json")
PROJECT_NUMBER = "584077347614"
QUOTA_PROJECT = "hslu-511808"
LOCATION = "eu"
ENDPOINT = f"https://{LOCATION}-discoveryengine.googleapis.com"
API = f"{ENDPOINT}/v1alpha/projects/{PROJECT_NUMBER}/locations/{LOCATION}"
UPLOAD = f"{ENDPOINT}/upload/v1alpha/projects/{PROJECT_NUMBER}/locations/{LOCATION}"
JUNK = {".venv", "venv", "__pycache__", ".ipynb_checkpoints", "node_modules", ".git", "site-packages"}
MAX_PDF_BYTES = 100 * 1024 * 1024
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def get_token():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    try:
        creds.refresh(Request())
    except RefreshError as e:
        raise RuntimeError(
            "Gelso-Token ungueltig oder abgelaufen. Neu anmelden (siehe README, Abschnitt NotebookLM) "
            "und in der Admin-Konsole die App als vertrauenswuerdig markieren, "
            f"sonst gilt die 16-Stunden-Regel. Details: {e}") from e
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    return creds.token


class Api:
    def __init__(self):
        self.token = get_token()

    def headers(self, extra=None):
        h = {"Authorization": f"Bearer {self.token}", "x-goog-user-project": QUOTA_PROJECT}
        h.update(extra or {})
        return h

    def call(self, method, url, retries=5, **kw):
        for attempt in range(1, retries + 1):
            r = requests.request(method, url, headers=self.headers(kw.pop("extra", None)), timeout=300, **kw)
            if r.status_code in (429, 500, 502, 503) and attempt < retries:
                time.sleep(5 * attempt)
                continue
            return r
        return r

    def create_notebook(self, title):
        r = self.call("POST", f"{API}/notebooks", json={"title": title}, extra={"Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()["notebookId"]

    def add_text(self, notebook_id, name, content):
        r = self.call("POST", f"{API}/notebooks/{notebook_id}/sources:batchCreate", extra={"Content-Type": "application/json"},
                      json={"userContents": [{"textContent": {"sourceName": name, "content": content}}]})
        r.raise_for_status()
        return r.json()["sources"][0]["sourceId"]["id"]

    def add_file(self, notebook_id, path, display_name=None):
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        upload_name = display_name or os.path.basename(path)
        with open(path, "rb") as f:
            data = f.read()
        r = self.call("POST", f"{UPLOAD}/notebooks/{notebook_id}/sources:uploadFile", data=data,
                      extra={"Content-Type": mime, "X-Goog-Upload-File-Name": upload_name, "X-Goog-Upload-Protocol": "raw"})
        r.raise_for_status()
        return r.json()["sourceId"]["id"]

    def delete_sources(self, notebook_id, source_ids):
        names = [f"projects/{PROJECT_NUMBER}/locations/{LOCATION}/notebooks/{notebook_id}/sources/{s}" for s in source_ids]
        r = self.call("POST", f"{API}/notebooks/{notebook_id}/sources:batchDelete", json={"names": names},
                      extra={"Content-Type": "application/json"})
        return r.ok


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"notebooks": {}, "files": {}}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def notebook_text(path):
    """Markdown- und Code-Zellen eines Jupyter-Notebooks (ohne Ausgaben)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
    except Exception:
        return ""
    fence = chr(96) * 3
    parts = []
    for cell in nb.get("cells", []):
        src = "".join(cell.get("source", []))
        if src.strip():
            parts.append(src if cell.get("cell_type") == "markdown" else f"{fence}python{chr(10)}{src}{chr(10)}{fence}")
    return (chr(10) * 2).join(parts)


def collect(subject_dirs):
    """Liefert (anzeigename, pfad, art) fuer Transkripte, Dossiers und PDFs."""
    out, seen = [], set()
    for root in subject_dirs:
        for dp, dns, fns in os.walk(root, followlinks=True):
            dns[:] = [d for d in dns if d not in JUNK]
            for fn in sorted(fns):
                full = os.path.join(dp, fn)
                low = fn.lower()
                # dieselbe Datei in mehreren Wochenordnern nur einmal: Texte nach Name, PDFs nach Name und Groesse
                ident = fn if low.endswith(".md") else (fn, os.path.getsize(full))
                if ident in seen:
                    continue
                seen.add(ident)
                wk = weeks.week_of_file(os.path.relpath(full, BASE))
                lab = weeks.label(wk)
                if low.endswith(".md") and fn.startswith("Transkript_"):
                    out.append((f"{lab} - Transkript - {fn[len('Transkript_'):-3]}", full, "text", wk))
                elif low.endswith(".md") and fn.startswith("Dossier_"):
                    out.append((f"{lab} - Dossier - {fn[len('Dossier_'):-3]}", full, "text", wk))
                elif low.endswith(".md") and fn.startswith("Vorlesungsskript_"):
                    out.append((f"{lab} - Vorlesungsskript (Audio)", full, "text", wk))
                elif low.endswith((".pdf", ".pptx", ".docx")) and os.path.getsize(full) <= MAX_PDF_BYTES:
                    out.append((f"{lab} - {fn}", full, "file", wk))
                elif low.endswith(".ipynb") and os.path.getsize(full) < 5_000_000:
                    out.append((f"{lab} - Notebook - {fn[:-6]}", full, "notebook", wk))
    out.sort(key=lambda x: (x[3] or 0, x[0]))      # nach Schulwoche sortiert hinzufuegen
    unique, names = [], set()
    for n, p, k, w in out:
        if n in names:                                  # gleicher Anzeigename (z.B. zwei Fassungen): nur eine Quelle
            continue
        names.add(n)
        unique.append((n, p, k))
    return unique


def subjects_on_disk():
    from main import clean_subject_name
    subjects = {}
    downloads = os.path.join(BASE, "downloads")
    for week in sorted(os.listdir(downloads)):
        wd = os.path.join(downloads, week)
        if not os.path.isdir(wd):
            continue
        if week == "live_recordings":
            for fach in os.listdir(wd):
                subjects.setdefault(clean_subject_name(fach), []).append(os.path.join(wd, fach))
            continue
        for course in os.listdir(wd):
            cd = os.path.join(wd, course)
            if os.path.isdir(cd):
                subjects.setdefault(clean_subject_name(course), []).append(cd)
    audio = os.path.join(downloads, "audio")
    if os.path.isdir(audio):
        for fach in os.listdir(audio):
            subjects.setdefault(clean_subject_name(fach), []).append(os.path.join(audio, fach))
    return subjects


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    keyword = args[args.index("--subject") + 1] if "--subject" in args else ""
    api = None if dry else Api()
    state = load_state()
    for subject, dirs in sorted(subjects_on_disk().items()):
        if keyword and keyword.lower() not in subject.lower():
            continue
        items = collect(dirs)
        if not items:
            continue
        print(f"\n=== {subject}: {len(items)} Dateien", flush=True)
        if dry:
            for name, _, kind in items:
                print(f"   [{kind}] {name}")
            continue
        nb = state["notebooks"].get(subject)
        if not nb:
            nb = api.create_notebook(f"HSLU - {subject}")
            state["notebooks"][subject] = nb
            save_state(state)
            print(f"   Notebook angelegt: HSLU - {subject}", flush=True)
        added = skipped = failed = 0
        for name, path, kind in items:
            key = f"{subject}|{os.path.relpath(path, BASE)}"
            size = os.path.getsize(path)
            known = state["files"].get(key)
            if known and known["size"] == size and known.get("name") == name and (kind != "file" or known.get("v") == 2):
                skipped += 1
                continue
            try:
                if known:
                    api.delete_sources(nb, [known["source"]])      # geaenderte Datei: alte Quelle ersetzen
                if kind in ("text", "notebook"):
                    if kind == "text":
                        with open(path, "r", encoding="utf-8") as f:
                            body = f.read()
                    else:
                        body = notebook_text(path)
                    if not body.strip():
                        continue
                    sid = api.add_text(nb, name, body)
                else:
                    sid = api.add_file(nb, path, name)
                state["files"][key] = {"size": size, "source": sid, "name": name, "v": 2}
                save_state(state)
                added += 1
                print(f"   + {name}", flush=True)
            except Exception as e:
                failed += 1
                print(f"   FEHLER bei {name}: {str(e)[:160]}", flush=True)
        current = {f"{subject}|{os.path.relpath(path, BASE)}" for _, path, _ in items}
        removed = 0
        for key in [k for k in state["files"] if k.startswith(subject + "|") and k not in current]:
            if api.delete_sources(nb, [state["files"][key]["source"]]):    # Datei verschwunden oder Doppelgaenger
                state["files"].pop(key)
                removed += 1
        if removed:
            save_state(state)
        print(f"   {added} neu, {skipped} unveraendert, {failed} Fehler, {removed} entfernt", flush=True)
    print("\nFertig.")


if __name__ == "__main__":
    main()
