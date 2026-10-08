import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google_integration import GoogleWorkspace
from llm_processor import LLMProcessor
import os
import time

gw = GoogleWorkspace()
llm = LLMProcessor()

subjects = [
    {
        "name": "Datenbanksysteme",
        "code": "I.BA_DBS.H2601",
        "desc": "Relationale Datenmodellierung, ER-Diagramme, Transformation, 3NF Normalisierung, PostgreSQL & MongoDB."
    },
    {
        "name": "Applied_Statistics",
        "code": "I.BA_ASTAT_MM.H26",
        "desc": "Wahrscheinlichkeitsrechnung, Deskriptive & Induktive Statistik, Hypothesentests, R/Python für Data Science."
    },
    {
        "name": "Logical_Reasoning_in_AI",
        "code": "I.BA_KRR.H2601",
        "desc": "Aussagen- und Prädikatenlogik, Wissensrepräsentation, Inferenzmechanismen, automatisches Schliessen in der KI."
    },
    {
        "name": "Verteilte_Systeme",
        "code": "I.BA_VSK_MM.H2601",
        "desc": "Verteilte Softwarekomponenten, Microservices, REST APIs, RPC, Concurrency, Synchronisation & Messaging."
    },
    {
        "name": "Produktentwicklung_PREN1",
        "code": "TA.BA_PREN1.H2601",
        "desc": "Interdisziplinäres Entwicklungsprojekt, Meilensteine, Anforderungsanalyse, Systemarchitektur & Prototyping."
    },
    {
        "name": "Academic_English",
        "code": "I.BA_AEDCIT.H2601",
        "desc": "IELTS Vorbereitung, Technical Academic Writing, Scientific Presentations, Software Engineering Terminology."
    }
]

week_name = "Woche_02_2026-09-30"

print("=" * 60)
print("RICHTE ALLE 6 FÄCHER IN GOOGLE DRIVE EIN...")
print("Struktur:")
print("Hauptordner -> Fach -> [Komplettes Google Doc direkt im Fach!]")
print("                    -> [Wochen-Ordner für Unterlagen & PDFs]")
print("=" * 60)

for s in subjects:
    name = s["name"]
    print(f"\n[Verarbeite] Fach: {name}...")
    
    # 1. Fach-Hauptordner im Agent_Test anlegen / abrufen
    subj_folder_id = gw.get_or_create_folder(name)
    print(f" -> Fach-Ordner ID: {subj_folder_id}")
    
    # 2. Wochen-Unterordner im Fach anlegen
    week_folder_id = gw.get_or_create_folder(week_name, parent_id=subj_folder_id)
    print(f" -> Wochen-Unterordner ID: {week_folder_id}")
    
    # 3. Generiere das komplette Dossier mit allem für dieses Fach
    sample_text = f"Modul: {name} ({s['code']})\nSchwerpunkte: {s['desc']}"
    dossier_content = llm.generate_dossier(
        week_title=f"{name} - {week_name}",
        transcript_text=f"Vorlesungsinhalte, Dozentenhinweise und Diskussionen zu {name}.",
        pdf_text_content=sample_text,
        subject_code=s['code']
    )
    
    # Lokal speichern
    local_path = f"downloads/Dossier_{name}.md"
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(dossier_content)
        
    # 4. Das KOMPLETTE GOOGLE DOC direkt in den Fach-Ordner legen!
    doc_id = gw.upload_file(local_path, subj_folder_id, as_google_doc=True)
    print(f" -> [Google Doc] Direkt im Fach '{name}' abgelegt! ID: {doc_id}")
    
    # 5. Zusätzlich zur Sicherheit auch eine Kopie im Wochenordner
    gw.upload_file(local_path, week_folder_id, as_google_doc=True)
    
    print(f" -> Warte 15 Sekunden um API-Limits zu vermeiden...")
    time.sleep(15)

print("\n" + "=" * 60)
print("ALLE 6 FÄCHER ERFOLGREICH EINGERICHTET!")
print("=" * 60)
