import os
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv
from pypdf import PdfReader

from scraper import HSLUScraper
from transcriber import Transcriber
from llm_processor import LLMProcessor
from google_integration import GoogleWorkspace

load_dotenv()

def extract_pdf_text(pdf_path, max_pages=30):
    """Liest Text aus einer PDF-Datei für die KI-Analyse aus."""
    try:
        reader = PdfReader(pdf_path)
        text = []
        for i, page in enumerate(reader.pages[:max_pages]):
            p_text = page.extract_text()
            if p_text:
                text.append(f"--- Seite {i+1} ---\n{p_text}")
        return "\n".join(text)
    except Exception as e:
        print(f"   [PDF-Parser] Hinweis zu {os.path.basename(pdf_path)}: {e}")
        return ""

def weekly_job():
    now = datetime.now()
    week_str = now.strftime("Woche_%W_%Y-%m-%d")
    print("\n" + "=" * 70)
    print(f"STARTE VOLLAUTONOMEN HSLU-STUDIENASSISTENTEN: {week_str}")
    print(f"Zeitstempel: {now.strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 70)

    # 1. Module initialisieren
    scraper = HSLUScraper()
    transcriber = Transcriber()
    llm = LLMProcessor()
    
    gworkspace = None
    try:
        gworkspace = GoogleWorkspace()
        print("[Google Drive] Erfolgreich verbunden!")
    except Exception as e:
        print(f"[Google Drive] Hinweis: {e}")

    # 2. HSLU Scraper ausführen: Alle Kurse, Unterlagen und To-Dos erfassen
    results = scraper.login_and_download(week_str)
    courses_data = results.get("courses_data", [])
    todos = results.get("todos", [])
    
    print(f"\n[Scraping Fertig] {len(courses_data)} Kurse gescannt, {len(todos)} globale To-Dos gefunden.")

    # 3. Google Drive Wochenordner anlegen (z.B. 'Woche_40_2026-09-30')
    drive_week_folder_id = None
    if gworkspace:
        try:
            drive_week_folder_id = gworkspace.create_folder(week_str)
            print(f"[Google Drive] Neuer Wochenordner angelegt: '{week_str}' (ID: {drive_week_folder_id})")
        except Exception as e:
            print(f"[Google Drive] Ordnererstellung fehlgeschlagen: {e}")

    # 4. Pro Fach (Kurs) verarbeiten: Unterlagen, Transkripte & Dossier
    for c in courses_data:
        course_title = c["title"]
        clean_name = c["clean_name"]
        files = c.get("files", [])
        videos = c.get("videos", [])
        page_text = c.get("text", "")
        
        print("\n" + "-" * 60)
        print(f"VERARBEITE MODUL: {course_title}")
        print(f"Heruntergeladene Dateien: {len(files)} | Gefundene Videos: {len(videos)}")
        print("-" * 60)

        # A. Google Drive Fachordner innerhalb des Wochenordners anlegen
        course_folder_id = None
        if gworkspace and drive_week_folder_id:
            try:
                course_folder_id = gworkspace.create_folder(clean_name, parent_id=drive_week_folder_id)
                print(f" -> Fach-Ordner in Drive angelegt: '{clean_name}'")
            except Exception as e:
                print(f" -> Fehler beim Erstellen des Fachordners: {e}")

        # B. Text aus allen heruntergeladenen PDFs extrahieren
        pdf_corpus = ""
        for pdf in files:
            if pdf.lower().endswith(".pdf"):
                print(f" -> Lese PDF-Inhalt: {os.path.basename(pdf)}...")
                pdf_text = extract_pdf_text(pdf)
                if pdf_text:
                    pdf_corpus += f"\n\n=== DOKUMENT: {os.path.basename(pdf)} ===\n" + pdf_text

        # C. Videos / Audios verarbeiten und transkribieren
        transcript_corpus = ""
        for v in videos:
            v_url = v.get("url", "")
            v_title = v.get("text", "Vorlesungsvideo")
            # Falls lokale Videodatei heruntergeladen wurde
            if os.path.exists(v_url):
                print(f" -> Extrahiere Audio & transkribiere: {v_title}...")
                audio = transcriber.extract_audio(v_url)
                if audio:
                    t_text = transcriber.transcribe(audio)
                    transcript_corpus += f"\n=== TRANSKRIPT: {v_title} ===\n" + t_text
            else:
                transcript_corpus += f"\nReferenziertes Video: {v_title} ({v_url})\n"

        if not transcript_corpus:
            transcript_corpus = f"Vorlesungsbesprechung und Aufzeichnungen zu {course_title}."

        # D. Gefundene modulspezifische To-Dos zusammenstellen
        mod_todos = [td for td in todos if clean_name.lower() in td.lower() or "abgabe" in td.lower()]
        todo_text = "\n".join([f"- {t}" for t in mod_todos])

        # E. Gemini KI-Synthese: Dossier mit Stoff, Prüfungsfragen & Musterlösungen generieren
        combined_source_text = f"Modulbeschrieb & Inhaltsseite:\n{page_text[:4000]}\n\nPDF-Skripte & Folien:\n{pdf_corpus[:15000]}"
        
        print(f" -> Generiere umfassendes MEP-Dossier mit Gemini 2.5 Flash...")
        dossier = llm.generate_dossier(
            week_title=f"{week_str} - {course_title}",
            transcript_text=transcript_corpus,
            pdf_text_content=combined_source_text
        )

        # F. Dossier lokal speichern
        dossier_filename = f"Dossier_{clean_name}_{week_str}.md"
        local_dossier_path = os.path.join(c["dir"], dossier_filename)
        with open(local_dossier_path, "w", encoding="utf-8") as f:
            f.write(dossier)
        print(f" -> Lokal gespeichert: {local_dossier_path}")

        # G. In Google Drive hochladen (Dossier als natives Google Doc + Originaldateien als Backup!)
        target_upload_folder = course_folder_id or drive_week_folder_id
        if gworkspace and target_upload_folder:
            # 1. Dossier als echtes Google Doc (perfekt für NotebookLM & sofortiges Lesen)
            doc_id = gworkspace.upload_file(local_dossier_path, target_upload_folder, as_google_doc=True)
            print(f" -> [Google Docs] Dossier hochgeladen! Doc-ID: {doc_id}")

            # 2. Original-PDFs als Referenz hochladen
            for pdf_file in files:
                gworkspace.upload_file(pdf_file, target_upload_folder, as_google_doc=False)

    print("\n" + "=" * 70)
    print(f"WÖCHENTLICHER DURCHLAUF FÜR {week_str} ERFOLGREICH BEENDET!")
    print(f"Alle Fächer wurden analysiert, Dossiers als Google Docs erstellt und in Drive abgelegt.")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    print("HSLU KI-Studienassistent ist aktiv.")
    print("Der wöchentliche Durchlauf startet jeden Sonntag um 18:00 Uhr automatisch.")
    print("Möchtest du einen Testdurchlauf jetzt sofort starten? (Führe weekly_job() aus).")
    
    # Scheduler: Jeden Sonntag um 18:00 Uhr
    schedule.every().sunday.at("18:00").do(weekly_job)
    
    # Für manuelle Ausführung bei Start (kann einkommentiert werden)
    # weekly_job()
    
    print("Warteschleife aktiv...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("Beendet.")
