import asyncio
import os
import glob
from notebooklm import NotebookLMClient
from notebooklm.types import SourceType

async def generate_audio_overview(notebook_title, source_folder, output_mp3_path):
    print(f"Starte NotebookLM Integration für '{notebook_title}'...")
    
    # Init client
    async with NotebookLMClient.from_storage() as client:
        # 1. Create a notebook
        notebook = await client.notebooks.create(notebook_title)
        print(f"Notebook erstellt: {notebook.notebook_id}")
        
        # 2. Upload files
        files = glob.glob(os.path.join(source_folder, "*.*"))
        valid_extensions = {".pdf", ".txt", ".md"}
        uploaded = 0
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_extensions:
                print(f"Lade hoch: {os.path.basename(f)}")
                with open(f, "rb") as file_data:
                    await client.sources.add(notebook.notebook_id, SourceType.FILE, file_data, filename=os.path.basename(f))
                uploaded += 1
                
        if uploaded == 0:
            print("Keine PDFs/MDs gefunden, breche ab.")
            return False
            
        print("Upload abgeschlossen. Starte Podcast-Generierung (Audio Overview)...")
        # 3. Generate Audio
        audio = await client.artifacts.generate_audio(notebook.notebook_id)
        
        print("Warte auf Render-Abschluss (Das kann ein paar Minuten dauern)...")
        await client.artifacts.wait(notebook.notebook_id, audio.artifact_id)
        
        print(f"Lade MP3 herunter: {output_mp3_path}")
        await client.artifacts.download_audio(notebook.notebook_id, audio.artifact_id, output_mp3_path)
        print("NotebookLM Podcast erfolgreich erstellt!")
        return True

if __name__ == "__main__":
    # Test
    # asyncio.run(generate_audio_overview("Test Notebook", "downloads/I.BA_KRR.H2601/Unterlagen", "podcast_test.mp3"))
    pass
