from google_integration import GoogleWorkspace
import re

gw = GoogleWorkspace()

print('Suche nach kaputten und doppelten Dossiers...')
query = "name contains 'Dossier' and trashed = false"
results = gw.drive_service.files().list(q=query, spaces='drive', fields='files(id, name, parents)').execute()
files = results.get('files', [])

for f in files:
    name = f['name']
    if '(1)' in name or '(2)' in name or '(3)' in name or '(4)' in name or name.startswith('Dossier_') or name.startswith('Komplettes_Dossier_'):
        print(f"Verschiebe in Papierkorb: {name}")
        gw.drive_service.files().update(fileId=f['id'], body={'trashed': True}).execute()

print('Cleanup abgeschlossen!')
