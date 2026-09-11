import torch
from faster_whisper import WhisperModel


class SpeechToTextEngine:
    def __init__(self, model_size: str = "large-v3-turbo"):
        """
        Initializes Faster-Whisper using CTranslate2 backend.
        Automatically selects CUDA (float16) if available, otherwise falls back to CPU (int8).
        """
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"

        print(f"[STT Engine] Loading Faster-Whisper ({model_size}) on {self.device} ({self.compute_type})...")
        self.model = WhisperModel(
            model_size,
            device=self.device,
            compute_type=self.compute_type
        )
        print("[STT Engine] Model loaded successfully.")

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribes audio file to text.

        Args:
            audio_path: Path to .wav or audio buffer file.
        """
        try:
            segments, info = self.model.transcribe(
                audio_path,
                beam_size=5,
                language="en",
                vad_filter=True,  # Filters out non-speech/silence audio chunks
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            text_segments = [segment.text for segment in segments]
            full_text = " ".join(text_segments).strip()
            return full_text

        except Exception as e:
            print(f"[STT Engine] Transcription error: {e}")
            return ""


# Singleton instance
stt_engine = SpeechToTextEngine()
