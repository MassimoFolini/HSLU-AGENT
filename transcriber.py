import os
import subprocess
import google.generativeai as genai
import time
import re

class Transcriber:
    def __init__(self):
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        # We use flash because it is almost free and fast for audio
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def download_audio_from_url(self, url, cookies_file, output_dir):
        """Downloads audio directly from a URL (Panopto, Zoom) using yt-dlp."""
        print(f"Downloading stream from {url}...")
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', url.split('/')[-1])[:30]
        if not safe_name:
            safe_name = "audio_stream"
        
        output_template = os.path.join(output_dir, f"{safe_name}.%(ext)s")
        mp3_path = os.path.join(output_dir, f"{safe_name}.mp3")
        
        if os.path.exists(mp3_path):
            print("Audio already downloaded!")
            return mp3_path
            
        cmd = [
            'yt-dlp',
            '--cookies', cookies_file,
            '-x', '--audio-format', 'mp3',
            '--audio-quality', '5', # lower quality is fine for speech, saves bandwidth
            '-o', output_template,
            url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(mp3_path):
                print(f"Successfully downloaded to {mp3_path}")
                return mp3_path
            else:
                print(f"yt-dlp error or unsupported URL: {result.stderr}")
                return None
        except Exception as e:
            print(f"Failed to execute yt-dlp: {e}")
            return None

    def extract_audio(self, video_path):
        """Extracts audio from a local mp4 file using ffmpeg."""
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
        """Transcribes audio using Gemini 1.5 Flash via File API and caches locally."""
        txt_path = audio_path.rsplit('.', 1)[0] + '.txt'
        if os.path.exists(txt_path):
            print(f"Lade lokales Transkript: {txt_path}")
            with open(txt_path, 'r', encoding='utf-8') as f:
                return f.read()

        print(f"Uploading {audio_path} to Gemini File API...")
        try:
            audio_file = genai.upload_file(path=audio_path)
            
            while audio_file.state.name == "PROCESSING":
                print("Waiting for audio processing...")
                time.sleep(2)
                audio_file = genai.get_file(audio_file.name)
            
            print("Audio uploaded. Generating transcription...")
            prompt = "Bitte transkribiere diese Vorlesungsaufzeichnung vollständig und wortgetreu auf Deutsch."
            
            response = self.model.generate_content([prompt, audio_file])
            transcript_text = response.text
            
            genai.delete_file(audio_file.name)
            
            # Cache locally
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(transcript_text)
                
            return transcript_text
        except Exception as e:
            print(f"Transcription error with Gemini: {e}")
            return "Fehler bei der Transkription."
