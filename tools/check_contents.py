from google_integration import GoogleWorkspace

gw = GoogleWorkspace()
dbs_id = '1ZYi_nWEWuPOndiuG7NeX9eQMJr1ncDiE'
res = gw.drive_service.files().list(q=f"'{dbs_id}' in parents and trashed = false", fields='files(id, name, mimeType)').execute()
print("Inhalt von Datenbanksysteme:")
for f in res.get('files', []):
    print(f"- {f['name']} ({f['mimeType']}) -> ID: {f['id']}")
    
    # Wenn es ein Ordner ist, schaue auch hinein:
    if f['mimeType'] == 'application/vnd.google-apps.folder':
        sub_res = gw.drive_service.files().list(q=f"'{f['id']}' in parents and trashed = false", fields='files(id, name, mimeType)').execute()
        for sf in sub_res.get('files', []):
            print(f"    * {sf['name']} ({sf['mimeType']})")
