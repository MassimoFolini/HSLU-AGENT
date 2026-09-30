import os
import re
from registry import registry
from transcriber import Transcriber
import google.generativeai as genai

def fetch_missing_videos():
    print("Starte gezielten Download der fehlenden Videos/Streams anhand der Registry...")
    transcriber = Transcriber()
    pending_items = registry.get_pending_items()
    
    videos = [i for i in pending_items if i.get("type") == "video"]
    if not videos:
        print("Keine ausstehenden Videos in der Registry gefunden!")
        return

    cookie_file = os.path.join("downloads", "cookies.txt")
    if not os.path.exists(cookie_file):
        print("WARNUNG: Keine cookies.txt gefunden! Panopto-Downloads könnten fehlschlagen.")
        cookie_file = None

    for v in videos:
        course_id = v["course_id"]
        url = v["url"]
        title = v["title"]
        item_id = v["item_id"]
        
        base_dir = os.path.join("downloads", "video_backfill", course_id)
        os.makedirs(base_dir, exist_ok=True)
        
        print(f"\nVerarbeite Video: {title} ({course_id})")
        audio_path = None
        
        if os.path.exists(url):
            audio_path = transcriber.extract_audio(url)
        elif url.startswith("http") and cookie_file:
            audio_path = transcriber.download_audio_from_url(url, cookie_file, output_dir=base_dir)
            
        if audio_path:
            transcript = transcriber.transcribe(audio_path)
            
            safe_title = re.sub(r'[^a-zA-Z0-9_\-\s]', '', title).strip()
            md_path = os.path.join(base_dir, f"Transkript_{safe_title}.md")
            
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(f"# Transkript: {title}\n")
                f.write(f"**Modul:** {course_id}\n")
                f.write(f"**Quelle:** {url}\n\n")
                f.write(transcript)
                
            print(f"-> Transkript gespeichert: {md_path}")
            registry.mark_processed(course_id, item_id)
        else:
            print("-> Fehler beim Download des Audios.")

if __name__ == '__main__':
    fetch_missing_videos()
