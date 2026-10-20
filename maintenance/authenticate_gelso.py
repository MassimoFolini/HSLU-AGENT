"""Einmalige Anmeldung des Gelso-Kontos fuer NotebookLM Enterprise: erzeugt token_gelso.json.

  python maintenance/authenticate_gelso.py

Im Browser mit massimo.folini@gelso.ch anmelden und zustimmen. Danach token_gelso.json auf den Server kopieren:
  scp token_gelso.json ubuntu@<server>:/opt/KiAgentHSLU/token_gelso.json
Aus dem Projektroot starten. Braucht client_secret_*.json im Projektroot.
"""
import glob
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

files = glob.glob(os.path.join(BASE, "client_secret_*.json"))
if not files:
    sys.exit("Keine client_secret_*.json im Projektroot gefunden.")
flow = InstalledAppFlow.from_client_secrets_file(files[0], SCOPES)
creds = flow.run_local_server(port=0, login_hint="massimo.folini@gelso.ch", prompt="consent", access_type="offline")
with open(os.path.join(BASE, "token_gelso.json"), "w", encoding="utf-8") as f:
    f.write(creds.to_json())
print("token_gelso.json gespeichert.")
