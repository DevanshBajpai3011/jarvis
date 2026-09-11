import os
import requests
import logging
import config
from typing import Generator

logger = logging.getLogger(__name__)


class FishAudioException(Exception):
    """Custom exception raised when Fish Audio TTS API request fails or times out."""
    pass


class FishAudioTTS:
    """
    Fish Audio S2.1 Pro TTS Synthesizer streaming audio chunks from https://api.fish.audio/v1/tts.
    """

    def __init__(self, api_key: str = None, model_id: str = None):
        self.api_key = api_key or getattr(config, "FISH_AUDIO_API_KEY", "")
        self.model_id = model_id or getattr(config, "FISH_AUDIO_MODEL_ID", "s2.1-pro-free")
        self.api_url = "https://api.fish.audio/v1/tts"

    def stream_audio_chunks(self, text: str) -> Generator[bytes, None, None]:
        """
        Sends text synthesis request to Fish Audio API targeting the free s2.1-pro-free model
        and yields audio byte chunks.

        Args:
            text (str): Input text to synthesize.

        Yields:
            bytes: Audio byte chunks.

        Raises:
            FishAudioException: If API key is missing, connection times out, or API returns error.
        """
        if not self.api_key or self.api_key == "your_fish_audio_api_key_here":
            raise FishAudioException("Fish Audio API key is not configured.")

        if not text or not text.strip():
            return

        model_name = getattr(config, "FISH_AUDIO_MODEL_ID", "s2.1-pro-free")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "model": model_name,
        }

        voice_ref_id = getattr(config, "FISH_AUDIO_VOICE_REF_ID", None)
        sample_rate = getattr(config, "FISH_AUDIO_SAMPLE_RATE", 24000)

        payload = {
            "text": text.strip(),
            "format": "pcm",
            "sample_rate": sample_rate,
        }

        if voice_ref_id and isinstance(voice_ref_id, str) and voice_ref_id.strip():
            payload["reference_id"] = voice_ref_id.strip()

        try:
            # 3-second connection timeout
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=(3.0, 15.0),
            )

            if response.status_code != 200:
                err_text = response.text[:250]
                raise FishAudioException(
                    f"Fish Audio API returned status {response.status_code}: {err_text}"
                )

            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk

        except requests.exceptions.Timeout as e:
            raise FishAudioException(f"Fish Audio connection timed out (3s threshold): {e}")
        except requests.exceptions.RequestException as e:
            raise FishAudioException(f"Fish Audio network request failed: {e}")
        except Exception as e:
            raise FishAudioException(f"Unexpected error during Fish Audio synthesis: {e}")


if __name__ == "__main__":
    print("[FishAudioTTS] Synthesizer loaded targeting model header:", getattr(config, "FISH_AUDIO_MODEL_ID", "s2.1-pro-free"))
