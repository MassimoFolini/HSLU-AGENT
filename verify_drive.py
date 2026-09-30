from google_integration import GoogleWorkspace

def verify_drive():
    gw = GoogleWorkspace()
    subjects = [
        "Academic_English", 
        "Applied_Statistics", 
        "Datenbanksysteme", 
        "Logical_Reasoning_in_AI", 
        "Verteilte_Systeme", 
        "Produktentwicklung_PREN1"
    ]
    
    print("Starte Google Drive Verifizierung...")
    for subject in subjects:
        print(f"\n--- Pruefe Fach: {subject} ---")
        
        # 1. Finde Fachordner
        results = gw.drive_service.files().list(
            q=f"name='{subject}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive', fields='files(id, name)'
        ).execute().get('files', [])
        
        if not results:
            print(f"[FEHLER] Fachordner {subject} nicht gefunden!")
            continue
            
        subject_id = results[0]['id']
        
        # 2. Finde 'Unterlagen'
        unterlagen = gw.drive_service.files().list(
            q=f"name='Unterlagen' and '{subject_id}' in parents and trashed=false",
            spaces='drive', fields='files(id)'
        ).execute().get('files', [])
        
        if unterlagen:
            u_id = unterlagen[0]['id']
            # Zaehle Dateien in Unterlagen
            u_files = gw.drive_service.files().list(
                q=f"'{u_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive', fields='files(id, name)'
            ).execute().get('files', [])
            print(f"  -> Unterlagen Archiv: {len(u_files)} Dateien vorhanden")
        else:
            print("  -> [WARNUNG] Ordner 'Unterlagen' fehlt!")
            
        # 3. Finde 'Woche 02'
        woche2 = gw.drive_service.files().list(
            q=f"name='Woche 02' and '{subject_id}' in parents and trashed=false",
            spaces='drive', fields='files(id)'
        ).execute().get('files', [])
        
        if woche2:
            w2_id = woche2[0]['id']
            w2_files = gw.drive_service.files().list(
                q=f"'{w2_id}' in parents and trashed=false",
                spaces='drive', fields='files(id, name)'
            ).execute().get('files', [])
            
            dossier_found = any("Wochen-Dossier" in f['name'] for f in w2_files)
            if dossier_found:
                print("  -> Woche 02: Dossier ist ERFOLGREICH generiert und vorhanden!")
            else:
                print("  -> Woche 02: Ordner existiert, aber KEIN Dossier gefunden!")
        else:
            print("  -> [FEHLER] Ordner 'Woche 02' fehlt!")

if __name__ == "__main__":
    verify_drive()
