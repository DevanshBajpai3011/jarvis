import os
import time
import logging
import numpy as np
from typing import Optional, Callable
import config
from tts.speech_engine import speech_engine, SpeechEngine

logger = logging.getLogger(__name__)


class AudioListener:
    """
    Audio & Microphone Listener supporting continuous mic monitoring for active TTS barge-in interruption
    and follow-up timer re-binding upon TTS completion.
    """

    def __init__(self, wake_threshold: float = 300.0, engine: Optional[SpeechEngine] = None):
        self.wake_threshold = wake_threshold
        self.speech_engine = engine or speech_engine
        self.is_monitoring = False

    def monitor_mic_rms(self, raw_audio_data: np.ndarray, rms_callback: Optional[Callable[[float], None]] = None) -> float:
        """
        Calculates mic input RMS energy and performs continuous monitoring during active TTS output.
        If speech_engine.is_speaking is True and microphone input RMS exceeds the wake threshold
        (user starts speaking over J.A.R.V.I.S.), calls speech_engine.stop() to trigger immediate barge-in interruption.

        Args:
            raw_audio_data (np.ndarray): Audio frame array from mic stream.
            rms_callback (Callable, optional): Callback emitting normalized RMS audio energy.

        Returns:
            float: Computed RMS energy.
        """
        if raw_audio_data is None or len(raw_audio_data) == 0:
            return 0.0

        rms = float(np.sqrt(np.mean(raw_audio_data.astype(np.float32) ** 2)))

        if rms_callback:
            try:
                norm_rms = min(1.0, rms / 1200.0)
                rms_callback(norm_rms)
            except Exception:
                pass

        # Continuous mic monitoring during speech for active barge-in audio interruption
        if self.speech_engine.is_speaking and rms >= self.wake_threshold:
            logger.info(f"[Barge-In] User voice activity detected during speech output (RMS {rms:.1f} >= {self.wake_threshold}). Triggering speech interruption.")
            print(f"\n[Barge-In Interruption] User speaking over J.A.R.V.I.S. (RMS: {rms:.1f}). Cutting speech output...", flush=True)
            self.speech_engine.stop()

        return rms

    def create_followup_callback(
        self,
        followup_trigger_fn: Callable[[float], None],
        timeout_seconds: float = 8.0,
    ) -> Callable[[], None]:
        """
        Binds the 8-second post-response silence listener strictly to the on_complete_callback
        passed into speech_engine.speak().
        Ensures the silence countdown does NOT start while TTS is still active.

        Args:
            followup_trigger_fn (Callable): Callback function that initiates the follow-up mic listener window.
            timeout_seconds (float): Silence listener timeout duration (default 8s).

        Returns:
            Callable[[], None]: Wrapped on_complete_callback to pass into speech_engine.speak().
        """
        def on_tts_complete():
            logger.info(f"[Follow-Up Binding] Speech output finished. Starting {timeout_seconds}s post-response silence listener...")
            if followup_trigger_fn:
                try:
                    followup_trigger_fn(timeout_seconds)
                except Exception as e:
                    logger.error(f"[Follow-Up Binding Error] {e}")

        return on_tts_complete


# Singleton instance
audio_listener = AudioListener()


if __name__ == "__main__":
    listener = AudioListener()
    print("[AudioListener] Initialized successfully.")
