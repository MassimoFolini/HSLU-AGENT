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
    print(f"Starting weekly HSLU workflow at {datetime.now()}")
    
    # 1. Init modules
    scraper = HSLUScraper()
    transcriber = Transcriber()
    llm = LLMProcessor()
    
    # Google Workspace Init (requires credentials.json)
    try:
        gworkspace = GoogleWorkspace()
    except Exception as e:
        print(f"Could not init Google Workspace (missing credentials?): {e}")
        gworkspace = None

    week_str = datetime.now().strftime("Woche_%W_%Y-%m-%d")
    
    # 2. Scrape
    files = scraper.login_and_download(week_str)
    
    # Process each downloaded video
    for video in files.get("videos", []):
        # 3. Transcribe
        audio_path = transcriber.extract_audio(video)
        if audio_path:
            transcript = transcriber.transcribe(audio_path)
        else:
            transcript = "Kein Transkript verfügbar."
            
        # 4. Generate Dossier
        dossier_text = llm.generate_dossier(week_str, transcript)
        
        # 5. Save to Google Workspace
        if gworkspace:
            folder_id = gworkspace.create_folder(week_str)
            doc_id = gworkspace.create_document(f"Dossier_{week_str}", dossier_text, folder_id)
            print(f"Dossier saved to Google Docs! Document ID: {doc_id}")
            
            # Optional: gworkspace.upload_file(video, folder_id)
            # Optional: gworkspace.upload_file(pdf, folder_id)
        else:
            # Fallback local save
            with open(f"downloads/Dossier_{week_str}.md", "w", encoding="utf-8") as f:
                f.write(dossier_text)
            print(f"Saved locally to downloads/Dossier_{week_str}.md")
            
    print("Workflow finished.")

if __name__ == "__main__":
    print("HSLU AI Assistant started.")
    
    # Start immediately for testing (comment out for pure cron behavior)
    weekly_job()
    
    # Schedule every Sunday at 18:00
    schedule.every().sunday.at("18:00").do(weekly_job)
    
    print("Scheduler is running...")
    while True:
        schedule.run_pending()
        time.sleep(60)
