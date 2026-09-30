from google_integration import GoogleWorkspace
import os
from dotenv import load_dotenv

load_dotenv()

def rename_root_folder():
    gw = GoogleWorkspace()
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    # Clean up single quotes from the .env value if they exist
    if folder_id and folder_id.startswith("'") and folder_id.endswith("'"):
        folder_id = folder_id[1:-1]
        
    print(f"Versuche Ordner mit ID {folder_id} umzubenennen...")
    
    try:
        # Aktuellen Namen abrufen
        folder = gw.drive_service.files().get(fileId=folder_id, fields='name').execute()
        old_name = folder.get('name')
        print(f"Aktueller Name: {old_name}")
        
        # Neuen Namen setzen
        new_name = "HSLU Agent"
        file_metadata = {'name': new_name}
        
        # Ordner aktualisieren
        updated_folder = gw.drive_service.files().update(
            fileId=folder_id,
            body=file_metadata,
            fields='name'
        ).execute()
        
        print(f"Ordner wurde erfolgreich umbenannt zu: {updated_folder.get('name')}")
    except Exception as e:
        print(f"Fehler beim Umbenennen: {e}")

if __name__ == "__main__":
    rename_root_folder()
