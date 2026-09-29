import os
import google.generativeai as genai

class LLMProcessor:
    def __init__(self):
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def generate_dossier(self, week_title, transcript_text, pdf_text_content=""):
        """Generates a structured weekly summary using Gemini."""
        print(f"Generating dossier for {week_title}...")
        
        prompt = f"""
        Du bist ein hochspezialisierter KI-Studienassistent für ein Informatik-Studium an der HSLU (Fokus: Softwareentwicklung).
        Erstelle basierend auf dem Vorlesungstranskript und den Skriptinhalten ein konsolidiertes Dossier für die Woche '{week_title}'.
        
        Das Dossier MUSS folgende Struktur als Markdown enthalten:
        1. Wochentitel & Datum
        2. Kern-Lernziele der Woche: (Was muss verstanden werden?)
        3. Zusammenfassung des Stoffs: (Nutze Bulletpoints und ggf. Code-Blöcke)
        4. Wichtige Erkenntnisse aus der Aufzeichnung: (Hinweise zu Prüfungen, besonders betonte Themen)
        5. To-Do-Liste: (Übungen, Abgaben, Code-Beispiele)

        Transkript:
        {transcript_text[:15000]} # Truncated for token limits in this example

        Zusätzliche Skriptinhalte:
        {pdf_text_content[:5000]}
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Error generating dossier: {e}")
            return f"# Dossier konnte nicht erstellt werden.\nFehler: {e}"
