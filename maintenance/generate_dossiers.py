"""Erzeugt aus vorhandenen Transkripten (.txt) und den passenden Folien (PDF) je ein Lern-Dossier (.md).

  python maintenance/generate_dossiers.py              # alle Transkripte
  python maintenance/generate_dossiers.py ASTAT        # nur Pfade mit Stichwort
  python maintenance/generate_dossiers.py ASTAT --sync # danach als Google Doc nach Drive

Aus dem Projektroot starten. Vorhandene Dossiers werden uebersprungen. Braucht GEMINI_API_KEY.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import time

from dotenv import load_dotenv

load_dotenv()
MAX_PDF_CHARS = 60000
WEEK_RE = re.compile(r"(?:SW|Week\s*)0*(\d+)", re.I)


def week_of(path):
    m = WEEK_RE.search(path)
    return int(m.group(1)) if m else None


def notebook_text(path):
    """Markdown- und Code-Zellen eines Jupyter-Notebooks (ohne Ausgaben)."""
    import json
    try:
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
    except Exception:
        return ""
    parts = []
    for cell in nb.get("cells", []):
        src = "".join(cell.get("source", []))
        if src.strip():
            fence = chr(96) * 3
            parts.append(src if cell.get("cell_type") == "markdown" else f"{fence}python{chr(10)}{src}{chr(10)}{fence}")
    return (chr(10) * 2).join(parts)


def find_transcripts(keyword):
    out = []
    for dp, _, fns in os.walk("downloads"):
        if dp.endswith("_chunks") or (keyword and keyword not in dp):
            continue
        for fn in fns:
            full = os.path.join(dp, fn)
            # nur Transkripte: .txt mit gleichnamiger MP3 daneben (keine Datensaetze oder Lizenztexte)
            if fn.lower().endswith(".txt") and not fn.startswith("Dossier_") and os.path.exists(os.path.splitext(full)[0] + ".mp3"):
                out.append(full)
    return sorted(out)


def course_root(path):
    parts = path.split(os.sep)
    return os.sep.join(parts[:parts.index("Unterlagen")]) if "Unterlagen" in parts else os.path.dirname(path)


def pdf_corpus(course_dir, week):
    from main import extract_pdf_text
    chunks, total = [], 0
    for dp, dns, fns in os.walk(os.path.join(course_dir, "Unterlagen")):
        dns[:] = [d for d in dns if d not in {".venv", "venv", "__pycache__", ".ipynb_checkpoints", "site-packages"}]
        for fn in sorted(fns):
            full = os.path.join(dp, fn)
            low = fn.lower()
            if not low.endswith((".pdf", ".ipynb")) or week is None or week_of(full) != week:
                continue
            text = extract_pdf_text(full) if low.endswith(".pdf") else notebook_text(full)
            if text:
                chunks.append(f"\n\n=== DOKUMENT: {fn} ===\n{text}")
                total += len(text)
            if total > MAX_PDF_CHARS:
                return "".join(chunks)
    return "".join(chunks)


def main():
    keyword = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
    from llm_processor import LLMProcessor
    from main import clean_subject_name
    llm = LLMProcessor()
    made = []
    for txt in find_transcripts(keyword):
        base = os.path.splitext(os.path.basename(txt))[0]
        out_path = os.path.join(os.path.dirname(txt), f"Dossier_{base}.md")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            print(f"Vorhanden: {out_path}")
            continue
        with open(txt, "r", encoding="utf-8") as f:
            transcript = f.read()
        if len(transcript.split()) < 500:
            print(f"Zu kurz, uebersprungen: {txt}")
            continue
        course_dir = course_root(txt)
        subject = clean_subject_name(os.path.basename(course_dir))
        week = week_of(txt)
        corpus = pdf_corpus(course_dir, week)
        title = f"{subject} - {base}" + (f" (SW{week:02d})" if week else "")
        print(f"\n=== {title} | Transkript {len(transcript.split())} Woerter | Folien {len(corpus)} Zeichen", flush=True)
        dossier = llm.generate_dossier(week_title=title, transcript_text=transcript,
                                       pdf_text_content=corpus, subject_code=os.path.basename(course_dir))
        if dossier.startswith("# Dossier konnte nicht erstellt werden"):
            print("   FEHLER:", dossier[:200], flush=True)
            continue
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(dossier)
        made.append((out_path, course_dir))
        print(f"   Dossier gespeichert: {out_path} ({len(dossier.split())} Woerter)", flush=True)
        time.sleep(15)

    if "--sync" in sys.argv and made:
        from google_integration import GoogleWorkspace
        from main import DriveSync
        gw = GoogleWorkspace()
        sync = DriveSync(gw)
        for path, course_dir in made:
            local_root = os.path.join(course_dir, "Unterlagen")
            rel_dir = os.path.relpath(os.path.dirname(path), local_root)
            subject = clean_subject_name(os.path.basename(course_dir))
            parent = sync.folder_path(sync.folder("Unterlagen", sync.folder(subject, None)), rel_dir)
            sync.upload(path, parent, f"{subject}/{os.path.relpath(path, local_root)}", as_google_doc=True)
    print("\nFertig.")


if __name__ == "__main__":
    main()
