"""Erzeugt pro Fach und Schulwoche eine Audio-Vorlesung (ca. 20-35 Minuten) aus den Unterlagen der Woche.

Ablauf: Material der Woche (Transkripte, Dossiers, Notebooks, Folien) -> Vorlesungsskript (Gemini, 2 Teile)
-> Sprache (Google Cloud Text-to-Speech, Chirp 3 HD, Gelso-Projekt) -> MP3 -> Drive "<Fach>/Audio-Vorlesungen".
Das Skript wird als Quelle "SWnn - Vorlesungsskript (Audio)" in das NotebookLM-Notebook aufgenommen.

  python maintenance/weekly_audio.py --dry-run                  # zeigt, fuer welche Wochen Audio entstehen wuerde
  python maintenance/weekly_audio.py --subject Applied --week 3 # eine bestimmte Vorlesung
  python maintenance/weekly_audio.py --max 3                    # hoechstens 3 neue Vorlesungen pro Lauf (Standard 3)

Aus dem Projektroot starten. Zustand: audio_state.json. Kosten: Cloud TTS (Gelso-Projekt) + Gemini-Skript.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base64
import hashlib
import json
import re
import subprocess
import time
import warnings
from datetime import datetime

import requests
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

import sync_notebooklm_api as nlm
import weeks

BASE = nlm.BASE
STATE_FILE = os.path.join(BASE, "audio_state.json")
AUDIO_DIR = os.path.join(BASE, "downloads", "audio")
VOICE = os.environ.get("AUDIO_VOICE", "de-DE-Chirp3-HD-Charon")
MODEL = os.environ.get("GEMINI_LECTURE_MODEL", "gemini-3.5-flash")
MIN_MATERIAL_WORDS = 1200      # weniger Material traegt keine 20 Minuten
MIN_MINUTES = 20
TTS_CHUNK_BYTES = 4500         # Limit der API: 5000 Bytes pro Anfrage
CORPUS_CAP = 140_000           # Zeichen Material pro Vorlesung

PROMPT_COMMON = """Du bist Dozent und haeltst eine Vorlesung, die als Audio aufgenommen wird. Studierende hoeren sie anstelle der Praesenzvorlesung.
Fach: {subject}. Schulwoche: {week}.

Regeln:
- Stuetze dich ausschliesslich auf das MATERIAL unten. Erfinde keine Fakten, Zahlen oder Aussagen des Dozenten. Allgemein bekannte Erklaerungen und Beispiele zum Verstaendnis sind erlaubt.
- Gesprochene Sprache, Deutsch, Du-Form, lebendig und klar. Erklaere Schritt fuer Schritt, mit Beispielen aus dem Material.
- Nur reiner Fliesstext in Absaetzen (Leerzeile zwischen den Absaetzen). KEINE Markdown-Zeichen, keine Aufzaehlungszeichen, keine Ueberschriften mit #, keine Klammern mit Regieanweisungen.
- Formeln, Code und Zahlen so formulieren, wie man sie spricht. Code nicht Zeichen fuer Zeichen vorlesen, sondern die Idee und das Ergebnis erklaeren.
- Lasse Organisatorisches weg (Aufzeichnungen, Abgabetermine, Raeume, Anwesenheit, ILIAS, Pruefungsmodalitaeten). Nur Fachinhalt zaehlt.
- Gib nur den gesprochenen Text aus.

"""

PART1 = PROMPT_COMMON + """AUFGABE: Teil 1 von 2 des Vorlesungsskripts. Schreibe etwa 1800 bis 2100 Woerter (nicht mehr als 2300).
Inhalt: Begruessung, Ueberblick ueber die Lernziele der Woche, danach die ersten drei Kapitel. Jedes Kapitel beginnt mit einem gesprochenen Kapitelhinweis (zum Beispiel "Kapitel eins: ...") und endet mit einem kurzen Zwischenfazit. Beende den Text mit einem Satz, der ankuendigt, dass es gleich weitergeht.

MATERIAL:
{corpus}
"""

PART2 = PROMPT_COMMON + """AUFGABE: Teil 2 von 2 des Vorlesungsskripts. Schreibe etwa 1800 bis 2100 Woerter (nicht mehr als 2300).
Bereits besprochen (Teil 1 endete so): {tail}
Inhalt: Beginne ohne neue Begruessung direkt mit dem naechsten Kapitel und fuehre die Kapitel vier bis sechs aus (wieder mit Kapitelhinweis und Zwischenfazit). Danach: fuenf Selbsttest-Fragen, jede mit gesprochener Musterantwort, eine Zusammenfassung der wichtigsten Merksaetze der Woche und eine kurze Verabschiedung.

