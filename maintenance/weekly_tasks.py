"""Wochen-Aufgaben: jeden Sonntag legt Gemini pro Fach einfache Aufgaben fuer die naechste Schulwoche in Todoist an.

Grundlage pro Fach: Transkripte und Dossiers der Vorwoche und der Zielwoche (was die Dozierenden gesagt haben),
Folien, Uebungen und Notebooks der Zielwoche. Todoist: Projekt "HSLU", ein Abschnitt pro Fach, Label "SWnn".

  python maintenance/weekly_tasks.py --dry-run          # zeigt die Aufgaben, legt nichts an
  python maintenance/weekly_tasks.py                    # naechste Woche (am Sonntag), sonst die laufende
  python maintenance/weekly_tasks.py --week 9           # bestimmte Schulwoche
  python maintenance/weekly_tasks.py --subject Applied  # nur Faecher mit diesem Stichwort
  python maintenance/weekly_tasks.py --force            # auch Faecher, die diese Woche schon angelegt wurden

Aus dem Projektroot starten. Braucht TODOIST_API_TOKEN und GEMINI_API_KEY in der .env.
Zustand: weekly_tasks_state.json (verhindert doppelte Aufgaben). Ergebnis des letzten Laufs: weekly_tasks_status.json
(das Dashboard zeigt einen Warnbalken, wenn er fehlgeschlagen oder zu alt ist; bei Fehlern kommt zusaetzlich eine
Nachricht ueber die Kanaele in /opt/zoomrec/notify.env, siehe notify_signout.py).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hashlib
import json
import re
import urllib.error
import urllib.request
import warnings
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

import sync_notebooklm_api as nlm
import weeks

BASE = nlm.BASE
STATE_FILE = os.path.join(BASE, "weekly_tasks_state.json")
STATUS_FILE = os.path.join(BASE, "weekly_tasks_status.json")
TODOIST = "https://api.todoist.com/api/v1"
PROJECT = "HSLU"
MAX_TASKS = 6               # pro Fach und Woche
MAX_CHARS_ITEM = 6000       # pro Quelle
MAX_CHARS_SUBJECT = 60000   # pro Fach (haelt die KI-Kosten bei wenigen Rappen)
MODEL = os.environ.get("GEMINI_TASK_MODEL", os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-3.5-flash"))

PROMPT = """Du schreibst eine einfache Aufgabenliste fuer einen Studenten der Hochschule Luzern.
Fach: {subject}. Schulwoche: {label} (Montag {monday:%d.%m.%Y} bis Sonntag {sunday:%d.%m.%Y}).

Unten steht Material: Mitschriften der Vorlesungen (Vorwoche und diese Woche), Dossiers, Folien, Uebungen.
Finde die konkreten Dinge, die der Student in {label} erledigen muss: Abgaben, Uebungsserien, Lesen, Vorbereiten,
Tests und Pruefungen. Beachte, was die Dozierenden sagen ("bis naechste Woche", "reicht bis ...", "bereitet ... vor").

Regeln:
- Hoechstens {max_tasks} Aufgaben. Nur Dinge, die im Material stehen. Erfinde nichts.
- Schreibe sehr einfach und kurz, Alltagssprache, kein Fachjargon. Der Titel beginnt mit einem Verb
  (zum Beispiel "Serie 8 abgeben", "Kapitel 3 lesen", "Fragen zum Test ueben"), hoechstens 8 Woerter.
- due: Datum als YYYY-MM-DD, wenn im Material eine Frist steht oder klar ableitbar ist
  ("bis naechste Woche" = Montag {next_monday:%Y-%m-%d}). Sonst null.
- note: ein einfacher Satz, woher die Aufgabe kommt oder was genau zu tun ist.
- Gibt es nichts Konkretes, antworte mit einer leeren Liste.

Antworte nur mit JSON: {{"tasks": [{{"title": "...", "due": "YYYY-MM-DD" oder null, "note": "..."}}]}}

