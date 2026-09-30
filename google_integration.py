import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

class GoogleWorkspace:
    def __init__(self):
        self.creds = None
        self._authenticate()
        self.drive_service = build('drive', 'v3', credentials=self.creds)
        self.docs_service = build('docs', 'v1', credentials=self.creds)
        self.root_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

    def _authenticate(self):
        # 1. Option: Service Account (ideal für Server, kein Browser nötig)
        if os.path.exists('service_account.json'):
            print("[Google Auth] Nutze service_account.json...")
            self.creds = service_account.Credentials.from_service_account_file(
                'service_account.json', scopes=SCOPES
            )
            return

        # 2. Option: Standard OAuth 2.0 Flow
        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                print("[Google Auth] Erneuere abgelaufenes Token...")
                self.creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    raise FileNotFoundError(
                        "Weder 'credentials.json' noch 'service_account.json' gefunden!\n"
                        "Bitte lade die OAuth Client-ID Credentials von der Google Cloud Console herunter."
                    )
                print("[Google Auth] Starte Browser für einmaligen Google-Login...")
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                self.creds = flow.run_local_server(port=0)
                
            with open('token.json', 'w', encoding='utf-8') as token:
                token.write(self.creds.to_json())

    def get_or_create_folder(self, folder_name, parent_id=None):
        """Sucht nach einem existierenden Ordner. Falls nicht vorhanden, wird er erstellt."""
        parent = parent_id or self.root_folder_id
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent:
            query += f" and '{parent}' in parents"
            
        results = self.drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        if files:
            print(f"[Google Drive] Ordner '{folder_name}' existiert bereits (ID: {files[0]['id']})")
            return files[0]['id']
            
        return self.create_folder(folder_name, parent_id=parent)

    def create_folder(self, folder_name, parent_id=None):
        """Erstellt einen neuen Ordner in Google Drive."""
        parent = parent_id or self.root_folder_id
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent:
            file_metadata['parents'] = [parent]

        folder = self.drive_service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

    def create_document(self, title, content, folder_id=None):
        """Erstellt ein formatiertes Google Doc im angegebenen Drive-Ordner."""
        document = self.docs_service.documents().create(body={'title': title}).execute()
        doc_id = document.get('documentId')
        
        # Text einfügen
        requests = [
            {
                'insertText': {
                    'location': {'index': 1},
                    'text': content
                }
            }
        ]
        self.docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
        
        # Dokument in den Zielordner verschieben
        target_folder = folder_id or self.root_folder_id
        if target_folder:
            doc_file = self.drive_service.files().get(fileId=doc_id, fields='parents').execute()
            previous_parents = ",".join(doc_file.get('parents', []))
            self.drive_service.files().update(
                fileId=doc_id,
                addParents=target_folder,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
        
        return doc_id

    def upload_file(self, file_path, folder_id=None, as_google_doc=True):
        """Lädt eine Datei in Google Drive hoch. Bei Text/Markdown wird sie automatisch in ein echtes Google Doc umgewandelt."""
        if not os.path.exists(file_path):
            print(f"[Google Drive] Datei nicht gefunden: {file_path}")
            return None

        filename = os.path.basename(file_path)
        clean_title = filename.replace('.md', '').replace('.txt', '')
        target_folder = folder_id or self.root_folder_id
        
        file_metadata = {'name': clean_title if as_google_doc and filename.endswith(('.md', '.txt')) else filename}
        if target_folder:
            file_metadata['parents'] = [target_folder]

        # Wenn es eine Markdown/Text-Datei ist, wandeln wir sie direkt in ein echtes Google Doc um!
        # Das ist entscheidend für NotebookLM, da NotebookLM Google Docs direkt als Quellen importieren kann.
        if as_google_doc and filename.endswith(('.md', '.txt')):
            file_metadata['mimeType'] = 'application/vnd.google-apps.document'
            media = MediaFileUpload(file_path, mimetype='text/plain', resumable=True)
        else:
            media = MediaFileUpload(file_path, resumable=True)

        print(f"[Google Drive] Lade '{filename}' in Drive hoch (als Google Doc: {as_google_doc})...")
        
        # ---------------------------------------------------------
        # DUPLIKAT-PRÜFUNG: Lösche alte Versionen mit demselben Namen
        # ---------------------------------------------------------
        if target_folder:
            target_name = file_metadata['name']
            query = f"name='{target_name}' and '{target_folder}' in parents and trashed=false"
            try:
                existing_files = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute().get('files', [])
                for ef in existing_files:
                    print(f"[Google Drive] Lösche veraltetes Duplikat '{target_name}' (ID: {ef['id']})")
                    self.drive_service.files().update(fileId=ef['id'], body={'trashed': True}).execute()
            except Exception as e:
                print(f"[Google Drive] Fehler bei der Duplikatsprüfung: {e}")
        # ---------------------------------------------------------
        file = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'
        ).execute()
        print(f"[Google Drive] Erfolgreich hochgeladen! ID: {file.get('id')}")
        return file.get('id')
