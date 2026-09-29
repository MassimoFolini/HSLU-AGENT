# HSLU KI-Studienassistent

Ein autonomer Python-Agent, der wöchentlich HSLU-Lernmaterialien (ILIAS/Moodle/Panopto) sammelt, Vorlesungen transkribiert und den Inhalt mithilfe von Google Gemini 1.5 Pro zusammenfasst. Die Ergebnisse werden strukturiert in Google Drive und Google Docs abgelegt.

## Setup

1. **Abhängigkeiten installieren:**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

2. **FFmpeg installieren:**
   Stelle sicher, dass `ffmpeg` auf deinem Windows-Rechner installiert und im PATH verfügbar ist. (z.B. über `winget install ffmpeg`).

3. **Umgebungsvariablen:**
   Kopiere `.env.example` nach `.env` und trage deine Zugangsdaten und API-Schlüssel ein.

4. **Google API Credentials:**
   Speichere deine `credentials.json` (für Google Drive/Docs API) im Hauptverzeichnis ab.

## Ausführung

Der Agent kann manuell gestartet werden oder durchgehend laufen und den wöchentlichen Schedule (Sonntag 18:00 Uhr) abarbeiten:

```bash
python main.py
```
