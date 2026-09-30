import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

class LLMProcessor:
    def __init__(self, memory_file="agent_memory.json"):
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        # Nutzen gemini-3.5-flash um 2.5 Rate Limits (20 Req/Tag) zu umgehen
        self.model = genai.GenerativeModel('gemini-3.5-flash')
        self.memory_file = memory_file
        self.memory = self._load_memory()

    def _load_memory(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"subjects": {}, "global_preferences": "Fokus auf Softwareentwicklung, praxisnahe Beispiele und klare Code-Snippets."}

    def _save_memory(self):
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=4, ensure_ascii=False)

    def adapt_strategy_for_subject(self, subject_code, pdf_text_content):
        """Der Agent reflektiert über das Material und passt seine EIGENE Instruktion für die Zukunft an!"""
        if not subject_code or subject_code == "UNKNOWN" or not pdf_text_content:
            return "Fokus auf allgemeine Softwareentwicklung."
            
        if subject_code in self.memory["subjects"]:
            return self.memory["subjects"][subject_code]
            
        print(f"\n[Meta-Agent] Analysiere Material für {subject_code}, um eigene Lernstrategie zu optimieren...")
        meta_prompt = f"""
        Du bist ein Meta-Agent. Deine Aufgabe ist es, einen anderen KI-Agenten zu verbessern.
        Hier ist Textmaterial aus einem Hochschulmodul ({subject_code}).
        
        Analysiere das Material kurz und entscheide: Wie muss der KI-Agent parametrisiert werden, um optimale Prüfungs-Dossiers für *genau dieses Fach* zu schreiben?
        - Ist es Mathe/Logik-lastig? (Dann Fokus auf Formeln, Beweise, Wahrheitstabellen)
        - Ist es Code-lastig? (Dann Fokus auf Code-Beispiele, Architekturmuster)
        - Ist es Management/Theorie-lastig? (Dann Fokus auf Definitionen, Prozesse, Diagramme)
        
        Schreibe NUR einen prägnanten System-Prompt (max 3-4 Sätze), den wir dem Agenten als "Spezial-Instruktion" übergeben. Er soll direkt als Anweisung formuliert sein (z.B. "Fokussiere dich auf...").
        
        Material-Auszug:
        {pdf_text_content[:4000]}
        """
        
        import time
        for attempt in range(3):
            try:
                response = self.model.generate_content(meta_prompt)
                new_strategy = response.text.strip()
                self.memory["subjects"][subject_code] = new_strategy
                self._save_memory()
                print(f"[Self-Improvement] Neue Strategie gelernt und dauerhaft gespeichert:\n -> {new_strategy}\n")
                return new_strategy
            except Exception as e:
                print(f"[Meta-Agent Fehler] (Versuch {attempt+1}): {e}")
                if attempt < 2:
                    time.sleep(10)
                else:
                    return "Fokus auf allgemeine Softwareentwicklung."

    def generate_dossier(self, week_title, transcript_text, pdf_text_content="", subject_code="UNKNOWN"):
        """Generiert ein umfassendes Studien- und Prüfungsvorbereitungsdossier."""
        print(f"Generiere interaktives Studien-Dossier für {week_title}...")
        
        # 1. Self-Adaptation: Lade oder erlerne die beste Strategie für dieses Fach
        subject_strategy = self.adapt_strategy_for_subject(subject_code, pdf_text_content)
        global_pref = self.memory.get("global_preferences", "")
        
        prompt = f"""
        Du bist der persönliche KI-Studienassistent für einen Informatik-Studenten an der HSLU.
        Deine Aufgabe ist es, ihm das maximale Mass an Denkarbeit und Vorbereitung abzunehmen!
        
        === DEINE SPEZIFISCHE LERN-STRATEGIE FÜR DIESES FACH ===
        {subject_strategy}
        
        === GLOBALE PRÄFERENZEN DES STUDENTEN ===
        {global_pref}
        
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

        ## 3. Kompakte Zusammenfassung des Stoffs (mit Code, Tabellen & Formeln)
        (Wende hier deine spezifische Lern-Strategie an! Gehe tief in die Details.)

        ## 4. Wichtige Dozenten-Hinweise & MEP-Prüfungsrelevanz
        (Was hat der Dozent im Transkript besonders betont? Welche Fallen oder MEP-Schwerpunkte wurden erwähnt?)

        ## 5. Vorbereiteter Fragenkatalog & Prüfungssimulation (MIT MUSTERLÖSUNGEN)
        (Nimm dem Studenten das Fragen-Überlegen ab! Formuliere mindestens 5-7 anspruchsvolle, realistische Prüfungsfragen, die in der HSLU-Modulendprüfung (MEP) vorkommen könnten, und liefere die perfekte Musterantwort direkt mit:)
        - **Frage 1 (Theorie/Verständnis):** ...
          *Musterlösung:* ...
        - **Frage 2 (Praxis/Code/Modellierung/Mathe):** ...
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
        {transcript_text[:15000]}

        Modulinhalte / Folien:
        {pdf_text_content[:8000]}
        """
        
        import time
        retries = 3
        for attempt in range(retries):
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                print(f"Fehler bei Dossier-Generierung (Versuch {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(15)
                else:
                    return f"# Dossier konnte nicht erstellt werden.\nFehler: {e}"