MATERIAL:
{corpus}
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


def pdf_text(path):
    try:
        from main import extract_pdf_text
        return extract_pdf_text(path, max_pages=40) or ""
    except Exception:
        return ""


def materials_by_week():
    """{(subject, week): [(anzeigename, pfad, art), ...]} nur Wochen 1..20."""
    out = {}
    for subject, dirs in nlm.subjects_on_disk().items():
        for name, path, kind in nlm.collect(dirs):
            wk = int(name[2:4]) if name.startswith("SW") and name[2:4].isdigit() else 0
            if not wk:                                     # SW00 = allgemein, kein Wochenbezug
                continue
            if "Vorlesungsskript" in name:
                continue                                   # eigene Ausgabe nie als Material nehmen
            out.setdefault((subject, wk), []).append((name, path, kind))
    return out


def build_corpus(items):
    """Text der Woche: Transkripte zuerst (was gesagt wurde), dann Folien/Notebooks, dann Dossiers."""
    order = {"Transkript": 0, "Notebook": 1, "Dossier": 2}
    def rank(it):
        for key, val in order.items():
            if f" - {key}" in it[0]:
                return val
        return 3
    parts, total = [], 0
    for name, path, kind in sorted(items, key=rank):
        if kind == "text":
            with open(path, "r", encoding="utf-8") as f:
                body = f.read()
        elif kind == "notebook":
            body = nlm.notebook_text(path)
        elif path.lower().endswith(".pdf"):
            body = pdf_text(path)
        else:
            body = ""
        body = body.strip()
        if not body:
            continue
        body = body[:45_000]
        parts.append(f"=== {name} ===\n{body}")
        total += len(body)
        if total >= CORPUS_CAP:
            break
    return "\n\n".join(parts)[:CORPUS_CAP]


def fingerprint(items):
    h = hashlib.sha1()
    for name, path, _ in sorted(items):
        h.update(f"{name}|{os.path.getsize(path)}".encode())
    return h.hexdigest()


def gemini(prompt, retries=4):
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel(MODEL)
    last = None
    for attempt in range(1, retries + 1):
        try:
            return model.generate_content(prompt, request_options={"timeout": 900}).text.strip()
        except Exception as e:
            last = str(e).split("key=")[0][:200]
            time.sleep(20 * attempt)
    raise RuntimeError(f"Gemini fehlgeschlagen: {last}")


def clean_script(text):
    text = re.sub(r"[*#_`]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_script(subject, week, corpus):
    p1 = clean_script(gemini(PART1.format(subject=subject, week=week, corpus=corpus)))
    tail = " ".join(p1.split()[-90:])
    p2 = clean_script(gemini(PART2.format(subject=subject, week=week, corpus=corpus, tail=tail)))
    return p1 + "\n\n" + p2


def split_for_tts(text):
    chunks, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        for sent in re.split(r"(?<=[.!?])\s+", para.strip()):
            if not sent:
                continue
            if len((cur + " " + sent).encode("utf-8")) > TTS_CHUNK_BYTES:
                if cur:
                    chunks.append(cur)
                cur = sent
            else:
                cur = (cur + " " + sent).strip()
        cur += "\n"
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def tts(api, text, retries=5):
    body = {"input": {"text": text}, "voice": {"languageCode": "de-DE", "name": VOICE}, "audioConfig": {"audioEncoding": "MP3"}}
    for attempt in range(1, retries + 1):
        r = requests.post("https://texttospeech.googleapis.com/v1/text:synthesize", headers=api.headers({"Content-Type": "application/json"}),
                          json=body, timeout=180)
        if r.ok:
            return base64.b64decode(r.json()["audioContent"])
        if r.status_code in (429, 500, 503) and attempt < retries:
            time.sleep(10 * attempt)
            continue
        raise RuntimeError(f"TTS {r.status_code}: {r.text[:200]}")


def synthesize(api, script, out_mp3):
    chunks = split_for_tts(script)
    work = out_mp3 + "_parts"
    os.makedirs(work, exist_ok=True)
    listing = []
    for i, chunk in enumerate(chunks):
        part = os.path.join(work, f"p{i:03d}.mp3")
        if not (os.path.exists(part) and os.path.getsize(part) > 0):
            with open(part, "wb") as f:
                f.write(tts(api, chunk))
        listing.append(part)
        print(f"      Sprachabschnitt {i + 1}/{len(chunks)}", flush=True)
    lst = os.path.join(work, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(f"file '{p}'" for p in listing))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-ac", "1",
                    "-c:a", "libmp3lame", "-b:a", "64k", out_mp3], check=True)
    for f in os.listdir(work):
        os.remove(os.path.join(work, f))
    os.rmdir(work)


