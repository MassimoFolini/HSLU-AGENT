from scraper import HSLUScraper
from llm_processor import LLMProcessor
from playwright.sync_api import sync_playwright
import os
import json

s = HSLUScraper()
llm = LLMProcessor()
os.makedirs("downloads/DBS", exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(accept_downloads=True)
    page = ctx.new_page()
    s.login(page)
    
    # Navigiere in DBS
    print("Navigiere in Modul: Datenbanksysteme (DBS)...")
    page.goto("https://elearning.hslu.ch/ilias/goto.php/crs/7206169", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Hole gesamten Text der Modulseite für die Analyse
    course_intro_text = page.locator('main').first.inner_text()
    
    # Suche Ordner "Modulunterlagen" oder "Inputs"
    folder = page.locator('text="Modulunterlagen"').or_(page.locator('text="Course Documents"')).first
    if folder.is_visible():
        print("Öffne Ordner Modulunterlagen...")
        folder.click()
        page.wait_for_timeout(3000)
        page.screenshot(path="screenshots/modulunterlagen.png")
        
    # Suche nach herunterladbaren Dateien
    files = []
    file_elements = page.locator('a[href*="goto.php/file/"], a[href*="download"], a[href*=".pdf"]').all()
    print(f"Gefundene Dateien im Ordner: {len(file_elements)}")
    
    downloaded_files = []
    for f in file_elements[:3]:
        try:
            fname = f.inner_text().strip().replace("\n", " ")
            print(f"Lade Datei herunter: {fname}")
            with page.expect_download(timeout=10000) as download_info:
                f.click()
            download = download_info.value
            target_path = os.path.join("downloads/DBS", download.suggested_filename)
            download.save_as(target_path)
            downloaded_files.append(target_path)
            print(f"Erfolgreich gespeichert: {target_path}")
        except Exception as e:
            print(f"Download-Hinweis/Fehler: {e}")
            
    b.close()

# Jetzt KI-Synthese mit Google Gemini 2.5 Flash durchführen!
print("\n" + "="*60)
print("Starte Gemini KI-Analyse & Dossier-Erstellung...")
print("="*60)

week_title = "Woche_02_Herbstsemester_2026_Datenbanksysteme"
sample_transcript = """
Prof. Kaufmann: Herzlich willkommen zur heutigen Vorlesung Datenbanksysteme!
In dieser Woche geht es um relationale Datenmodellierung, das ER-Modell und die Transformation in relationale Schemata.
Ein ganz wichtiger Hinweis zur Modulendprüfung (MEP): Wir werden mindestens 20 Punkte auf Normalisierung und 3NF vergeben!
Bitte stellt sicher, dass ihr die Übungseinheit 1 bis kommenden Freitag bearbeitet habt.
Wir arbeiten mit PostgreSQL und später mit MongoDB für den NoSQL-Teil.
Achtet beim Entwurf besonders auf Primär- und Fremdschlüsselintegrität.
"""

dossier = llm.generate_dossier(
    week_title=week_title,
    transcript_text=sample_transcript,
    pdf_text_content=course_intro_text[:6000]
)

dossier_path = f"downloads/DBS/Dossier_{week_title}.md"
with open(dossier_path, "w", encoding="utf-8") as f:
    f.write(dossier)

print(f"\nDossier erfolgreich generiert und gespeichert unter: {dossier_path}")
print("="*60)
print("Vorschau des generierten Dossiers:")
print("="*60)
print(dossier[:1200] + "\n...")
