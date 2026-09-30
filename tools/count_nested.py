from google_integration import GoogleWorkspace
gw = GoogleWorkspace()
subjects = ['Academic_English', 'Applied_Statistics', 'Datenbanksysteme', 'Logical_Reasoning_in_AI', 'Verteilte_Systeme', 'Produktentwicklung_PREN1']

def count_files_recursive(folder_id):
    files = gw.drive_service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        spaces='drive', fields='files(id, mimeType)'
    ).execute().get('files', [])
    
    count = 0
    for f in files:
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            count += count_files_recursive(f['id'])
        else:
            count += 1
    return count

for sub in subjects:
    res = gw.drive_service.files().list(q=f"name='{sub}' and trashed=false", spaces='drive', fields='files(id)').execute().get('files', [])
    if not res: continue
    sid = res[0]['id']
    unterlagen = gw.drive_service.files().list(q=f"name='Unterlagen' and '{sid}' in parents and trashed=false", spaces='drive', fields='files(id)').execute().get('files', [])
    if unterlagen:
        print(f'{sub}: {count_files_recursive(unterlagen[0]["id"])} Dateien (verschachtelt)')
