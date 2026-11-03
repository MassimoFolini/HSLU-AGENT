# HSLU KI-Studienassistent

Ein Agent für das Studium an der Hochschule Luzern (HSLU). Er lädt die Kursunterlagen aus ILIAS, nimmt die Zoom-Vorlesungen als Ton auf, erzeugt daraus Transkripte und Wochen-Dossiers (Gemini), legt alles nach Fach und Schulwoche in Google Drive ab und füttert NotebookLM Enterprise. Dort entstehen pro Fach und Woche die Audio-Zusammenfassungen von NotebookLM selbst.

Stand: 02.11.2026. Server: Infomaniak, `ubuntu@179.237.110.120`, Projekt unter `/opt/KiAgentHSLU` (kein Git-Checkout, Deployment per `scp`).

## Inhalt

1. [Datenfluss](#datenfluss)
2. [Verbindungen und Konten](#verbindungen-und-konten)
3. [Anforderungen an NotebookLM Enterprise](#anforderungen-an-notebooklm-enterprise)
4. [Steuerung: Dienste und Timer auf dem Server](#steuerung-dienste-und-timer-auf-dem-server)
5. [Zoom-Aufnahme (zoomrec)](#zoom-aufnahme-zoomrec)
6. [Schulwochen und Ablage](#schulwochen-und-ablage)
7. [Dateien im Projekt](#dateien-im-projekt)
8. [Installation und Deployment](#installation-und-deployment)
9. [Wartung und Störungen](#wartung-und-störungen)
10. [Sicherheit](#sicherheit)

## Datenfluss

```
ILIAS (edu-ID + TOTP) ──► scraper.py ──► downloads/KW_xx/<Kurs>/ ──► Google Drive "HSLU Agent/<Fach>/SWnn"
                                                         │
Zoom-Vorlesung ──► zoomrec (Server, Ton als MP3) ────────┤
Eigene Aufnahme / Zoom-Transkript ──► Drive _Eingang ──► process_inbox.py ──► nur Text: Transkript + Dossier (Gemini)
                                                         (Audio/Video wird nach dem Transkribieren gelöscht)
                                                         │
                                                         ▼
                         sync_notebooklm_api.py ──► NotebookLM "HSLU - <Fach>" (alle Quellen)
                    weekly_notebooklm_audio.py ──► NotebookLM "HSLU - <Fach> - SWnn" + Audio-Zusammenfassung
```

Das Dashboard (`dashboard.py`) zeigt Status, Logs, Live-Bildschirm und den Login-Zustand von Zoom.

## Verbindungen und Konten

| Verbindung | Konto | Wo hinterlegt | Erneuern |
|---|---|---|---|
| ILIAS / SWITCH edu-ID | HSLU-Studierendenkonto | `.env`: `HSLU_USERNAME`, `HSLU_PASSWORD`, `HSLU_TOTP_SECRET` | Nur bei Passwortwechsel |
| Google Drive + Docs (Ablage) | `massimo.folini@gelso.ch` (Besitzer des Zielordners) | `token_gelso.json` (Scopes cloud-platform, drive, documents), gewählt über `.env`: `GOOGLE_TOKEN_FILE=token_gelso.json` | `python maintenance/authenticate_gelso.py`, dann nach `/opt/KiAgentHSLU/` kopieren. Läuft nicht nach 7 Tagen ab (App ist als vertrauenswürdig markiert). |
| Alter Drive-Zugang | `mg.folini@gmail.com` | `token.json` (Client `credentials.json`), nur noch Rückfall ohne `GOOGLE_TOKEN_FILE`, und `upload_to_inbox.py` | Siehe [Google-Token](#google-token-abgelaufen) |
| Drive-Zielordner | Ordner `HSLU/Fächer/HSLU Agent` (gehört `massimo.folini@gelso.ch`) | `.env`: `GOOGLE_DRIVE_FOLDER_ID` | Pflicht: ohne ID bricht `GoogleWorkspace` ab und schreibt nie in "Meine Ablage" |
| NotebookLM Enterprise, Cloud TTS | `massimo.folini@gelso.ch` | `token_gelso.json` (OAuth, Scope `cloud-platform`, Client `client_secret_*.json`) | `python maintenance/authenticate_gelso.py`, dann nach `/opt/KiAgentHSLU/` kopieren |
| Gemini (Transkription, Dossiers) | API-Key | `.env`: `GEMINI_API_KEY`, optional `GEMINI_TRANSCRIBE_MODEL`, `GEMINI_LECTURE_MODEL` | Bei Bedarf |
| Zoom (Aufnahme) | HSLU-Zoom per SSO (Domäne `hslu`) | Zoom-Client im Container, Profil unter `/opt/zoomrec/profile/` | Per VNC neu anmelden, siehe [zoomrec](#zoom-aufnahme-zoomrec) |
| Warnungen | ntfy-Thema und optional Gmail-SMTP | `/opt/zoomrec/notify.env` | Gmail-App-Passwort trägt der Nutzer selbst ein |
| Dashboard | Benutzer `admin` | `.env`: `DASHBOARD_PASS` | Beliebig ändern, dann `sudo systemctl restart hslu-dashboard` |
| Server | SSH-Schlüssel `~/.ssh/id_ed25519` | Laptop | |

Keine dieser Dateien gehört ins Repository (`.gitignore`).

## Anforderungen an NotebookLM Enterprise

Damit die Notebooks und Audio-Zusammenfassungen entstehen, muss alles Folgende erfüllt sein:

1. **Google-Cloud-Projekt** `hslu-511808` (Projektnummer `584077347614`) im Gelso-Workspace.
2. **Region eu**: Endpunkt `https://eu-discoveryengine.googleapis.com`, Pfad `v1alpha/projects/584077347614/locations/eu`, Header `x-goog-user-project: hslu-511808`.
3. **API**: Discovery Engine API im Projekt aktiviert.
4. **Lizenz**: Gemini Enterprise (Standard) mit einer Lizenz, die `massimo.folini@gelso.ch` zugewiesen ist (Cloud Console → Gemini Enterprise → Nutzer verwalten, Standort eu). Ohne Lizenz antwortet die API mit Fehlern, auch ein Dienstkonto bräuchte eine eigene Lizenz.
5. **Anmeldung**: OAuth-Token des Gelso-Kontos in `token_gelso.json` mit Scope `https://www.googleapis.com/auth/cloud-platform`. Erzeugen mit `python maintenance/authenticate_gelso.py`.
6. **Sitzungsdauer**: In der Google-Admin-Konsole (Gelso) muss die OAuth-App als vertrauenswürdig markiert sein (App-Zugriffskontrolle) und unter "Sitzungssteuerung für Google Cloud" von der Neuanmeldung ausgenommen sein. Sonst läuft das Token nach 16 Stunden ab. Das ist seit Oktober 2026 eingerichtet.
7. **Freigabe**: Notebooks werden über `notebooks:share` mit Rolle `PROJECT_ROLE_WRITER` geteilt. Ob ein privates Gmail-Konto Enterprise-Notebooks öffnen kann, ist nicht bestätigt. Zugriff sicher über das Gelso-Konto.

Grenzen der API, die das Design bestimmen:

- **Eine Audio-Zusammenfassung pro Notebook.** Ein zweites `audioOverviews:create` gibt die bestehende zurück. Deshalb gibt es pro Fach und Schulwoche ein eigenes Notebook `HSLU - <Fach> - SWnn`. Für das Gesamt-Audio pro Fach wird die alte gelöscht (`DELETE .../audioOverviews/default`) und neu erzeugt.
- Optionen gehören in `generationOptions` (`episodeFocus`, `languageCode: "de"`). Eine Längenoption gibt es nicht.
- Herunterladen der Audios und Video-Zusammenfassungen gehen nur in der Oberfläche, nicht per API.
- Quellen brauchen Zeit zur Verarbeitung. Das Skript wartet 45 Sekunden und wiederholt eine gescheiterte Audio-Zusammenfassung bis zu 3-mal.

Oberfläche (mit dem Gelso-Konto öffnen): `https://notebooklm.cloud.google.com/eu/?project=584077347614`

## Steuerung: Dienste und Timer auf dem Server

| Unit | Takt | Startet | Aufgabe |
|---|---|---|---|
| `hslu-agent.service` | Dauerlauf, Job jeden Sonntag 18:00 | `main.py` | ILIAS-Scraping, Download nach `downloads/KW_xx`, Drive-Sync |
| `hslu-dashboard.service` | Dauerlauf | `dashboard.py` | Dashboard auf `127.0.0.1:5000` |
| `hslu-proxy.service` | Dauerlauf | nginx mit `deploy/proxy/nginx.conf` | HTTPS auf Port 8443 vor dem Dashboard (selbst signiertes Zertifikat) |
| `hslu-inbox.timer` | alle 15 Min | `maintenance/process_inbox.py` | Drive-Eingang: Transkript, Lesefassung, Dossier |
| `hslu-notebooks.timer` | stündlich | `maintenance/sync_notebooklm_api.py` | Quellen in die Fach-Notebooks `HSLU - <Fach>` |
| `hslu-weekly-nlm.timer` | täglich 04:30 UTC | `maintenance/weekly_notebooklm_audio.py` | Wochen-Notebooks + Audio, Gesamt-Audio pro Fach (höchstens alle 3 Tage) |
| `hslu-zoom-watch.timer` | alle 5 Min | `/opt/zoomrec/notify_signout.py` | Warnung, wenn Zoom abgemeldet ist |
| Docker-Container `zoomrec` | Dauerlauf | `/opt/zoomrec/audiorec.py` | Zoom-Vorlesungen nach `meetings.csv` als MP3 aufnehmen |
| `hslu-scheduler.service` | **deaktiviert** | `live_scheduler.py` | Alter Browser-Zoom-Bot, ersetzt durch zoomrec |
| `hslu-audio.timer` | **nicht installiert** | `maintenance/weekly_audio.py` | Eigene Audio-Vorlesungen mit Cloud TTS (ca. 1 USD pro Vorlesung), ersetzt durch NotebookLM-Audio |

Häufige Befehle:

```bash
systemctl list-timers | grep hslu                                   # wann läuft was
journalctl -u hslu-inbox -n 50 --no-pager                           # Log eines Dienstes
sudo systemctl start hslu-notebooks.service                         # Sync sofort starten
venv/bin/python maintenance/weekly_notebooklm_audio.py --dry-run    # was wäre fällig
venv/bin/python maintenance/weekly_notebooklm_audio.py --all --max 30 --no-total   # alle Wochen mit Material, auch kommende
```

Zustandsdateien auf dem Server: `notebooklm_api_state.json` (Fach-Notebooks), `weekly_nlm_state.json` (Wochen-Notebooks, Audio, Versuche), `inbox_state.json`, `drive_sync.json`, `ilias_registry.json`.

## Zoom-Aufnahme (zoomrec)

Der Server tritt den Vorlesungen mit dem echten Zoom-Client (Zoom Workplace 7.x) als angemeldeter Nutzer "Massimo Folini" bei und nimmt nur den Ton auf. Er beruht auf [kastldratza/zoomrec](https://github.com/kastldratza/zoomrec), stark angepasst. Die geänderten Dateien liegen in `deploy/zoomrec/`.

**Lebenszyklus (On-Demand):** HSLU meldet Zoom-Konten nach **120 Minuten Inaktivität** ab (Kontorichtlinie, Meldung "signed out for being inactive"). Diese Regel wird nicht umgangen und es werden keine Aktivitäten vorgetäuscht. Stattdessen läuft Zoom nur kurz vor und während der Vorlesungen: Im Leerlauf ist der Client beendet (sobald er angemeldet ist, nach 2 Minuten), 3 Minuten vor einem Termin startet `audiorec.py` ihn, prüft den Login und meldet bei Bedarf über SSO (Domäne `hslu`) neu an, nach der Aufnahme wird er wieder beendet. Die Microsoft-/HSLU-Sitzung im Firefox bleibt erhalten (`user.js` im Profil: Cookies und Sitzung werden beim Schliessen nicht gelöscht). Ob Zoom die Anmeldung über Tage ohne laufenden Client behält, ist erst mit dem Termin Do 12:50 bestätigt.

**Ablauf** (`audiorec.py`): Er liest `/opt/zoomrec/meetings.csv` (`weekday;time;duration;id;password;description;record;`, Zeiten Europe/Zurich). Zur Startzeit öffnet er `zoommtg://zoom.us/join?action=join&confno=<ID>&pwd=<Passcode>` und nimmt `speaker.monitor` mit ffmpeg als MP3 (128k) nach `/opt/zoomrec/recordings/` auf. Am Ende beendet er den Zoom-Client und startet ihn neu, denn Zoom 7 nennt das Meeting-Fenster nur "Meeting". Alle 2 Minuten schreibt er den Login-Zustand nach `zoom_status.json`, alle 30 Sekunden ein Bildschirmfoto nach `live.png` (für die Live-Ansicht im Dashboard).

**Termine** (Herbstsemester 2026, je 140 Minuten): Mo 15:30 ASTAT, Do 12:50 DBS, Do 15:30 VSK, Do 18:30 AEDCIT, Fr 09:05 VSK. Die Passcodes stehen nur auf dem Server, nicht im Repository. Die Meetings verlangen ein angemeldetes Zoom-Konto, Gäste werden abgewiesen.

**Container-Start** (aus `/opt/zoomrec`):

```bash
P=$(pwd)/profile
docker run -d --name zoomrec --restart unless-stopped --memory 3g --shm-size 512m \
  --security-opt apparmor=docker-zoomrec --security-opt seccomp=$(pwd)/seccomp-zoomrec.json \
  -e TZ=Europe/Zurich -e XDG_SESSION_TYPE=x11 -e DEBUG=True -e VNC_PW="$(cat .vnc_pw)" \
  -e QTWEBENGINE_DISABLE_SANDBOX=1 -e QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox \
  -v $(pwd)/audiorec.py:/home/zoomrec/audiorec.py:ro \
  -v $P/.zoom:/home/zoomrec/.zoom -v $P/.config:/home/zoomrec/.config \
  -v $P/.cache:/home/zoomrec/.cache -v $P/.mozilla:/home/zoomrec/.mozilla \
  -v $(pwd)/recordings:/home/zoomrec/recordings -v $(pwd)/meetings.csv:/home/zoomrec/meetings.csv:ro \
  -p 127.0.0.1:5901:5901 zoomrec
```

**Sicherheit des Containers.** Der Zoom-Client braucht User-Namespaces. Ubuntu 24.04 verbietet sie normalen Prozessen (`kernel.apparmor_restrict_unprivileged_userns=1`). Diese Einstellung bleibt global unverändert, und der Container bekommt auch kein `SYS_ADMIN`. Stattdessen gibt es zwei enge Ausnahmen nur für diesen Container:

- **AppArmor:** Das Profil `/etc/apparmor.d/docker-zoomrec` (`deploy/zoomrec/docker-zoomrec`) erlaubt `userns`. Laden mit `sudo apparmor_parser -r /etc/apparmor.d/docker-zoomrec`. Nach einem Server-Neustart lädt AppArmor das Profil von selbst.
- **Seccomp:** `seccomp-zoomrec.json` ist das Docker-Standardprofil plus `unshare`, `setns`, `clone` und `clone3`.

**Image bauen:** `cd /opt/zoomrec && docker build -t zoomrec .`. Das Dockerfile installiert den aktuellen Zoom-Client von `https://zoom.us/client/latest/zoom_amd64.deb` sowie Firefox (für den SSO-Login), `xdg-utils` und `wmctrl`. Zusätzlich muss `pillow>=9.2.0,<11` gesetzt sein, sonst stürzt pyscreeze ab.

**Neu anmelden (VNC).** Das ist nötig, wenn Dashboard oder Warnung "Zoom abgemeldet" melden:

1. Tunnel öffnen und das Fenster offen lassen:
   ```bash
   ssh -i ~/.ssh/id_ed25519 -L 5901:127.0.0.1:5901 ubuntu@179.237.110.120
   ```
2. Das VNC-Passwort holen:
   ```bash
   ssh -i ~/.ssh/id_ed25519 ubuntu@179.237.110.120 cat /opt/zoomrec/.vnc_pw
   ```
3. Mit TigerVNC (`winget install TigerVNC.TigerVNC`) auf `localhost:5901` verbinden.
4. Im Zoom-Fenster Sign in → SSO → Domäne `hslu`. Im Firefox anmelden, "Angemeldet bleiben" anhaken und den `zoommtg://`-Link mit Zoom öffnen.
5. Angemeldet ist der Client, wenn der Fenstertitel "Zoom Workplace - Licensed account" lautet.
6. Einmalig unter Settings → Audio setzen: "Automatically join audio by computer" und "Mute my microphone when joining".

**Warnung bei Abmeldung:** `notify_signout.py` (Timer `hslu-zoom-watch`) warnt, wenn Zoom abgemeldet ist oder der Container seit 20 Minuten nichts meldet. Die Warnung wiederholt sich höchstens alle 6 Stunden, nach der Behebung folgt eine Entwarnung. Die Kanäle stehen in `/opt/zoomrec/notify.env`:

- `NTFY_TOPIC` für Push über ntfy.sh. Am 02.11.2026 war das Tageskontingent der Server-IP erschöpft, der Kanal ist daher unzuverlässig.
- `SMTP_*` und `MAIL_TO` für Mail. Für Gmail braucht es ein App-Passwort, das der Nutzer selbst einträgt.

Das Dashboard zeigt unabhängig davon einen roten Balken und in "Zugangsdaten-Status" die Zeile "Zoom-Aufnahme (Server)".

**Weiterverarbeitung:** Fertige MP3s (Name `YYYY-MM-DD_HH-MM_<Kürzel>.mp3`, Kürzel ASTAT, DBS, VSK, AEDCIT, KRR, PREN) holt `process_inbox.py` (alle 15 Minuten) frühestens 5 Minuten nach dem Ende ab. Er transkribiert, legt Rohtranskript (mit Zeitmarken), Lesefassung und Dossier unter `<Fach>/Transkripte` und `<Fach>/Dossiers` ab und **löscht danach die MP3**. Die Schulwoche kommt aus dem Datum. Das Aufnehmen fremder Vorlesungen ist nur mit Erlaubnis der Dozierenden zulässig.

## Schulwochen und Ablage

- `weeks.py` ordnet jede Datei einer Schulwoche zu: SW01 ist die Woche ab Montag 14.09.2026, SW00 steht für Allgemeines. Die Zuordnung kommt aus dem Ordnerpfad, dem Dateinamen oder dem Datum.
- Drive-Struktur unter dem Zielordner:
  - `<Fach>/SWnn/` für die Unterlagen
  - `<Fach>/Dossiers/`
  - `<Fach>/Transkripte/` (Google Docs)
  - `<Fach>/Live-Aufnahmen/`
  - `_Eingang/<Fach>/SWnn/` für eigene Aufnahmen oder Zoom-Transkripte
  - `_Eingang/_Verarbeitet/`
- In Drive und auf dem Server bleibt nur Text. Eigene Audio- oder Videodateien im Eingang werden nach dem Transkribieren in den Drive-Papierkorb gelegt (30 Tage wiederherstellbar) und lokal gelöscht, erst nach erfolgreichem Upload.
- Der Drive-Eingang nimmt Audio und Video (mp3, mp4, m4a, wav …) und Texttranskripte (.txt, .vtt, .md, auch das Zoom-Docs-Format `HH:MM:SS --> HH:MM:SS`). Aufnahmen ohne Ton werden abgelehnt. Hochladen vom PC:
  ```bash
  python maintenance/upload_to_inbox.py <Fach> <Woche> <Datei> [Name]
  ```
- `laptop/record_system_audio.py` nimmt den Systemton des Windows-Laptops auf und legt ihn in den Eingang. Er ist ein Ausweichweg, falls zoomrec ausfällt.
  ```bash
  python laptop/record_system_audio.py --subject Datenbanksysteme --at 12:50 --minutes 140
  ```
  Voraussetzungen: ffmpeg und `pip install -r laptop/requirements-laptop.txt`.

## Dateien im Projekt

| Datei | Aufgabe |
|---|---|
| `main.py` | Daemon mit `weekly_job()` (Sonntag 18:00): Scraping, Downloads, Drive-Sync, optional Dossiers. |
| `run_weeks.py` | Einmaliger manueller Lauf, z. B. `python run_weeks.py "KW 41 (08.10.2026)"`. |
| `scraper.py`, `registry.py` | Playwright-Scraper für ILIAS (edu-ID, TOTP, `cmd=sendfile`) und das Verzeichnis bereits geladener Dateien (`ilias_registry.json`). |
| `google_integration.py` | Google Drive und Docs. Bricht ab, wenn `GOOGLE_DRIVE_FOLDER_ID` fehlt. |
| `llm_processor.py`, `transcriber.py` | Gemini-Dossiers und Transkription. |
| `weeks.py` | Zuordnung zur Schulwoche. |
| `dashboard.py` | Flask-Dashboard: Start, Logs (Agent und zoomrec), Live-Bildschirm, Konfiguration, Verbindungstests, Zoom-Login-Status. |
| `detect_live_courses.py` | Erkennt Fächer und Live-Kurse (erzeugt `live_meetings.json`). |
| `zoom_downloader.py`, `live_zoom_bot.py`, `live_scheduler.py`, `scripts/run_live_zoom.sh` | Alter Browser-Zoom-Weg (Cloud-Aufzeichnungen, Live-Bot). Der Live-Bot ist deaktiviert, Zoom blockiert ihn. |
| `notebooklm_integration.py` | Alte inoffizielle NotebookLM-Anbindung, nicht mehr genutzt. |
| `maintenance/sync_notebooklm_api.py` | Offizieller Sync in die Fach-Notebooks. |
| `maintenance/weekly_notebooklm_audio.py` | Wochen-Notebooks und Audio-Zusammenfassungen (`--dry-run`, `--subject`, `--week`, `--max`, `--all`, `--no-total`). |
| `maintenance/process_inbox.py`, `maintenance/upload_to_inbox.py` | Drive-Eingang verarbeiten und befüllen. |
| `maintenance/authenticate_google.py`, `maintenance/authenticate_gelso.py` | OAuth-Login für `token.json` (Gmail-Drive) und `token_gelso.json` (NotebookLM). |
| `maintenance/clean_drive_zips.py` | Räumt ZIPs und Junk-Ordner (.venv, .ipynb_checkpoints …) im Drive-Zielordner auf (Trockenlauf ohne `--apply`). |
| `maintenance/weekly_audio.py` | Eigene TTS-Audio-Vorlesungen (abgelöst, Timer nicht aktiv). |
| `maintenance/*` (übrige) | Einmalige Migrations- und Aufräumskripte. Aus dem Projektroot starten: `python maintenance/<skript>.py`. |
| `checks/` | Verbindungstests (Google, Gemini, ILIAS, Zoom), auch über die Test-Buttons im Dashboard. |
| `laptop/` | Systemton-Rekorder für Windows. |
| `deploy/` | systemd-Units, `setup_server.sh`, `proxy/nginx.conf`, `zoomrec/` (Dockerfile, Entrypoint, `audiorec.py`, Warnung, AppArmor- und Seccomp-Profil). |

## Installation und Deployment

Lokal:

```bash
git clone https://github.com/MassimoFolini/HSLU-AGENT.git
cd HSLU-AGENT
pip install -r requirements.txt
playwright install chromium
cp .env.example .env          # Werte eintragen, mindestens DASHBOARD_PASS und GOOGLE_DRIVE_FOLDER_ID
python dashboard.py           # http://localhost:5000, Benutzer admin
```

Server (Ubuntu 24.04):

1. Projekt nach `/opt/KiAgentHSLU` kopieren, Geheimnisse dazulegen: `.env`, `credentials.json`, `token.json`, `token_gelso.json`, `client_secret_*.json`.
2. `cd deploy && sudo ./setup_server.sh` richtet das venv mit Playwright, `hslu-agent` und `hslu-dashboard` ein.
3. Weitere Units aus `deploy/` nach `/etc/systemd/system/` kopieren und einschalten:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now hslu-proxy hslu-inbox.timer hslu-notebooks.timer hslu-weekly-nlm.timer hslu-zoom-watch.timer
   ```
4. zoomrec:
   - Repository nach `/opt/zoomrec` klonen und die Dateien aus `deploy/zoomrec/` darüberlegen: `Dockerfile`, `audiorec.py`, `notify_signout.py`, `seccomp-zoomrec.json`, `entrypoint.sh` und `requirements.txt` nach `res/`.
   - AppArmor-Profil laden.
   - `meetings.csv`, `.vnc_pw` und `notify.env` anlegen.
   - Image bauen, Container starten (Befehl oben), per VNC anmelden.

Einzelne Dateien aktualisieren: `scp <datei> ubuntu@179.237.110.120:/opt/KiAgentHSLU/<datei>`. Danach den betroffenen Dienst neu starten, Timer-Dienste nehmen die neue Version beim nächsten Lauf.

## Wartung und Störungen

### Google-Token abgelaufen

Seit dem 03.11.2026 nutzt die Ablage `token_gelso.json` (kein 7-Tage-Ablauf). Der folgende Abschnitt gilt nur noch, wenn `GOOGLE_TOKEN_FILE` nicht gesetzt ist und das alte Gmail-Token `token.json` verwendet wird. Der Fehler `invalid_grant: Token has been expired or revoked` betrifft dann `token.json`. Die OAuth-App steht im Testmodus, deshalb laufen Tokens nach 7 Tagen ab. Erneuern auf dem PC:

```bash
python maintenance/authenticate_google.py
scp token.json ubuntu@179.237.110.120:/opt/KiAgentHSLU/token.json
```

Dauerhaft lösen: In der Google Cloud Console unter APIs & Dienste → OAuth-Zustimmungsbildschirm auf "In Produktion" stellen. Das ist noch offen.

### Weitere Störungen

| Symptom | Ursache | Behebung |
|---|---|---|
| NotebookLM-Sync meldet "Gelso-Token ungueltig" | `token_gelso.json` abgelaufen | `python maintenance/authenticate_gelso.py`, kopieren. Prüfen, ob die App in der Admin-Konsole noch vertrauenswürdig ist. |
| Wochen-Audio fehlt (`audio: false` in `weekly_nlm_state.json`) | Quellen waren noch nicht verarbeitet | Wird beim nächsten Lauf wiederholt, höchstens 3 Versuche. |
| Dashboard: roter Balken "Zoom ist abgemeldet" | Zoom-Sitzung abgelaufen (z. B. 120-Minuten-Regel oder Microsoft verlangt Passwort) | VNC-Anmeldung (siehe zoomrec): Passwort und 2FA gibst du selbst ein. |
| Zoom: "Sign in to join this meeting" | Client nicht angemeldet | VNC-Anmeldung. |
| zoomrec-Aufnahme still | Zoom-Audio nicht verbunden | In Zoom-Settings "Automatically join audio by computer" prüfen. |
| Dateien landen in "Meine Ablage" | `GOOGLE_DRIVE_FOLDER_ID` fehlt | Der Code bricht jetzt ab. ID in `.env` eintragen. |

## Sicherheit

- Das Dashboard hat kein Standardpasswort. Ohne `DASHBOARD_PASS` ist es gesperrt.
- Es lauscht nur auf `127.0.0.1:5000`. Von aussen ist es nur über den HTTPS-Proxy auf Port 8443 erreichbar, also aus dem ganzen Internet, geschützt nur durch das Passwort.
- `.env`, `credentials*.json`, `client_secret*.json`, `token*.json`, `service_account.json`, Aufnahmen (`*.mp3`, `recordings/`) und die zoomrec-Terminliste mit Passcodes gehören nie ins Repository.
- zoomrec: VNC nur auf `127.0.0.1:5901`, Zugang über SSH-Tunnel, eigenes VNC-Passwort in `/opt/zoomrec/.vnc_pw`. Gespeicherte Zoom-Sitzung unter `/opt/zoomrec/profile/`, wie ein Passwort behandeln.
