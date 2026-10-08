import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google_integration import GoogleWorkspace
import time

def clean_duplicates():
    gw = GoogleWorkspace()
    # Finde alle "Wochen-Dossier" Dateien
    files = gw.drive_service.files().list(
        q="name contains 'Wochen-Dossier' and trashed=false",
        spaces='drive', fields='files(id, name, parents, createdTime)'
    ).execute().get('files', [])
    
    parent_map = {}
    for f in files:
        if not f.get('parents'): continue
        p = f['parents'][0]
        if p not in parent_map:
            parent_map[p] = []
        parent_map[p].append(f)
        
    deleted_count = 0
    for p, flist in parent_map.items():
        if len(flist) > 1:
            # Sortiere nach Datum (älteste zuerst)
            flist.sort(key=lambda x: x.get('createdTime', ''))
            
            # Behalte nur das neueste (letztes Element in der Liste)
            to_delete = flist[:-1]
            for f in to_delete:
                print(f"Lösche veraltetes Dossier: {f['id']} (Erstellt: {f.get('createdTime')})")
                try:
                    gw.drive_service.files().update(fileId=f['id'], body={'trashed': True}).execute()
                    deleted_count += 1
                except Exception as e:
                    print(f"Fehler beim Löschen: {e}")
    print(f"Fertig! {deleted_count} alte Duplikate in den Papierkorb verschoben.")

if __name__ == "__main__":
    clean_duplicates()
