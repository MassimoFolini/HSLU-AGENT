import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/documents']

class GoogleWorkspace:
    def __init__(self):
        self.creds = None
        self._authenticate()
        self.drive_service = build('drive', 'v3', credentials=self.creds)
        self.docs_service = build('docs', 'v1', credentials=self.creds)
        self.root_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

    def _authenticate(self):
        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                self.creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(self.creds.to_json())

    def create_folder(self, folder_name, parent_id=None):
        """Creates a folder in Google Drive."""
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
        """Creates a Google Doc with the specified content."""
        document = self.docs_service.documents().create(body={'title': title}).execute()
        doc_id = document.get('documentId')
        
        # Insert text (naive insertion, proper formatting requires complex requests)
        requests = [
            {
                'insertText': {
                    'location': {
                        'index': 1,
                    },
                    'text': content
                }
            }
        ]
        self.docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
        
        # Move document to folder
        if folder_id:
            doc_file = self.drive_service.files().get(fileId=doc_id, fields='parents').execute()
            previous_parents = ",".join(doc_file.get('parents', []))
            self.drive_service.files().update(
                fileId=doc_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
        
        return doc_id

    def upload_file(self, file_path, folder_id):
        """Uploads a file (e.g. PDF/MP3) to the specified folder."""
        # TODO: Implement media upload using MediaFileUpload
        print(f"Uploading {file_path} to folder {folder_id}...")
        pass
