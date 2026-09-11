import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
import numpy as np
import sounddevice as sd
import config
from tts.player import AudioStreamPlayer


def split_sentences_smoothly(text: str) -> list[str]:
    """
    Splits text into sentences on major sentence boundaries (. !, ?, \n)
    while preserving decimal points, timestamps (e.g. 5:30 p.m.), abbreviations (e.g. U.S., Mr., Dr.),
    and version numbers (e.g. v1.0) to prevent mid-sentence stutters.
    """
    text = text.strip()
    if not text:
        return []

    # Protect common abbreviations and decimal structures
    protected = text
    protected = re.sub(r'\b(p\.m|a\.m|u\.s|v\d+\.\d+)\.', r'\1_DOT_', protected, flags=re.IGNORECASE)
    protected = re.sub(r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|inc|ltd)\.', r'\1_DOT_', protected, flags=re.IGNORECASE)
    protected = re.sub(r'(\d+)\.(\d+)', r'\1_DOT_\2', protected)

    # Split on major sentence boundaries (. ! ? \n)
    parts = re.split(r'(?<=[.!?\n])\s+', protected)

    # Restore protected dots
    sentences = [p.replace('_DOT_', '.').strip() for p in parts if p.replace('_DOT_', '.').strip()]
    return sentences


class PiperTTS:
    """
    Text-to-Speech engine wrapper using local Piper TTS, continuous audio stream player,
    and pre-buffering to eliminate hardware reset gaps between sentence chunks.
    """

    def __init__(self, voice_model: str = None):
        """
        Initializes PiperTTS with voice model configuration, AudioStreamPlayer,
        and ensuring model files exist locally.
        """
        self.voices_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "voices"))
        os.makedirs(self.voices_dir, exist_ok=True)

        model_setting = voice_model or getattr(config, "PIPER_VOICE_MODEL", "en_GB-alan-medium")
        self.model_path = self._resolve_and_ensure_model(model_setting)
        self.player = AudioStreamPlayer(default_samplerate=22050)
        self.streaming_enabled = getattr(config, "STREAMING_TTS", True)

    def _get_download_urls(self, model_name: str) -> tuple[str, str]:
        parts = model_name.split("-")
        if len(parts) >= 3:
            locale = parts[0]
            voice = parts[1]
            quality = parts[2]
            lang = locale.split("_")[0]
            base_url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{locale}/{voice}/{quality}/{model_name}"
        else:
            base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium"

        return f"{base_url}.onnx", f"{base_url}.onnx.json"

    def _download_file(self, url: str, target_path: str) -> None:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req) as response, open(target_path, "wb") as out_file:
            shutil.copyfileobj(response, out_file)

    def _resolve_and_ensure_model(self, voice_model: str) -> str:
        if os.path.isabs(voice_model) and os.path.exists(voice_model):
            return voice_model

        model_name = voice_model[:-5] if voice_model.endswith(".onnx") else voice_model

        onnx_file_name = f"{model_name}.onnx"
        json_file_name = f"{model_name}.onnx.json"

        onnx_local_path = os.path.abspath(os.path.join(self.voices_dir, onnx_file_name))
        json_local_path = os.path.abspath(os.path.join(self.voices_dir, json_file_name))

        onnx_url, json_url = self._get_download_urls(model_name)

        if not os.path.exists(onnx_local_path):
            print(
                f"[PiperTTS] Voice model '{onnx_file_name}' not found locally. Downloading from HuggingFace...",
                flush=True,
            )
            self._download_file(onnx_url, onnx_local_path)
            print(f"[PiperTTS] Downloaded '{onnx_file_name}' successfully.", flush=True)

        if not os.path.exists(json_local_path):
            print(
                f"[PiperTTS] Voice config '{json_file_name}' not found locally. Downloading from HuggingFace...",
                flush=True,
            )
            self._download_file(json_url, json_local_path)
            print(f"[PiperTTS] Downloaded '{json_file_name}' successfully.", flush=True)

        return onnx_local_path

    def speak(self, text: str) -> None:
        """
        Synthesizes and plays back speech text.
        If config.STREAMING_TTS is True, uses gapless sentence streaming with pre-buffering.
        If config.STREAMING_TTS is False, synthesizes full response in a single smooth audio pass.

        Args:
            text (str): Speech text to synthesize.
        """
        if not text or not text.strip():
            return

        text = text.strip()

        # Check FALLBACK TOGGLE flag from config
        is_streaming = getattr(config, "STREAMING_TTS", True)
        if not is_streaming:
            print(f"[PiperTTS] STREAMING_TTS=False: Synthesizing full response in single pass...", flush=True)
            self._speak_single_pass(text)
            return

        # Sentence-Level Gapless Streaming TTS
        sentences = split_sentences_smoothly(text)
        if len(sentences) <= 1:
            self._speak_single_pass(text)
            return

        print(f"[PiperTTS] STREAMING_TTS=True: Streaming {len(sentences)} sentence chunks with pre-buffering...", flush=True)

        def audio_chunk_generator():
            for idx, sentence in enumerate(sentences, 1):
                pcm_bytes, samplerate = self._synthesize_sentence_pcm(sentence)
                if pcm_bytes is not None:
                    yield (pcm_bytes, samplerate)

        # Pre-buffer initial 2 sentences before playback starts
        self.player.play_chunks(audio_chunk_generator(), prebuffer_count=2)

    def speak_chunked(self, text: str) -> None:
        """Alias for speak() supporting streaming sentence playback."""
        self.speak(text)

    def _speak_single_pass(self, text: str) -> None:
        """Synthesizes and plays text in a single audio pass."""
        temp_wav_path = os.path.join(
            tempfile.gettempdir(), f"piper_output_{int(time.time() * 1000)}.wav"
        )
        try:
            self._synthesize_to_file(text, temp_wav_path)
            self._play_audio_file(temp_wav_path)
        except Exception as e:
            print(f"[PiperTTS Error] Speech generation failed: {e}")
        finally:
            if os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except OSError:
                    pass

    def _synthesize_sentence_pcm(self, sentence: str) -> tuple[np.ndarray, int]:
        """
        Synthesizes a single sentence string into PCM array and samplerate.
        """
        temp_wav_path = os.path.join(
            tempfile.gettempdir(), f"piper_chunk_{int(time.time() * 1000)}.wav"
        )
        try:
            self._synthesize_to_file(sentence, temp_wav_path)
            with wave.open(temp_wav_path, "rb") as wf:
                samplerate = wf.getframerate()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                raw_frames = wf.readframes(wf.getnframes())

                dtype = np.int16 if sampwidth == 2 else np.int32
                arr = np.frombuffer(raw_frames, dtype=dtype)
                if n_channels > 1:
                    arr = arr.reshape(-1, n_channels)[:, 0]
                return arr, samplerate
        except Exception as e:
            print(f"[PiperTTS Error] Sentence synthesis failed: {e}")
            return None, 22050
        finally:
            if os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except OSError:
                    pass

    def _synthesize_to_file(self, text: str, output_path: str) -> None:
        piper_binary = shutil.which("piper")
        if not piper_binary:
            candidate = os.path.join(os.path.dirname(sys.executable), "piper.exe")
            if os.path.exists(candidate):
                piper_binary = candidate
            else:
                candidate_no_ext = os.path.join(os.path.dirname(sys.executable), "piper")
                piper_binary = candidate_no_ext if os.path.exists(candidate_no_ext) else "piper"

        try:
            process = subprocess.Popen(
                [piper_binary, "-m", self.model_path, "--output_file", output_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(input=text)

            if process.returncode != 0:
                raise RuntimeError(
                    f"Piper process exited with non-zero status ({process.returncode}).\nStderr: {stderr.strip()}"
                )

            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError("Piper completed but output WAV file is empty or missing.")

        except FileNotFoundError as e:
            raise RuntimeError(
                f"Piper TTS binary ('{piper_binary}') was not found in system PATH."
            ) from e

    def _play_audio_file(self, wav_file_path: str) -> None:
        with wave.open(wav_file_path, "rb") as wf:
            samplerate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

            dtype = np.int16 if sampwidth == 2 else np.int32
            audio_array = np.frombuffer(raw_data, dtype=dtype)
            if n_channels > 1:
                audio_array = audio_array.reshape(-1, n_channels)

            sd.play(audio_array, samplerate=samplerate)
            sd.wait()


if __name__ == "__main__":
    tts = PiperTTS()
    print("[PiperTTS] Initialized with continuous AudioStreamPlayer.")
