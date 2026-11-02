# zoomrec (angepasst)

Grundlage: https://github.com/kastldratza/zoomrec (MIT, siehe `LICENSE-zoomrec`). Die Dateien hier ersetzen die Originale in `/opt/zoomrec` auf dem Server:

| Datei | Ziel auf dem Server |
|---|---|
| `Dockerfile` | `/opt/zoomrec/Dockerfile` (Zoom latest, Firefox, xdg-utils, wmctrl) |
| `entrypoint.sh`, `requirements.txt` | `/opt/zoomrec/res/` |
| `audiorec.py` | `/opt/zoomrec/audiorec.py` (in den Container gemountet) |
| `notify_signout.py` | `/opt/zoomrec/notify_signout.py` |
| `seccomp-zoomrec.json` | `/opt/zoomrec/seccomp-zoomrec.json` |
| `docker-zoomrec` | `/etc/apparmor.d/docker-zoomrec` |
| `hslu-zoom-watch.service`, `.timer` | `/etc/systemd/system/` |

Nicht im Repository: `meetings.csv` (Passcodes), `notify.env`, `.vnc_pw`, `profile/` (Zoom-Sitzung), `recordings/`. Betrieb und Neuanmeldung: Abschnitt "Zoom-Aufnahme (zoomrec)" im Haupt-README.
