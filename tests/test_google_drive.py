from google_integration import GoogleWorkspace
import os
from dotenv import load_dotenv

load_dotenv()

def test_drive():
    print("=" * 60)
    print("GOOGLE DRIVE & DOCS INTEGRATIONSTEST")
    print("=" * 60)
    
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    print(f"Zielordner-ID aus .env: {folder_id}")
    
    if not os.path.exists("credentials.json") and not os.path.exists("service_account.json"):
        print("\n[FEHLER] Es wurde weder 'credentials.json' noch 'service_account.json' gefunden!")
        print("Google verlangt eine Berechtigungsdatei, damit externe Skripte in dein Drive schreiben dürfen.")
        print("\nSo richtest du das in 3 Minuten ein:")
        print("1. Öffne die Google Cloud Console: https://console.cloud.google.com/")
        print("2. Aktiviere unter 'APIs und Dienste' die 'Google Drive API' und 'Google Docs API'.")
        print("3. Erstelle unter 'Anmeldedaten' (Credentials) eine 'OAuth-Client-ID' (Typ: Desktop-App).")
        print("4. Klicke auf 'JSON herunterladen' und speichere die Datei als 'credentials.json' im Projektordner ab.")
        return
        
    try:
        gw = GoogleWorkspace()
        print("[OK] Verbindung zu Google Workspace hergestellt!")
        
        # Test 1: Testordner anlegen
        print("\n1. Erstelle Testordner in Drive...")
        test_folder = gw.create_folder("HSLU_Agent_Testlauf", parent_id=folder_id)
        print(f"[OK] Ordner erstellt! ID: {test_folder}")
        
        # Test 2: Testdokument anlegen
        print("\n2. Erstelle Google Doc...")
        test_doc = gw.create_document(
            title="HSLU_Test_Dossier",
            content="Hallo von deinem autonomen KI-Studienassistenten!\nDieser Test bestätigt die erfolgreiche Google Drive & Docs Anbindung.",
            folder_id=test_folder
        )
        print(f"[OK] Google Doc erstellt! ID: {test_doc}")
        
        # Test 3: Vorhandenes DBS Dossier hochladen
        dossier_path = "downloads/DBS/Dossier_Woche_02_Herbstsemester_2026_Datenbanksysteme.md"
        if os.path.exists(dossier_path):
            print("\n3. Lade generiertes DBS-Dossier hoch...")
            gw.upload_file(dossier_path, folder_id=test_folder)
            
        print("\n" + "=" * 60)
        print("FERTIG! Bitte öffne dein Google Drive und überprüfe den Ordner!")
        print("=" * 60)
        
    except Exception as e:
        print(f"[FEHLER] Beim Drive-Test aufgetreten: {e}")

if __name__ == "__main__":
    test_drive()