def duration_min(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip()) / 60
    except ValueError:
        return 0.0


def upload_drive(subject, mp3, script_md):
    try:
        from google_integration import GoogleWorkspace
        gw = GoogleWorkspace()
        folder = gw.get_or_create_folder("Audio-Vorlesungen", parent_id=gw.get_or_create_folder(subject))
        gw.upload_file(mp3, folder, as_google_doc=False)
        gw.upload_file(script_md, folder, as_google_doc=True)
        return True
    except Exception as e:
        print(f"      Drive-Upload fehlgeschlagen (Datei bleibt lokal): {str(e)[:160]}", flush=True)
        return False


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    force = "--force" in args
    keyword = args[args.index("--subject") + 1] if "--subject" in args else ""
    only_week = int(args[args.index("--week") + 1]) if "--week" in args else None
    limit = int(args[args.index("--max") + 1]) if "--max" in args else 3
    state = load_state()
    todo = []
    for (subject, wk), items in sorted(materials_by_week().items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if keyword and keyword.lower() not in subject.lower():
            continue
        if only_week and wk != only_week:
            continue
        fp = fingerprint(items)
        key = f"{subject}|{weeks.label(wk)}"
        known = state.get(key)
        age_days = (datetime.now() - datetime.fromisoformat(known["made"])).days if known else None
        if known and not force and (known["hash"] == fp or age_days < 3):
            continue
        todo.append((subject, wk, items, fp, key))
    print(f"{len(todo)} Vorlesung(en) faellig (Maximum pro Lauf: {limit}).", flush=True)
    if dry:
        for subject, wk, items, _, _ in todo:
            print(f"   {weeks.label(wk)} {subject}: {len(items)} Quellen")
        return
    if not todo:
        return
    api = nlm.Api()
    for subject, wk, items, fp, key in todo[:limit]:
        print(f"\n=== {weeks.label(wk)} {subject} ({len(items)} Quellen)", flush=True)
        corpus = build_corpus(items)
        words = len(corpus.split())
        if words < MIN_MATERIAL_WORDS:
            print(f"   zu wenig Material ({words} Woerter), uebersprungen", flush=True)
            state[key] = {"hash": fp, "made": datetime.now().isoformat(), "minutes": 0, "skipped": "zu wenig Material"}
            save_state(state)
            continue
        out_dir = os.path.join(AUDIO_DIR, subject)
        os.makedirs(out_dir, exist_ok=True)
        base = f"{weeks.label(wk)}_{subject}"
        script_md = os.path.join(out_dir, f"Vorlesungsskript_{weeks.label(wk)}.md")
        mp3 = os.path.join(out_dir, f"{base}_Vorlesung.mp3")
        try:
            print("   Skript schreiben ...", flush=True)
            script = make_script(subject, wk, corpus)
            with open(script_md, "w", encoding="utf-8") as f:
                f.write(f"# Vorlesungsskript {weeks.label(wk)} - {subject}\n\n{script}\n")
            print(f"   Skript: {len(script.split())} Woerter. Sprache erzeugen ...", flush=True)
            synthesize(api, script, mp3)
        except Exception as e:
            print(f"   FEHLER: {str(e)[:200]}", flush=True)
            continue
        minutes = duration_min(mp3)
        ok = upload_drive(subject, mp3, script_md)
        state[key] = {"hash": fp, "made": datetime.now().isoformat(), "minutes": round(minutes, 1),
                      "mp3": os.path.relpath(mp3, BASE), "drive": ok}
        save_state(state)
        warn = "" if minutes >= MIN_MINUTES else f"  (kuerzer als {MIN_MINUTES} Minuten, Material knapp)"
        print(f"   Fertig: {minutes:.1f} Minuten{warn}", flush=True)
    print("\nFertig.")


if __name__ == "__main__":
    main()
