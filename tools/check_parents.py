from google_integration import GoogleWorkspace
gw = GoogleWorkspace()
results = gw.drive_service.files().list(q="name contains 'AEDCIT' and trashed = false", spaces='drive', fields='files(id, name, parents)').execute()
for f in results.get('files', []):
    print(f['name'], f.get('parents', []))
