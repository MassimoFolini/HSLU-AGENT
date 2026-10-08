import os
import subprocess
import google.generativeai as genai
import time
import re

class Transcriber:
    def __init__(self):
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        # Flash ist guenstig und schnell fuer Audio; Modell per GEMINI_TRANSCRIBE_MODEL aenderbar
        self.model = genai.GenerativeModel(os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-3.5-flash"))

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

    CHUNK_SECONDS = 1200  # 20-Minuten-Segmente: bleibt unter dem Ausgabelimit und macht Neustarts billig

    def _split_audio(self, audio_path, work_dir):
        os.makedirs(work_dir, exist_ok=True)
        pattern = os.path.join(work_dir, "part_%03d.mp3")
        subprocess.run(["ffmpeg", "-y", "-i", audio_path, "-f", "segment", "-segment_time", str(self.CHUNK_SECONDS),
                        "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k", pattern], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return sorted(os.path.join(work_dir, f) for f in os.listdir(work_dir) if f.startswith("part_") and f.endswith(".mp3"))

    def _transcribe_chunk(self, path, retries=4):
        prompt = ("Transkribiere diese Vorlesungsaufzeichnung vollstaendig und wortgetreu in der gesprochenen Sprache "
                  "(meist Deutsch, Fachbegriffe auf Englisch bleiben). Gib nur den Text aus, in Absaetzen, "
                  "ohne Kommentare, ohne Zusammenfassung, ohne Erfindungen. Unverstaendliches als [unverstaendlich] markieren.")
        last = None
        with open(path, "rb") as f:
            audio = {"mime_type": "audio/mp3", "data": f.read()}
        for attempt in range(1, retries + 1):
            try:
                response = self.model.generate_content([prompt, audio], request_options={"timeout": 900})
                return response.text
            except Exception as e:
                last = str(e).split("key=")[0][:300]  # nie den API-Key ins Log schreiben
                print(f"   [Transkript] Versuch {attempt}/{retries} fehlgeschlagen: {last}", flush=True)
                time.sleep(20 * attempt)
        raise RuntimeError(f"Segment nicht transkribierbar: {last}")

    def transcribe(self, audio_path):
        """Transkribiert eine MP3 in Segmenten per Gemini. Ergebnis wird als .txt neben der MP3 gespeichert.
        Fertige Segmente werden zwischengespeichert, ein Abbruch verliert also nichts."""
        txt_path = audio_path.rsplit('.', 1)[0] + '.txt'
        if os.path.exists(txt_path) and os.path.getsize(txt_path) > 0:
            print(f"Lade lokales Transkript: {txt_path}")
            with open(txt_path, 'r', encoding='utf-8') as f:
                return f.read()

        work_dir = audio_path.rsplit('.', 1)[0] + '_chunks'
        parts = self._split_audio(audio_path, work_dir)
        texts = []
        for i, part in enumerate(parts):
            cache = part + ".txt"
            if os.path.exists(cache) and os.path.getsize(cache) > 0:
                with open(cache, 'r', encoding='utf-8') as f:
                    texts.append((i, f.read()))
                continue
            print(f"   [Transkript] Segment {i + 1}/{len(parts)} ...", flush=True)
            text = self._transcribe_chunk(part)
            with open(cache, 'w', encoding='utf-8') as f:
                f.write(text)
            texts.append((i, text))

        out = []
        for i, text in texts:
            start = i * self.CHUNK_SECONDS
            out.append(f"[{start // 3600:02d}:{start % 3600 // 60:02d}:{start % 60:02d}]" + chr(10) + text.strip())
        transcript = (chr(10) * 2).join(out)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(transcript)
        for f in os.listdir(work_dir):
            os.remove(os.path.join(work_dir, f))
        os.rmdir(work_dir)
        return transcript
