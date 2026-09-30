from google_integration import GoogleWorkspace
gw = GoogleWorkspace()
query = "name contains '.pdf' and trashed = false"
results = gw.drive_service.files().list(q=query, spaces='drive', fields='files(id, name, parents)').execute()
for f in results.get('files', []):
    print('Gefundene PDF:', f['name'])
