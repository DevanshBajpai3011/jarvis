import threading
import logging
from typing import Optional, Callable
from tts.manager import get_tts_manager, TTSManager

logger = logging.getLogger(__name__)


class SpeechEngine:
    """
    Speech Engine wrapping TTSManager with active barge-in audio interruption
    and follow-up timing on_complete callbacks.
    """

    def __init__(self, tts_manager: Optional[TTSManager] = None):
        self.tts_manager = tts_manager or get_tts_manager()
        self.is_speaking: bool = False
        self.interrupt_event: threading.Event = threading.Event()
        self._lock = threading.Lock()

    def speak(self, text: str, on_complete_callback: Optional[Callable[[], None]] = None) -> bool:
        """
        Synthesizes and plays speech text with interrupt event monitoring.

        Args:
            text (str): Speech text to synthesize and speak.
            on_complete_callback (Callable, optional): Deprecated -- kept only for backward
                compatibility with any external caller still passing it (none in this
                codebase as of the Step 4 turn-completion redesign; see CHANGELOG.md).
                Orchestrator.process_input() no longer relies on this -- it tracks
                completion itself via this method's return value instead, since a per-call
                injected callback can't express "wait until the true last call in a
                variable-length sequence finishes."

        Returns:
            bool: True if speech completed cleanly (not interrupted by barge-in), False
                if it was interrupted or text was empty/whitespace.
        """
        if not text or not text.strip():
            return False

        with self._lock:
            self.interrupt_event.clear()
            self.is_speaking = True

        logger.info(f"[SpeechEngine] Speaking text (length={len(text)})...")

        try:
            if hasattr(self.tts_manager, "player") and hasattr(self.tts_manager.player, "interrupt_event"):
                self.tts_manager.player.interrupt_event = self.interrupt_event

            self.tts_manager.speak(text)

        except Exception as e:
            logger.error(f"[SpeechEngine Error] {e}")
        finally:
            was_interrupted = self.interrupt_event.is_set()

            with self._lock:
                self.is_speaking = False
                self.interrupt_event.clear()

            if was_interrupted:
                logger.info("[SpeechEngine] Speech output was interrupted by barge-in event.")
            else:
                logger.info("[SpeechEngine] Speech completed cleanly.")
                if on_complete_callback:
                    try:
                        logger.info("[SpeechEngine] Executing on_complete_callback...")
                        on_complete_callback()
                    except Exception as cb_err:
                        logger.error(f"[SpeechEngine Callback Error] {cb_err}")

        return not was_interrupted

    def stop(self) -> None:
        """
        Triggers immediate barge-in interruption flag to cut active speech.
        """
        logger.info("[SpeechEngine] Stop requested. Setting interrupt_event flag.")
        with self._lock:
            self.interrupt_event.set()
            self.is_speaking = False

        if hasattr(self.tts_manager, "player") and hasattr(self.tts_manager.player, "stop"):
            try:
                self.tts_manager.player.stop()
            except Exception as e:
                logger.warning(f"[SpeechEngine] Player stop error: {e}")


# Singleton instance
speech_engine = SpeechEngine()


if __name__ == "__main__":
    engine = SpeechEngine()
    print("[SpeechEngine] Initialized successfully.")
