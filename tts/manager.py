import re
import logging
import config
from tts.player import AudioStreamPlayer
from tts.piper_tts import PiperTTS
from tts.fish_tts import FishAudioTTS, FishAudioException
from tts.google_tts import GoogleTTS, GoogleTTSException

logger = logging.getLogger(__name__)


def clean_text_for_speech(text: str) -> str:
    """
    Cleans raw markdown symbols, code syntax, URLs, and formatting markers
    so TTS engines read clean natural language.
    """
    if not text:
        return ""

    # Remove code blocks and inline code
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`[^`]*`", "", cleaned)

    # Remove raw URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)

    # Remove markdown header symbols (#, ##, etc.)
    cleaned = re.sub(r"#+\s*", "", cleaned)

    # Remove bold/italic markers (*, _, **)
    cleaned = re.sub(r"[\*_]{1,3}", "", cleaned)

    # Remove list bullet markers
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.MULTILINE)

    # Normalize multiple whitespace lines
    cleaned = re.sub(r"\n\s*\n", "\n", cleaned)
    return cleaned.strip()


class TTSManager:
    """
    Unified 3-Tier Cascading TTS Manager supporting:
    - Tier 1: Fish Audio S2.1 Pro (Primary Neural API)
    - Tier 2: Google TTS Backup (British accent co.uk via Google Translate API)
    - Tier 3: Local Piper TTS (100% Offline Fallback)
    """

    def __init__(self):
        self.player = AudioStreamPlayer(default_samplerate=22050)
        self.fish_tts = FishAudioTTS()
        self.google_tts = GoogleTTS()
        self.piper_tts = PiperTTS()

    def speak(self, text: str) -> None:
        """
        Synthesizes and plays back speech text using a 3-tier cascading architecture.

        Args:
            text (str): Speech text to synthesize.
        """
        if not text or not text.strip():
            return

        clean_text = clean_text_for_speech(text)
        if not clean_text:
            return

        engine = getattr(config, "TTS_ENGINE", "fish").strip().lower()
        use_3tier = getattr(config, "ENABLE_3TIER_TTS", True)

        if engine == "fish" and use_3tier:
            # ----------------------------------------------------
            # TIER 1: Fish Audio S2.1 Pro
            # ----------------------------------------------------
            try:
                print(f"[TTSManager] Tier 1: Synthesizing speech via Fish Audio S2.1 Pro...", flush=True)
                fish_rate = getattr(config, "FISH_AUDIO_SAMPLE_RATE", 24000)

                def fish_chunk_generator():
                    for pcm_chunk in self.fish_tts.stream_audio_chunks(clean_text):
                        yield (pcm_chunk, fish_rate)

                self.player.play_chunks(fish_chunk_generator(), prebuffer_count=2)
                return
            except Exception as tier1_err:
                print(
                    f"[TTS Warning] Tier 1 (Fish Audio) failed: {tier1_err}. Falling back to Tier 2 (Google TTS)...",
                    flush=True,
                )

            # ----------------------------------------------------
            # TIER 2: Google TTS Backup (British Accent co.uk)
            # ----------------------------------------------------
            try:
                print(f"[TTSManager] Tier 2: Synthesizing speech via Google TTS (British accent)...", flush=True)
                pcm_bytes = self.google_tts.synthesize_to_pcm(clean_text)
                if pcm_bytes:
                    g_rate = getattr(self.google_tts, "sample_rate", 24000)
                    self.player.play_chunks([(pcm_bytes, g_rate)], prebuffer_count=1)
                    return
            except Exception as tier2_err:
                print(
                    f"[TTS Warning] Tier 2 (Google TTS) failed: {tier2_err}. Falling back to Tier 3 (Piper Local TTS)...",
                    flush=True,
                )

            # ----------------------------------------------------
            # TIER 3: Local Piper TTS (100% Offline Fallback)
            # ----------------------------------------------------
            print(f"[TTSManager] Tier 3: Synthesizing speech via local Piper TTS engine...", flush=True)
            self.piper_tts.speak(clean_text)

        elif engine == "google":
            try:
                print(f"[TTSManager] Synthesizing speech via Google TTS...", flush=True)
                pcm_bytes = self.google_tts.synthesize_to_pcm(clean_text)
                if pcm_bytes:
                    g_rate = getattr(self.google_tts, "sample_rate", 24000)
                    self.player.play_chunks([(pcm_bytes, g_rate)], prebuffer_count=1)
                    return
            except Exception as err:
                print(f"[TTS Warning] Google TTS failed: {err}. Falling back to local Piper TTS...", flush=True)
                self.piper_tts.speak(clean_text)
        else:
            # Engine is "piper"
            self.piper_tts.speak(clean_text)

    def speak_chunked(self, text: str) -> None:
        """Alias for speak() method."""
        self.speak(text)


_global_tts_manager = None


def get_tts_manager() -> TTSManager:
    """Returns singleton instance of TTSManager."""
    global _global_tts_manager
    if _global_tts_manager is None:
        _global_tts_manager = TTSManager()
    return _global_tts_manager


if __name__ == "__main__":
    manager = get_tts_manager()
    print("[TTSManager] 3-Tier Cascading TTS Manager initialized successfully.")
