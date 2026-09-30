import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

class LLMProcessor:
    def __init__(self):
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        # Nutzen gemini-2.5-flash für schnelle, hochpräzise und tiefgehende Analyse
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def generate_dossier(self, week_title, transcript_text, pdf_text_content=""):
        """Generiert ein umfassendes Studien- und Prüfungsvorbereitungsdossier."""
        print(f"Generiere interaktives Studien-Dossier für {week_title}...")
        
        prompt = f"""
        Du bist der persönliche KI-Studienassistent für einen Informatik-Studenten an der HSLU (Spezialisierung Softwareentwicklung).
        Deine Aufgabe ist es, ihm das maximale Mass an Denkarbeit und Vorbereitung abzunehmen!
        
        Erstelle basierend auf dem Vorlesungstranskript, den Skripten und den Modulunterlagen ein vollständiges, hochprofessionelles Lern- und Prüfungs-Dossier für die Woche: '{week_title}'.

        WICHTIG: Der Student soll NICHT selbst Fragen an ein KI-Tool oder NotebookLM formulieren müssen! 
        Du musst die wichtigsten Prüfungsfragen, Selbsttests, Musterlösungen und Verständnisfragen BEREITS VOLLSTÄNDIG VORBEREITEN und beantworten!

        Das Dossier MUSS zwingend folgende klare Struktur auf Deutsch haben:

        # {week_title}

        ## 1. Wochentitel & Kontext
        - **Modul & Kalenderwoche:**
        - **Themenschwerpunkt:**

        ## 2. Kern-Lernziele der Woche
        (Präzise Bulletpoints: Was MUSS man nach dieser Woche beherrschen, verstehen und anwenden können?)

        ## 3. Kompakte Zusammenfassung des Stoffs (mit Code & Tabellen)
        (Detailliert, technisch präzise, Fokus auf Softwareentwicklung. Verwende Code-Blöcke für SQL, Python, Java etc. und Tabellen, wo sinnvoll).

        ## 4. Wichtige Dozenten-Hinweise & MEP-Prüfungsrelevanz
        (Was hat der Dozent im Transkript besonders betont? Welche Fallen oder MEP-Schwerpunkte wurden erwähnt?)

        ## 5. Vorbereiteter Fragenkatalog & Prüfungssimulation (MIT MUSTERLÖSUNGEN)
        (Nimm dem Studenten das Fragen-Überlegen ab! Formuliere mindestens 5-7 anspruchsvolle, realistische Prüfungsfragen, die in der HSLU-Modulendprüfung (MEP) vorkommen könnten, und liefere die perfekte Musterantwort direkt mit:)
        - **Frage 1 (Theorie/Verständnis):** ...
          *Musterlösung:* ...
        - **Frage 2 (Praxis/Code/Modellierung):** ...
          *Musterlösung & Erklärung:* ...
        - **Frage 3 (Typische Prüfungsfalle):** ...
          *Musterlösung:* ...

        ## 6. NotebookLM Copy-Paste Prompts
        (Falls der Student in NotebookLM noch tiefer in den Stoff bohren möchte, gib ihm 3-5 fertige, messerscharfe Prompts, die er mit einem Klick in NotebookLM kopieren kann).

        ## 7. To-Do-Liste & Übungsaufgaben
        (Konkrete Handlungsanweisungen: Was muss bis wann implementiert oder abgegeben werden?)

        ---
        QUELLENMATERIAL:
        Transkript:
        {transcript_text[:20000]}

        Modulinhalte / Folien:
        {pdf_text_content[:8000]}
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Fehler bei Dossier-Generierung: {e}")
            return f"# Dossier konnte nicht erstellt werden.\nFehler: {e}"
