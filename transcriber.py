import os
import subprocess
import google.generativeai as genai
import time

class Transcriber:
    def __init__(self):
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    def extract_audio(self, video_path):
        """Extracts audio from an mp4 file using ffmpeg to reduce upload size."""
        audio_path = video_path.rsplit('.', 1)[0] + '.mp3'
        if not os.path.exists(audio_path):
            print(f"Extracting audio to {audio_path}")
            cmd = ['ffmpeg', '-i', video_path, '-q:a', '0', '-map', 'a', audio_path, '-y']
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"Error extracting audio: {e}")
                return None
        return audio_path

    def transcribe(self, audio_path):
        """Transcribes audio using Gemini 1.5 Pro via File API."""
        print(f"Uploading {audio_path} to Gemini File API...")
        try:
            # Upload the file to Gemini
            audio_file = genai.upload_file(path=audio_path)
            
            # Wait for file processing if needed
            while audio_file.state.name == "PROCESSING":
                print("Waiting for audio processing...")
                time.sleep(2)
                audio_file = genai.get_file(audio_file.name)
            
            print("Audio uploaded. Generating transcription...")
            prompt = "Bitte transkribiere diese Vorlesungsaufzeichnung vollständig und wortgetreu auf Deutsch."
            
            response = self.model.generate_content([prompt, audio_file])
            transcript_text = response.text
            
            # Cleanup the file from Google's servers
            genai.delete_file(audio_file.name)
            
            return transcript_text
        except Exception as e:
            print(f"Transcription error with Gemini: {e}")
            return "Fehler bei der Transkription."
