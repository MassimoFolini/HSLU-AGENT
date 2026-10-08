# HSLU KI-Studienassistent

Ein automatisierter Agent für Studierende der Hochschule Luzern (HSLU). Er loggt sich per SWITCH edu-ID (mit TOTP) in ILIAS ein, lädt alle Kursunterlagen herunter, sichert Zoom-Aufzeichnungen (Microsoft-365-SSO) und synchronisiert alles in eine Ordnerstruktur (Fach, Woche) auf Google Drive. Optional erstellt Gemini daraus Wochen-Dossiers, und NotebookLM kann die Unterlagen als Quellen nutzen.

## Architektur

| Datei | Aufgabe |
|---|---|
| `main.py` | Daemon mit `weekly_job()`. Läuft jeden Sonntag um 18:00 (Scraping, Zoom-Download, Drive-Sync, optional Dossier). |
| `run_weeks.py` | Einmaliger manueller Lauf. Optional mit Wochenbezeichnung als Argument: `python run_weeks.py "KW 41 (08.10.2026)"`. |
| `scraper.py` | Playwright-Scraper für ILIAS (edu-ID, TOTP, verschachtelte Ordner, `cmd=sendfile`-Downloads). |
| `registry.py` | `ilias_registry.json`: merkt sich, was bereits heruntergeladen wurde. |
| `zoom_downloader.py`, `live_zoom_bot.py`, `scripts/run_live_zoom.sh` | Zoom-Aufzeichnungen und Live-Meetings (Xvfb, PulseAudio, ffmpeg). |
| `detect_live_courses.py` | Erkennt Fächer und Live-Kurse. |
| `google_integration.py` | Google Drive und Docs API. |
| `llm_processor.py`, `transcriber.py` | Gemini-Dossiers und Transkription. |
| `notebooklm_integration.py` | NotebookLM-Anbindung. |
| `dashboard.py` | Flask-Dashboard (Port 5000, Basic Auth): Läufe starten, Logs lesen, Konfiguration bearbeiten. |
| `checks/` | Verbindungschecks (Google, Gemini, ILIAS, Zoom), werden von den Test-Buttons im Dashboard gestartet. |
| `maintenance/` | Wartungs- und Migrationsskripte (Backfill, Duplikate bereinigen, NotebookLM-Sync, Google-Auth usw.). Aus dem Projektroot starten: `python maintenance/<skript>.py`. |
| `scripts/` | Shell-Skripte (`start_run.sh`, `run_fetcher.sh`, `run_live_zoom.sh`). |
| `deploy/` | `setup_server.sh` und systemd-Units für Ubuntu. |

## Installation

Voraussetzungen: Python 3.10+, ein Google-Cloud-Projekt mit aktivierter Drive- und Docs-API (Service Account oder OAuth), HSLU-Login samt TOTP-Secret.

```bash
git clone https://github.com/MassimoFolini/HSLU-AGENT.git
cd HSLU-AGENT
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Trage in `.env` mindestens `DASHBOARD_PASS` ein und fülle die übrigen Werte (siehe `.env.example`). Danach:

```bash
python dashboard.py
```

Das Dashboard läuft unter http://localhost:5000 (Benutzer `admin`). Die Konfiguration lässt sich dort im Tab Konfiguration bearbeiten.

## Sicherheit

* Das Dashboard hat kein Standardpasswort. Ohne `DASHBOARD_PASS` in `.env` ist der Zugang gesperrt.
* Es bindet standardmässig nur an `127.0.0.1`. Für den Serverbetrieb `DASHBOARD_HOST=0.0.0.0` setzen und einen HTTPS-Reverse-Proxy (Caddy oder nginx) davorschalten. Basic Auth über HTTP überträgt das Passwort im Klartext.
* `.env`, `credentials*.json`, `token*.json` und `service_account.json` sind in `.gitignore` und dürfen nie committet werden.

## Server-Deployment (Ubuntu)

1. Projekt nach `/opt/KiAgentHSLU` kopieren.
2. Setup ausführen:

   ```bash
   cd /opt/KiAgentHSLU/deploy
   sudo chmod +x setup_server.sh
   sudo ./setup_server.sh
   ```

3. Das Skript richtet ein Virtual Environment mit Playwright und zwei systemd-Dienste ein: `hslu-dashboard.service` und `hslu-agent.service`.
4. Das Dashboard über den Reverse-Proxy auf Port 443 erreichbar machen. Port 5000 nicht direkt freigeben.
