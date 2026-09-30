from google_integration import GoogleWorkspace

def check_duplicates():
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
        
    for p, flist in parent_map.items():
        if len(flist) > 1:
            print(f"Parent {p} hat {len(flist)} Dossiers!")
            # Sortiere nach Datum (älteste zuerst)
            flist.sort(key=lambda x: x.get('createdTime', ''))
            for f in flist:
                print(f"  - {f['name']} (ID: {f['id']}) - {f.get('createdTime')}")
        else:
            pass

if __name__ == "__main__":
    check_duplicates()
