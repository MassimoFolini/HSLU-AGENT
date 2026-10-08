import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os
import subprocess
import webbrowser
from google_auth_oauthlib.flow import InstalledAppFlow
from checks.check_google_drive import test_drive

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

# Browser-Launcher anpassen für Windows Powershell
def custom_open(url, *args, **kwargs):
    print(f"\n[Browser] Öffne URL via Windows PowerShell...")
    with open('auth_url.txt', 'w', encoding='utf-8') as f:
        f.write(url)
    subprocess.Popen(['powershell', '-c', f'Start-Process "{url}"'])
    return True

webbrowser.open = custom_open

def run_auth_and_upload():
    print("=" * 60)
    print("GOOGLE WORKSPACE AUTHENTIFIZIERUNG")
    print("=" * 60)
    
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    port = 8080
    
    print("Starte lokalen OAuth-Server auf Port 8080...")
    # run_local_server generiert nur EINMAL das State-Token
    creds = flow.run_local_server(
        port=port,
        prompt='consent',
        access_type='offline',
        open_browser=True
    )
    
    with open('token.json', 'w', encoding='utf-8') as token:
        token.write(creds.to_json())
        
    print("\n" + "=" * 60)
    print("[ERFOLG] Authentifizierung erfolgreich! token.json gespeichert.")
    print("Starte sofort den Upload nach Google Drive...")
    print("=" * 60)
    test_drive()

if __name__ == "__main__":
    run_auth_and_upload()
