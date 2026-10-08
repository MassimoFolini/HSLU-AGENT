import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os
import sys
import shutil
from dotenv import load_dotenv

load_dotenv()

def test_environment():
    print("=" * 60)
    print("1. UMGEBUNGSVARIABLEN (.env)")
    print("=" * 60)
    
    username = os.environ.get("HSLU_USERNAME")
    password = os.environ.get("HSLU_PASSWORD")
    totp_secret = os.environ.get("HSLU_TOTP_SECRET")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    print(f"HSLU_USERNAME: {'[OK] Gesetz' if username else '[FEHLT]'}")
    print(f"HSLU_PASSWORD: {'[OK] Gesetzt' if password else '[FEHLT]'}")
    print(f"HSLU_TOTP_SECRET: {'[OK] Gesetzt' if totp_secret and totp_secret != 'DEIN_TOTP_SETUP_KEY_OHNE_LEERZEICHEN' else '[FEHLT / Platzhalter]'}")
    print(f"GEMINI_API_KEY: {'[OK] Gesetzt' if gemini_key and gemini_key != 'AIzaSy...' else '[FEHLT / Platzhalter]'}")
    
    print("\n" + "=" * 60)
    print("2. TOTP 2FA CODE-TEST")
    print("=" * 60)
    if totp_secret and totp_secret != "DEIN_TOTP_SETUP_KEY_OHNE_LEERZEICHEN":
        try:
            import pyotp
            totp = pyotp.TOTP(totp_secret.replace(" ", ""))
            code = totp.now()
            print(f"Aktueller 6-stelliger Code: {code}")
            print("-> Vergleiche diesen Code mit deiner Authenticator App auf dem Handy!")
        except Exception as e:
            print(f"Fehler bei TOTP-Generierung: {e}")
    else:
        print("Übersprungen: HSLU_TOTP_SECRET ist noch nicht konfiguriert.")

    print("\n" + "=" * 60)
    print("3. SYSTEMABHÄNGIGKEITEN")
    print("=" * 60)
    ffmpeg_installed = shutil.which("ffmpeg") is not None
    print(f"ffmpeg im System-PATH: {'[OK] Gefunden' if ffmpeg_installed else '[FEHLT] Bitte installiere ffmpeg (z.B. winget install ffmpeg)'}")

    print("\n" + "=" * 60)
    print("4. GEMINI API TEST")
    print("=" * 60)
    if gemini_key and gemini_key != "AIzaSy...":
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            res = model.generate_content("Antworte nur mit: 'Gemini Verbindung erfolgreich!'")
            print(f"Antwort von Gemini: {res.text.strip()}")
        except Exception as e:
            print(f"Fehler beim Gemini-Test: {e}")
    else:
        print("Übersprungen: GEMINI_API_KEY noch nicht eingetragen.")

    print("\n" + "=" * 60)
    print("Test abgeschlossen.")
    print("=" * 60)

if __name__ == "__main__":
    test_environment()
