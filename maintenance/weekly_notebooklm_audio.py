"""Ein NotebookLM-Notebook pro Fach und Schulwoche, dazu die Audio-Zusammenfassung von NotebookLM selbst.

Die API erlaubt nur eine Audio-Zusammenfassung pro Notebook. Deshalb entsteht "HSLU - <Fach> - SWnn" mit den
Quellen genau dieser Woche; die Audio-Zusammenfassung erzeugt NotebookLM (Studio, Audio-Zusammenfassung).

  python maintenance/weekly_notebooklm_audio.py --dry-run
  python maintenance/weekly_notebooklm_audio.py --subject Applied --week 3
  python maintenance/weekly_notebooklm_audio.py --max 3        # hoechstens 3 neue Wochen-Notebooks pro Lauf
  --no-total                                                   # Gesamt-Audio pro Fach nicht aktualisieren

Aus dem Projektroot starten. Zustand: weekly_nlm_state.json. Nur Wochen bis zur aktuellen Schulwoche.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hashlib
import json
from datetime import datetime

import sync_notebooklm_api as nlm
import weeks

STATE_FILE = os.path.join(nlm.BASE, "weekly_nlm_state.json")
MIN_SOURCES = 2
FOCUS = ("Erklaere die Inhalte dieser Schulwoche wie eine ausfuehrliche Vorlesung: alle Themen der Reihe nach, "
         "mit Beispielen und Zwischenfazits, so ausfuehrlich und lang wie moeglich. Nur Fachinhalt, "
         "kein Organisatorisches (Termine, Abgaben, Raeume, Aufzeichnungen).")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def week_items():
    out = {}
    for subject, dirs in nlm.subjects_on_disk().items():
        for name, path, kind in nlm.collect(dirs):
            if "Vorlesung" in name and "(Audio)" in name:
                continue                                   # eigene Pilot-Dateien nicht als Quelle
            wk = int(name[2:4]) if name.startswith("SW") and name[2:4].isdigit() else 0
            if wk:
                out.setdefault((subject, wk), []).append((name, path, kind))
    return out


TOTAL_FOCUS = ("Fasse das gesamte Fach bis heute wie eine zusammenhaengende Vorlesung zusammen: Woche fuer Woche der Reihe nach, "
               "mit den wichtigsten Konzepten und Zusammenhaengen, so ausfuehrlich wie moeglich. Kein Organisatorisches.")


def refresh_totals(get_api, state, keyword, dry):
    """Gesamt-Audio pro Fach im Notebook "HSLU - <Fach>": bei neuem Material (hoechstens alle 3 Tage) alte loeschen, neu erzeugen."""
    notebooks = nlm.load_state().get("notebooks", {})
    for subject, dirs in sorted(nlm.subjects_on_disk().items()):
        nb = notebooks.get(subject)
        if not nb or (keyword and keyword.lower() not in subject.lower()):
            continue
        items = [it for it in nlm.collect(dirs) if "(Audio)" not in it[0]]
        h = hashlib.sha1("|".join(f"{n}{os.path.getsize(p)}" for n, p, _ in sorted(items)).encode()).hexdigest()
        known = state.get(f"GESAMT|{subject}")
        if known and (known["hash"] == h or (datetime.now() - datetime.fromisoformat(known["made"])).days < 3):
            continue
        print(f"\n=== Gesamt-Audio {subject} ({len(items)} Quellen)", flush=True)
        if dry:
            continue
        api = get_api()
        api.call("DELETE", f"{nlm.API}/notebooks/{nb}/audioOverviews/default")
        r = api.call("POST", f"{nlm.API}/notebooks/{nb}/audioOverviews", extra={"Content-Type": "application/json"},
                     json={"generationOptions": {"episodeFocus": TOTAL_FOCUS, "languageCode": "de"}})
        print(f"   {'gestartet' if r.ok else 'FEHLER ' + r.text[:160]}", flush=True)
        if r.ok:
            state[f"GESAMT|{subject}"] = {"hash": h, "made": datetime.now().isoformat()}
            save_state(state)


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    keyword = args[args.index("--subject") + 1] if "--subject" in args else ""
    only_week = int(args[args.index("--week") + 1]) if "--week" in args else None
    limit = int(args[args.index("--max") + 1]) if "--max" in args else 3
    current = weeks.week_of_date(datetime.now()) or 0
    state = load_state()
    apis = []

    def get_api():
        if not apis:
            apis.append(nlm.Api())
        return apis[0]

    todo = []
    for (subject, wk), items in sorted(week_items().items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if keyword and keyword.lower() not in subject.lower():
            continue
        if only_week and wk != only_week:
            continue
        if not only_week and wk > current:
            continue
        if f"{subject}|{weeks.label(wk)}" in state or len(items) < MIN_SOURCES:
            continue
        todo.append((subject, wk, items))
    print(f"{len(todo)} Wochen-Notebook(s) faellig (Maximum pro Lauf: {limit}).", flush=True)
    for subject, wk, items in todo[:limit]:
        title = f"HSLU - {subject} - {weeks.label(wk)}"
        print(f"\n=== {title}: {len(items)} Quellen", flush=True)
        if dry:
            for name, _, kind in items:
                print(f"   [{kind}] {name}")
            continue
        api = get_api()
        nb = api.create_notebook(title)
        added = 0
        for name, path, kind in items:
            try:
                if kind == "file":
                    api.add_file(nb, path, name)
                else:
                    body = open(path, encoding="utf-8").read() if kind == "text" else nlm.notebook_text(path)
                    if not body.strip():
                        continue
                    api.add_text(nb, name, body)
                added += 1
            except Exception as e:
                print(f"   FEHLER bei {name}: {str(e)[:140]}", flush=True)
        r = api.call("POST", f"{nlm.API}/notebooks/{nb}/audioOverviews", extra={"Content-Type": "application/json"},
                     json={"generationOptions": {"episodeFocus": FOCUS, "languageCode": "de"}})
        ok = r.ok
        print(f"   {added} Quellen, Audio-Zusammenfassung: {'gestartet' if ok else 'FEHLER ' + r.text[:200]}", flush=True)
        state[f"{subject}|{weeks.label(wk)}"] = {"notebook": nb, "sources": added, "audio": ok, "made": datetime.now().isoformat()}
        save_state(state)
    if not only_week and "--no-total" not in args:
        refresh_totals(get_api, state, keyword, dry)
    print("\nFertig.")


if __name__ == "__main__":
    main()
