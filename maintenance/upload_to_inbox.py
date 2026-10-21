"""Legt Dateien in den Drive-Eingang <Fach>/SWnn (Transkripte oder Aufnahmen, die der Server verarbeitet).

  python maintenance/upload_to_inbox.py Applied_Statistics 5 "C:/Users/X1/Downloads/ASTAT_Berger.txt" [neuer Name.txt]

Die Schulwoche ist eine Zahl (5 = SW05, SW01 = Woche ab 14.09.2026). Aus dem Projektroot starten.
Verwendet token.json (privates Konto), legt fehlende Ordner _Eingang/<Fach>/SWnn an.
"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shutil
import tempfile

import weeks
from google_integration import GoogleWorkspace


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    subject, week, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    name = sys.argv[4] if len(sys.argv) > 4 else os.path.basename(path)
    gw = GoogleWorkspace()
    inbox = gw.get_or_create_folder("_Eingang")
    folder = gw.get_or_create_folder(weeks.label(week), parent_id=gw.get_or_create_folder(subject, parent_id=inbox))
    tmp = os.path.join(tempfile.mkdtemp(), name)
    shutil.copy(path, tmp)
    gw.upload_file(tmp, folder, as_google_doc=False)
    print(f"Hochgeladen: _Eingang/{subject}/{weeks.label(week)}/{name}")


if __name__ == "__main__":
    main()
