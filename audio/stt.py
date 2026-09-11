import os
import importlib.util
import ctranslate2
from faster_whisper import WhisperModel

import config


def _register_cublas_dll_directory() -> None:
    """
    Locates the nvidia-cublas-cu12 pip package's bin folder (wherever it's actually
    installed) and registers it both via os.add_dll_directory() and by prepending it
    to os.environ["PATH"], so ctranslate2 can find cublas64_12.dll at inference time.
    Both mechanisms are needed: ctranslate2's native CUDA loader only consults PATH
    and does not honor the newer Windows AddDllDirectory API on its own (confirmed by
    testing add_dll_directory() alone against a real recorded transcription, which
    still failed with "Library cublas64_12.dll is not found or cannot be loaded"
    until PATH was also set).
    """
    if os.name != "nt":
        return
    try:
        cublas_spec = importlib.util.find_spec("nvidia.cublas")
        if not cublas_spec or not cublas_spec.submodule_search_locations:
            return
        for location in cublas_spec.submodule_search_locations:
            bin_dir = os.path.join(location, "bin")
            if os.path.isdir(bin_dir):
                os.add_dll_directory(bin_dir)
                if bin_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception as e:
        print(f"[STT Engine] Warning: could not register cuBLAS DLL directory: {e}")


class SpeechToTextEngine:
    def __init__(self, model_size: str = "large-v3-turbo"):
        """
        Initializes Faster-Whisper using CTranslate2 backend.
        Device/compute type come from config.WHISPER_DEVICE / config.WHISPER_COMPUTE_TYPE.
        "auto" (the default) selects CUDA (float16) if ctranslate2 detects a CUDA device,
        otherwise CPU (int8). An explicit "cuda"/"cpu" or "float16"/"int8" value overrides auto-detection.
        """
        device_setting = getattr(config, "WHISPER_DEVICE", "auto")
        compute_setting = getattr(config, "WHISPER_COMPUTE_TYPE", "auto")

        if device_setting == "auto":
            self.device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        else:
            self.device = device_setting

        if compute_setting == "auto":
            self.compute_type = "float16" if self.device == "cuda" else "int8"
        else:
            self.compute_type = compute_setting

        _register_cublas_dll_directory()

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
