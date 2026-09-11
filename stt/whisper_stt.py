import os
import shutil
import time
import config
from audio.stt import SpeechToTextEngine, stt_engine


class WhisperSTT:
    """
    Speech-to-Text wrapper delegating to Faster-Whisper SpeechToTextEngine.
    """

    def __init__(self, model_name: str = None):
        """
        Initializes Faster-Whisper SpeechToTextEngine instance.
        """
        self.model_name = model_name or getattr(config, "WHISPER_MODEL", "large-v3-turbo")
        self.engine = stt_engine if self.model_name == "large-v3-turbo" else SpeechToTextEngine(self.model_name)

    def transcribe(self, audio_file_path: str) -> str:
        """
        Transcribes the given audio file using Faster-Whisper SpeechToTextEngine.

        Args:
            audio_file_path (str): Path to the WAV or audio file to transcribe.

        Returns:
            str: Clean transcribed text with leading and trailing whitespace removed, or empty string on error.
        """
        if not os.path.exists(audio_file_path):
            print(f"[WhisperSTT Error] Audio file does not exist: {audio_file_path}", flush=True)
            return ""

        print(f"[WhisperSTT] Processing audio file '{audio_file_path}' via Faster-Whisper...", flush=True)
        start_time = time.time()

        try:
            transcribed_text = self.engine.transcribe(audio_file_path)
            processing_time = time.time() - start_time

            print(
                f"[WhisperSTT] Transcribed in {processing_time:.2f}s -> '{transcribed_text}'",
                flush=True,
            )
            return transcribed_text
        except Exception as e:
            print(f"[WhisperSTT Error] Failed to transcribe audio file '{audio_file_path}': {e}", flush=True)
            return ""



if __name__ == "__main__":
    stt = WhisperSTT()
    print("[WhisperSTT] Model initialized and ready.")
