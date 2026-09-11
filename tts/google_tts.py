import os
import io
import shutil
import urllib.parse
import subprocess
import logging
import requests
import config

logger = logging.getLogger(__name__)


class GoogleTTSException(Exception):
    """Custom exception raised when Google TTS synthesis or network request fails."""
    pass


class GoogleTTS:
    """
    Tier 2 Backup Synthesizer using Google Translate TTS API with British English accent (tld='co.uk').
    Converts MP3 audio buffers to 24000Hz 16-bit PCM bytes for direct feeding into AudioStreamPlayer.
    """

    def __init__(self, lang: str = None, tld: str = None):
        self.lang = lang or getattr(config, "GOOGLE_TTS_LANG", "en")
        self.tld = tld or getattr(config, "GOOGLE_TTS_TLD", "co.uk")
        self.sample_rate = 24000

    def synthesize_to_pcm(self, text: str) -> bytes:
        """
        Synthesizes text into 24000Hz 16-bit PCM bytes with a 3-second network timeout.

        Args:
            text (str): Speech text to synthesize.

        Returns:
            bytes: Raw PCM 16-bit audio bytes.

        Raises:
            GoogleTTSException: If network connection times out or audio conversion fails.
        """
        if not text or not text.strip():
            return b""

        clean_text = text.strip()
        encoded_query = urllib.parse.quote(clean_text)
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_query}&tl={self.lang}&client=tw-ob&tld={self.tld}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        try:
            # 3-second network timeout
            response = requests.get(url, headers=headers, timeout=(3.0, 10.0))
            if response.status_code != 200:
                raise GoogleTTSException(f"Google TTS API returned HTTP status {response.status_code}")

            mp3_bytes = response.content
            if not mp3_bytes:
                raise GoogleTTSException("Google TTS returned empty audio payload.")

            # Convert MP3 audio buffer to 24000Hz 16-bit PCM via FFmpeg
            ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
            proc = subprocess.Popen(
                [
                    ffmpeg_path,
                    "-i",
                    "pipe:0",
                    "-f",
                    "s16le",
                    "-ac",
                    "1",
                    "-ar",
                    str(self.sample_rate),
                    "pipe:1",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            pcm_bytes, stderr = proc.communicate(input=mp3_bytes)

            if proc.returncode != 0:
                raise GoogleTTSException(f"FFmpeg conversion failed: {stderr.decode('utf-8', errors='ignore')[:150]}")

            return pcm_bytes

        except requests.exceptions.Timeout as e:
            raise GoogleTTSException(f"Google TTS connection timed out (3s threshold): {e}")
        except requests.exceptions.RequestException as e:
            raise GoogleTTSException(f"Google TTS network request failed: {e}")
        except Exception as e:
            if isinstance(e, GoogleTTSException):
                raise
            raise GoogleTTSException(f"Unexpected Google TTS error: {e}")


if __name__ == "__main__":
    tts = GoogleTTS()
    print("[GoogleTTS] Synthesizer initialized successfully with British accent (tld='co.uk').")
