import os
from dotenv import load_dotenv
import schedule
import time
from datetime import datetime

from scraper import HSLUScraper
from transcriber import Transcriber
from llm_processor import LLMProcessor
from google_integration import GoogleWorkspace

load_dotenv()

def weekly_job():
    now = datetime.now()
    week_str = now.strftime("Woche_%W_%Y-%m-%d")
    print(f"\n========================================================")
    print(f"STARTE WÖCHENTLICHEN HSLU-WORKFLOW: {week_str} ({now.strftime('%d.%m.%Y %H:%M')})")
    print(f"========================================================")
    
    # 1. Module initialisieren
    scraper = HSLUScraper()
    transcriber = Transcriber()
    llm = LLMProcessor()
    
    # Google Workspace Init (falls credentials.json vorhanden ist)
    gworkspace = None
    if os.path.exists('credentials.json'):
        try:
            gworkspace = GoogleWorkspace()
            print("[Google Workspace] Erfolgreich verbunden.")
        except Exception as e:
            print(f"[Google Workspace] Authentifizierungs-Hinweis: {e}")
    else:
        print("[Google Workspace] Keine credentials.json gefunden. Speichere lokal in downloads/.")

    # 2. HSLU ILIAS scannen
    scraped_data = scraper.login_and_download(week_str)
    
    courses = scraped_data.get("courses", [])
    todos = scraped_data.get("todos", [])
    
    print(f"\nGefundene Kurse für diese Woche: {len(courses)}")
    print(f"Gefundene offene To-Dos / Abgaben: {len(todos)}")
    
    # Lokalen Wochenordner anlegen
    local_week_dir = os.path.join("downloads", week_str)
    os.makedirs(local_week_dir, exist_ok=True)
    
    # Google Drive Wochenordner anlegen (falls aktiv)
    drive_folder_id = None
    if gworkspace:
        try:
            drive_folder_id = gworkspace.create_folder(week_str)
            print(f"[Google Drive] Wochenordner '{week_str}' erstellt (ID: {drive_folder_id})")
        except Exception as e:
            print(f"[Google Drive] Fehler beim Erstellen des Ordners: {e}")

    # 3. Dossiers für die belegten Module erstellen
    # Falls keine Kurse direkt übergeben wurden, Standardmodule nehmen
    if not courses:
        courses = [
            {"title": "I.BA_DBS.H2601 (Datenbanksysteme)", "url": ""},
            {"title": "I.BA_ASTAT_MM.H26 (Applied Statistics)", "url": ""},
            {"title": "I.BA_KRR.H2601 (Logical Reasoning in AI)", "url": ""},
            {"title": "I.BA_VSK_MM.H2601 (Verteilte Systeme)", "url": ""},
            {"title": "TA.BA_PREN1.H2601 (Projekt Produktentwicklung 1)", "url": ""},
            {"title": "I.BA_AEDCIT.H2601 (Academic English)", "url": ""}
        ]

    for course in courses:
        course_name = course.get("title", "Modul")
        clean_name = course_name.split(".")[1] if "." in course_name else course_name
        clean_name = clean_name.replace("/", "_").replace(" ", "_")
        
        print(f"\n[Verarbeitung] Erstelle Dossier für: {course_name}...")
        
        # Audio / Transkription falls Videos vorhanden
        course_videos = course.get("videos", [])
        transcript_text = ""
        for v in course_videos:
            audio_path = transcriber.extract_audio(v)
            if audio_path:
                t = transcriber.transcribe(audio_path)
                transcript_text += f"\n--- Transkript: {os.path.basename(v)} ---\n" + t
                
        if not transcript_text:
            transcript_text = f"Vorlesungsinhalte und Diskussionen für {course_name} in Kalenderwoche {now.strftime('%W')}."

        # To-Dos für dieses Fach filtern
        relevant_todos = "\n".join([f"- {td}" for td in todos if clean_name.lower() in td.lower() or "abgabe" in td.lower()])

        # KI-Synthese via Gemini 2.5 Flash
        dossier_text = llm.generate_dossier(
            week_title=f"{week_str} - {course_name}",
            transcript_text=transcript_text,
            pdf_text_content=relevant_todos
        )
        
        # Lokal abspeichern
        local_file = os.path.join(local_week_dir, f"Dossier_{clean_name}.md")
        with open(local_file, "w", encoding="utf-8") as f:
            f.write(dossier_text)
        print(f" -> Lokal gespeichert: {local_file}")
        
        # In Google Drive als echtes Google Doc speichern (perfekt für NotebookLM)
        if gworkspace and drive_folder_id:
            try:
                doc_id = gworkspace.upload_file(local_file, drive_folder_id, as_google_doc=True)
                print(f" -> Als Google Doc in Drive abgelegt! (Doc-ID: {doc_id})")
            except Exception as e:
                print(f" -> Google Drive Export-Fehler: {e}")

    print(f"\n========================================================")
    print(f"WÖCHENTLICHER WORKFLOW FÜR {week_str} ERFOLGREICH BEENDET!")
    print(f"========================================================\n")

if __name__ == "__main__":
    print("HSLU KI-Studienassistent wurde gestartet.")
    print("Jeden Sonntag um 18:00 Uhr wird der Workflow autonom ausgeführt.")
    
    # Schedule definieren: Jeden Sonntag um 18:00 Uhr
    schedule.every().sunday.at("18:00").do(weekly_job)
    
    print("Warteschleife aktiv. Drücke Strg + C zum Beenden.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("Agent beendet.")
