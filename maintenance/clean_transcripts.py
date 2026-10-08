"""Macht aus Rohtranskripten (.txt) saubere, gut lesbare Dokumente (.md) und laedt sie als Google Doc nach Drive.

Bereinigt wird nur die Form: Fuellwoerter, Wiederholungen und Versprecher raus, Satzzeichen und Absaetze,
Kapitelueberschriften mit Zeitmarke. Inhalt und Fachbegriffe bleiben, nichts wird zusammengefasst oder erfunden.

  python maintenance/clean_transcripts.py              # alle Transkripte
  python maintenance/clean_transcripts.py ASTAT        # nur Pfade mit Stichwort
  python maintenance/clean_transcripts.py ASTAT --sync # danach als Google Doc nach <Fach>/Transkripte

Aus dem Projektroot starten. Vorhandene saubere Fassungen werden uebersprungen. Braucht GEMINI_API_KEY.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import time
import warnings

from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

SEGMENT_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s*$", re.M)
PROMPT = """Du bekommst einen Ausschnitt aus dem Rohtranskript einer Hochschulvorlesung (gesprochene Sprache, meist Deutsch).
Erstelle daraus eine saubere Lesefassung:
- Entferne Fuellwoerter (aeh, aem, also, ja, genau, okay), Wiederholungen, abgebrochene Saetze und Versprecher.
- Setze korrekte Satzzeichen und gliedere in sinnvolle Absaetze.
- Behalte den Inhalt, die Reihenfolge, Fachbegriffe, Zahlen, Formeln und Beispiele vollstaendig. NICHT zusammenfassen, nichts hinzufuegen, nichts erfinden.
- Organisatorisches ohne Lernstoff (Begruessung, Technikprobleme, Smalltalk) darf auf einen kurzen Satz gekuerzt werden.
- Schreibe Formeln und Code, wo erkennbar, in Markdown (z. B. `code`, $formel$).
- Beginne mit EINER kurzen Kapitelueberschrift im Format: ## <Titel>
Gib nur das Ergebnis aus, ohne Kommentar.

ROHTEXT:
"""


def find_transcripts(keyword):
    out = []
    for dp, _, fns in os.walk("downloads"):
        if dp.endswith("_chunks") or (keyword and keyword not in dp):
            continue
        for fn in fns:
            full = os.path.join(dp, fn)
            if (fn.lower().endswith(".txt") and not fn.startswith(("Dossier_", "Transkript_"))
                    and os.path.exists(os.path.splitext(full)[0] + ".mp3")):
                out.append(full)
    return sorted(out)


def split_segments(text):
    marks = list(SEGMENT_RE.finditer(text))
    if not marks:
        return [("00:00:00", text.strip())]
    segs = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        segs.append((m.group(1), text[m.end():end].strip()))
    return segs


def clean_segment(model, raw, retries=4):
    last = None
    for attempt in range(1, retries + 1):
        try:
            return model.generate_content(PROMPT + raw, request_options={"timeout": 600}).text.strip()
        except Exception as e:
            last = str(e).split("key=")[0][:200]
            print(f"   Versuch {attempt}/{retries} fehlgeschlagen: {last}", flush=True)
            time.sleep(15 * attempt)
    raise RuntimeError(f"Segment nicht bereinigbar: {last}")


def course_root(path):
    parts = path.split(os.sep)
    return os.sep.join(parts[:parts.index("Unterlagen")]) if "Unterlagen" in parts else os.path.dirname(path)


def main():
    keyword = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
    import google.generativeai as genai
    from main import clean_subject_name
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel(os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-3.5-flash"))

    made = []
    for txt in find_transcripts(keyword):
        base = os.path.splitext(os.path.basename(txt))[0]
        out_path = os.path.join(os.path.dirname(txt), f"Transkript_{base}.md")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            print(f"Vorhanden: {out_path}")
            continue
        with open(txt, "r", encoding="utf-8") as f:
            raw = f.read()
        course_dir = course_root(txt)
        subject = clean_subject_name(os.path.basename(course_dir))
        segments = split_segments(raw)
        print(f"\n=== {subject} - {base} | {len(segments)} Segmente", flush=True)
        parts = [f"# {subject} - {base}", f"*Bereinigtes Transkript. Quelle: Vorlesungsaufzeichnung, automatisch transkribiert und sprachlich geglaettet.*"]
        for i, (stamp, text) in enumerate(segments, 1):
            if not text:
                continue
            print(f"   Segment {i}/{len(segments)} ...", flush=True)
            cleaned = clean_segment(model, text)
            cleaned = re.sub(r"^##\s*", f"## [{stamp}] ", cleaned, count=1) if cleaned.startswith("##") else f"## [{stamp}]\n\n{cleaned}"
            parts.append(cleaned)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(parts) + "\n")
        made.append((out_path, course_dir))
        print(f"   Gespeichert: {out_path}", flush=True)

    if "--sync" in sys.argv and made:
        from google_integration import GoogleWorkspace
        from main import DriveSync
        gw = GoogleWorkspace()
        sync = DriveSync(gw)
        for path, course_dir in made:
            subject = clean_subject_name(os.path.basename(course_dir))
            folder = sync.folder("Transkripte", sync.folder(subject, None))
            local_root = os.path.join(course_dir, "Unterlagen")
            sync.upload(path, folder, f"{subject}/Transkripte/{os.path.basename(path)}", as_google_doc=True)
    print("\nFertig.")


if __name__ == "__main__":
    main()