MATERIAL:
{material}
"""


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def monday_of(week):
    return weeks.SEMESTER_START + timedelta(weeks=week - 1)


def target_week(args):
    if "--week" in args:
        return int(args[args.index("--week") + 1])
    return weeks.week_of_date(date.today() + timedelta(days=1)) or 0      # am Sonntag: die kommende Woche


def item_text(path, kind):
    try:
        if kind == "text":
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        if kind == "notebook":
            return nlm.notebook_text(path)
        if path.lower().endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(path)
            return "\n".join((p.extract_text() or "") for p in reader.pages[:25])
    except Exception:
        pass
    return ""


def material_for(subject, dirs, wk):
    """Texte der Zielwoche (alles) und der Vorwoche (nur Mitschriften und Dossiers), gekuerzt."""
    parts, total = [], 0
    for name, path, kind in nlm.collect(dirs):
        m = re.match(r"SW(\d\d)", name)
        w = int(m.group(1)) if m else None
        if w == wk:
            pass
        elif w == wk - 1 and kind == "text":
            pass
        elif w == 0 and "Modulbeschreibung" in name:
            pass
        else:
            continue
        text = item_text(path, kind).strip()
        if len(text) < 200:
            continue
        chunk = f"--- {name} ---\n{text[:MAX_CHARS_ITEM]}"
        if total + len(chunk) > MAX_CHARS_SUBJECT:
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n\n".join(parts)


def ask_gemini(subject, wk, material):
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel(MODEL, generation_config={"response_mime_type": "application/json", "temperature": 0.2})
    mon = monday_of(wk)
    prompt = PROMPT.format(subject=subject.replace("_", " "), label=weeks.label(wk), monday=mon,
                           sunday=mon + timedelta(days=6), next_monday=mon + timedelta(days=7),
                           max_tasks=MAX_TASKS, material=material)
    for attempt in range(3):
        try:
            data = json.loads(model.generate_content(prompt).text)
            tasks = data.get("tasks", []) if isinstance(data, dict) else []
            return [t for t in tasks if isinstance(t, dict) and str(t.get("title", "")).strip()][:MAX_TASKS]
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Gemini-Antwort nicht brauchbar: {str(e)[:150]}")


class Todoist:
    def __init__(self):
        self.token = (os.environ.get("TODOIST_API_TOKEN") or "").strip()
        if not self.token:
            raise RuntimeError("TODOIST_API_TOKEN fehlt in der .env (Dashboard, Logins & Zugangsdaten).")

    def call(self, method, path, body=None):
        req = urllib.request.Request(TODOIST + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Todoist {method} {path}: HTTP {e.code} {e.read().decode()[:200]}")

    def all(self, path):
        out, cursor = [], None
        while True:
            sep = "&" if "?" in path else "?"
            res = self.call("GET", path + (f"{sep}cursor={cursor}" if cursor else ""))
            out += res.get("results", [])
            cursor = res.get("next_cursor")
            if not cursor:
                return out

    def project(self):
        for p in self.all("/projects"):
            if p["name"] == PROJECT:
                return p["id"]
        return self.call("POST", "/projects", {"name": PROJECT})["id"]

    def section(self, project_id, name):
        for s in self.all(f"/sections?project_id={project_id}"):
            if s["name"] == name:
                return s["id"]
        return self.call("POST", "/sections", {"name": name, "project_id": project_id})["id"]

    def open_titles(self, project_id):
        return {t["content"].strip().lower() for t in self.all(f"/tasks?project_id={project_id}")}

    def add(self, project_id, section_id, title, note, due, label):
        body = {"content": title, "description": note, "project_id": project_id, "section_id": section_id, "labels": [label]}
        if due:
            body["due_date"] = due
        return self.call("POST", "/tasks", body)["id"]


def clean_due(value, mon):
    """Nur gueltige Daten; nichts weit ausserhalb der Zielwoche."""
    try:
        d = datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return d.isoformat() if mon - timedelta(days=7) <= d <= mon + timedelta(days=35) else None


def write_status(ok, label, created, problems):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({"ok": ok, "at": datetime.now().isoformat(timespec="seconds"), "week": label, "created": created,
                   "problems": problems[:10]}, f, indent=2, ensure_ascii=False)


def alert(label, problems):
    """Nachricht ueber die gleichen Kanaele wie die Zoom-Warnung (ntfy, Mail). Fehler hier brechen nichts ab."""
    try:
        sys.path.insert(0, "/opt/zoomrec")
        import notify_signout as ns
        ns.send(ns.env(), f"HSLU Wochen-Aufgaben ({label}) fehlgeschlagen",
                "Die Sonntags-Aufgaben konnten nicht (vollstaendig) angelegt werden:\n- " + "\n- ".join(problems[:8]) +
                "\nLog: journalctl -u hslu-tasks", True)
    except Exception as e:
        print(f"   Warnung konnte nicht gesendet werden: {e}", flush=True)


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    wk = target_week(args)
    label = weeks.label(wk) if wk else "?"
    created, problems = [0], []
    try:
        run(args, created, problems)
    except Exception as e:                                   # z. B. Token fehlt, Todoist nicht erreichbar
        problems.append(str(e)[:200])
    if dry:
        return
    write_status(not problems, label, created[0], problems)
    if problems:
        print("\nPROBLEME:\n- " + "\n- ".join(problems), flush=True)
        alert(label, problems)
        sys.exit(1)


def run(args, created_box, problems):
    dry = "--dry-run" in args
    keyword = args[args.index("--subject") + 1] if "--subject" in args else ""
    wk = target_week(args)
    if not wk:
        print("Keine Schulwoche erkannt (ausserhalb des Semesters). Mit --week N angeben.")
        return
    label, mon = weeks.label(wk), monday_of(wk)
    print(f"Aufgaben fuer {label} ({mon:%d.%m.}-{mon + timedelta(days=6):%d.%m.%Y})" + (" [Trockenlauf]" if dry else ""), flush=True)
    state = load_state()
    td = None if dry else Todoist()
    project_id = None if dry else td.project()
    existing = None if dry else td.open_titles(project_id)
    for subject, dirs in sorted(nlm.subjects_on_disk().items()):
        if keyword and keyword.lower() not in subject.lower():
            continue
        done_key = f"_fertig|{subject}|{label}"
        if not dry and done_key in state and "--force" not in args:
            print(f"\n=== {subject}: {label} schon angelegt (mit --force trotzdem neu)", flush=True)
            continue                                         # Gemini formuliert jedes Mal anders: nie zweimal pro Woche
        material = material_for(subject, dirs, wk)
        if not material:
            print(f"\n=== {subject}: kein Material fuer {label}", flush=True)
            continue
        print(f"\n=== {subject}: {len(material) // 1000} k Zeichen Material", flush=True)
        try:
            tasks = ask_gemini(subject, wk, material)
        except RuntimeError as e:
            print(f"   FEHLER: {e}", flush=True)
            problems.append(f"{subject}: {str(e)[:120]}")
            continue
        if not tasks:
            print("   keine konkreten Aufgaben", flush=True)
        section_id = None
        for t in tasks:
            title, note = str(t["title"]).strip(), str(t.get("note") or "").strip()
            due = clean_due(t.get("due"), mon)
            key = hashlib.sha1(f"{subject}|{label}|{title.lower()}".encode()).hexdigest()
            line = f"   - {title}" + (f"  (bis {due})" if due else "")
            if dry:
                print(line + (f"\n       {note}" if note else ""), flush=True)
                continue
            if key in state or title.lower() in existing:
                print(line + "  [schon vorhanden]", flush=True)
                continue
            try:
                section_id = section_id or td.section(project_id, subject.replace("_", " "))
                state[key] = td.add(project_id, section_id, title, note, due, label)
            except RuntimeError as e:
                print(f"   FEHLER: {e}", flush=True)
                problems.append(f"{subject}: {str(e)[:120]}")
                break
            existing.add(title.lower())
            save_state(state)
            created_box[0] += 1
            print(line, flush=True)
        if not dry and tasks and not any(pr.startswith(subject + ":") for pr in problems):
            state[done_key] = datetime.now().isoformat(timespec="seconds")
            save_state(state)
    print(f"\nFertig. {created_box[0]} neue Aufgabe(n) in Todoist." if not dry else "\nFertig (nichts angelegt).")


if __name__ == "__main__":
    main()
