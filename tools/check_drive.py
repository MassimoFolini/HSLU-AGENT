from google_integration import GoogleWorkspace
gw = GoogleWorkspace()
print("Root folder ID:", gw.root_folder_id)

def print_tree(folder_id, indent=0):
    query = f"'{folder_id}' in parents and trashed = false"
    results = gw.drive_service.files().list(q=query, spaces='drive', fields='files(id, name, mimeType)').execute()
    for f in results.get('files', []):
        print("  " * indent + f"- {f['name']}")
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            print_tree(f['id'], indent + 1)

print_tree(gw.root_folder_id)
