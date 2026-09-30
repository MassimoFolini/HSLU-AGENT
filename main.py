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

def clean_subject_name(raw_title):
    """Erzeugt einen sauberen, lesbaren Fachnamen (z.B. 'Datenbanksysteme')."""
    # z.B. aus 'I.BA_DBS.H2601' oder 'I.BA_DBS.H2601 - Datenbanksysteme'
    mapping = {
        "DBS": "Datenbanksysteme",
        "ASTAT": "Applied_Statistics",
        "KRR": "Logical_Reasoning_in_AI",
        "VSK": "Verteilte_Systeme",
        "PREN1": "Produktentwicklung_PREN1",
        "AEDCIT": "Academic_English"
    }
    for code, name in mapping.items():
        if code in raw_title:
            return name
            
    # Fallback
    parts = raw_title.split(".")
    name = parts[1] if len(parts) > 1 else raw_title
    return name.replace(" ", "_").replace("/", "_")

def weekly_job(force_week_str=None):
    now = datetime.now()
    if force_week_str:
        week_str = force_week_str
    else:
        # Sauberer Name: z.B. "KW 39 (30.09.2026)"
        calendar_week = now.strftime("%W")
        week_str = f"KW {calendar_week} ({now.strftime('%d.%m.%Y')})"
    
    print("\n" + "=" * 75)
    print(f"STARTE HSLU-STUDIENASSISTENT: {week_str}")
    print(f"Struktur: Fach-Hauptordner -> Wochen-Unterordner -> Komplettes Google Doc mit allem")
    print(f"Zeitstempel: {now.strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 75)

    # 1. Module initialisieren
    scraper = HSLUScraper()
    transcriber = Transcriber()
    llm = LLMProcessor()
    
    gworkspace = None
    try:
        gworkspace = GoogleWorkspace()
        print("[Google Drive] Verbindung erfolgreich hergestellt!")
    except Exception as e:
        print(f"[Google Drive] Hinweis: {e}")

    # 2. HSLU ILIAS scannen: Alle Fächer, Unterlagen und To-Dos erfassen
    results = scraper.login_and_download(week_str.replace(" ", "_").replace("(", "").replace(")", ""))
    courses_data = results.get("courses_data", [])
    todos = results.get("todos", [])
    
    print(f"\n[Scraping Fertig] {len(courses_data)} Kurse gescannt, {len(todos)} offene Abgaben/To-Dos gefunden.")

    # 3. PRO FACH verarbeiten
    for c in courses_data:
        course_title = c["title"]
        subject_name = clean_subject_name(course_title)
        files = c.get("files", [])
        videos = c.get("videos", [])
        page_text = c.get("text", "")
        
        print("\n" + "=" * 60)
        print(f"FACH: {subject_name} ({course_title})")
        print(f"Gefundene Unterlagen: {len(files)} | Gefundene Videos: {len(videos)}")
        print("=" * 60)

        # A. Google Drive Ordnerstruktur: Fach-Ordner (z.B. 'Datenbanksysteme')
        subject_folder_id = None
        sources_folder_id = None
        week_folder_id = None
        
        if gworkspace:
            try:
                # 1. Hauptordner für das Fach
                subject_folder_id = gworkspace.get_or_create_folder(subject_name)
                print(f" -> Fach-Ordner in Drive: '{subject_name}' (ID: {subject_folder_id})")
                
                # 2. Ordner für ALLE Quellen (wird immer weiter befüllt) - Sauberer Name!
                sources_folder_id = gworkspace.get_or_create_folder("Unterlagen", parent_id=subject_folder_id)
                print(f" -> Quellen-Ordner: 'Unterlagen'")
                
                # 3. Wochen-Ordner innerhalb des Fachs (nur für das generierte KI-Dossier)
                week_folder_id = gworkspace.get_or_create_folder(week_str, parent_id=subject_folder_id)
                print(f" -> Wochen-Ordner in '{subject_name}': '{week_str}'")
            except Exception as e:
                print(f" -> Fehler bei Google Drive Ordnererstellung: {e}")

        # B. Text aus allen NEUEN heruntergeladenen PDFs extrahieren
        pdf_corpus = ""
        for pdf in files:
            if pdf.lower().endswith(".pdf"):
                print(f" -> Extrahiere Text aus NEUEM PDF: {os.path.basename(pdf)}...")
                pdf_text = extract_pdf_text(pdf)
                if pdf_text:
                    pdf_corpus += f"\n\n=== DOKUMENT: {os.path.basename(pdf)} ===\n" + pdf_text

        # C. Videos erfassen / transkribieren
        transcript_corpus = ""
        for v in videos:
            v_url = v.get("url", "")
            v_title = v.get("text", "Vorlesung")
            if os.path.exists(v_url):
                print(f" -> Extrahiere Audio & Transkript von: {v_title}...")
                audio = transcriber.extract_audio(v_url)
                if audio:
                    t_text = transcriber.transcribe(audio)
                    transcript_corpus += f"\n=== VORLESUNGSTRANSKRIPT: {v_title} ===\n" + t_text
            else:
                transcript_corpus += f"\nReferenziertes Video/Stream: {v_title} ({v_url})\n"

        if not transcript_corpus:
            transcript_corpus = f"Vorlesungsinhalte und Aufzeichnungen zu {subject_name} für {week_str}."

        # D. To-Dos für dieses Fach filtern
        mod_todos = [td for td in todos if subject_name.lower() in td.lower() or "abgabe" in td.lower()]
        todo_text = "\n".join([f"- {t}" for t in mod_todos])

        # E. Gemini KI-Synthese: KOMPLETTES DOSSIER MIT ALLEM (Stoff, MEP-Fragen & Musterlösungen)
        combined_source_text = f"Modul-Informationen:\n{page_text[:4000]}\n\nNeue Unterlagen / Folien-Inhalte:\n{pdf_corpus[:15000]}\n\nOffene Abgaben:\n{todo_text}"
        
        print(f" -> Generiere das komplette Google Doc mit Gemini...")
        dossier = llm.generate_dossier(
            week_title=f"{subject_name} - {week_str}",
            transcript_text=transcript_corpus,
            pdf_text_content=combined_source_text,
            subject_code=course_title
        )

        # F. Lokal abspeichern
        dossier_filename = f"Wochen-Dossier.md"
        local_dossier_path = os.path.join(c["dir"], dossier_filename)
        with open(local_dossier_path, "w", encoding="utf-8") as f:
            f.write(dossier)
        print(f" -> Lokal gespeichert: {local_dossier_path}")

        # G. In Google Drive hochladen:
        if gworkspace:
            try:
                if week_folder_id:
                    doc_id = gworkspace.upload_file(local_dossier_path, week_folder_id, as_google_doc=True)
                    print(f" -> [Google Docs] Komplettes Dokument hochgeladen! ID: {doc_id}")

                if sources_folder_id:
                    local_unterlagen_dir = os.path.join(c["dir"], "Unterlagen")
                    
                    for pdf_file in files:
                        # Berechne den relativen Pfad (z.B. "01_Einfuehrung/Skript.pdf")
                        rel_path = os.path.relpath(pdf_file, local_unterlagen_dir)
                        rel_dir = os.path.dirname(rel_path)
                        
                        target_folder_id = sources_folder_id
                        
                        # Erstelle die Unterordner in Google Drive (falls vorhanden)
                        if rel_dir and rel_dir != "." and rel_dir != "":
                            parts = rel_dir.replace('\\', '/').split('/')
                            current_parent_id = sources_folder_id
                            for part in parts:
                                current_parent_id = gworkspace.get_or_create_folder(part, parent_id=current_parent_id)
                            target_folder_id = current_parent_id
                            
                        gworkspace.upload_file(pdf_file, target_folder_id, as_google_doc=False)
                        print(f" -> [Google Drive] Originaldatei in 'Unterlagen/{rel_dir}' gesichert: {os.path.basename(pdf_file)}")
            except Exception as e:
                print(f" -> Fehler beim Drive-Upload: {e}")

        print(f" -> Warte 15 Sekunden um API-Limits zu vermeiden...")
        time.sleep(15)

    print("\n" + "=" * 75)
    print(f"WÖCHENTLICHER DURCHLAUF FÜR {week_str} ERFOLGREICH BEENDET!")
    print(f"Alle Fächer haben ihren Hauptordner, darin den Wochenordner und das komplette Google Doc mit allem erhalten.")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    print("HSLU KI-Studienassistent ist aktiv.")
    print("Schedule: Jeden Sonntag um 18:00 Uhr automatisch.")
    
    # Scheduler
    schedule.every().sunday.at("18:00").do(weekly_job)
    
    print("Warteschleife aktiv. Drücke Strg + C zum Beenden.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("Beendet.")
