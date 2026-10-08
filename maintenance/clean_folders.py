import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google_integration import GoogleWorkspace
gw = GoogleWorkspace()
query = "name contains 'Woche_' and trashed = false"
results = gw.drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
for f in results.get('files', []):
    print('Lösche Ordner:', f['name'])
    gw.drive_service.files().update(fileId=f['id'], body={'trashed': True}).execute()
