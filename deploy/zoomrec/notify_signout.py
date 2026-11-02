"""Warnt, wenn der Zoom-Client in zoomrec abgemeldet ist oder der Container nicht mehr meldet.

Liest recordings/zoom_status.json (schreibt audiorec.py alle 2 Minuten). Kanaele aus /opt/zoomrec/notify.env:
  NTFY_TOPIC=...                      Push ueber ntfy.sh (App "ntfy" aufs Handy, Thema abonnieren)
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO   optional zusaetzlich per Mail
Wiederholt die Warnung hoechstens alle 6 Stunden und meldet, wenn wieder alles gut ist.
"""
import json
import os
import smtplib
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage

BASE = "/opt/zoomrec"
STATUS = os.path.join(BASE, "recordings", "zoom_status.json")
STATE = os.path.join(BASE, "notify_state.json")
STALE = timedelta(minutes=20)
REPEAT = timedelta(hours=6)


def env():
    out = {}
    try:
        for line in open(os.path.join(BASE, "notify.env"), encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                out[k] = v.strip().strip("'\"")
    except FileNotFoundError:
        pass
    return out


def send(cfg, title, text, urgent):
    if cfg.get("NTFY_TOPIC"):
        req = urllib.request.Request(f"https://ntfy.sh/{cfg['NTFY_TOPIC']}", data=text.encode("utf-8"), method="POST",
                                     headers={"Title": title, "Priority": "urgent" if urgent else "default",
                                              "Tags": "rotating_light" if urgent else "white_check_mark"})
        urllib.request.urlopen(req, timeout=20).read()
    if cfg.get("SMTP_HOST") and cfg.get("MAIL_TO"):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = title, cfg.get("SMTP_USER", cfg["MAIL_TO"]), cfg["MAIL_TO"]
        msg.set_content(text)
        with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg.get("SMTP_PORT", 587)), timeout=30) as s:
            s.starttls()
            if cfg.get("SMTP_USER"):
                s.login(cfg["SMTP_USER"], cfg.get("SMTP_PASS", ""))
            s.send_message(msg)


def main():
    now = datetime.now()
    try:
        st = json.load(open(STATUS, encoding="utf-8"))
        checked = datetime.fromisoformat(st["checked"])
        problem = None if st.get("signed_in") else "Zoom ist ABGEMELDET"
        if now - checked > STALE:
            problem = f"zoomrec meldet sich seit {checked:%d.%m. %H:%M} nicht mehr (Container aus?)"
    except Exception as e:
        problem = f"Zoom-Status nicht lesbar ({e.__class__.__name__})"
    try:
        state = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        state = {}
    cfg = env()
    if problem:
        last = state.get("alerted")
        if last and now - datetime.fromisoformat(last) < REPEAT:
            return
        send(cfg, "HSLU Zoom-Aufnahme: neu einloggen!",
             f"{problem}.\nDie Vorlesungen werden NICHT aufgenommen, bis du dich per VNC neu anmeldest:\n"
             "ssh -i ~/.ssh/id_ed25519 -L 5901:127.0.0.1:5901 ubuntu@179.237.110.120\n"
             "dann VNC-Viewer auf localhost:5901, in Zoom: Sign in -> SSO -> hslu.", True)
        state["alerted"] = now.isoformat(timespec="seconds")
        print(now, "Warnung gesendet:", problem, flush=True)
    elif state.get("alerted"):
        send(cfg, "HSLU Zoom-Aufnahme: wieder angemeldet", "Zoom ist wieder angemeldet, die Aufnahmen laufen.", False)
        state.pop("alerted")
        print(now, "Entwarnung gesendet", flush=True)
    json.dump(state, open(STATE, "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
