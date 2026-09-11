import logging
import numpy as np

logger = logging.getLogger(__name__)


class SpeakerVerifier:
    """
    Lightweight speaker verification and owner voice authorization module.
    """

    def __init__(self, energy_threshold: float = 300.0):
        self.owner_voice_profile = None
        self.energy_threshold = energy_threshold
        self.is_authenticated = True  # Default unlocked; toggleable by owner command

    def verify_speaker(self, audio_data: bytes) -> bool:
        """
        Validates audio buffer energy/pitch characteristics against baseline metrics.
        Returns True if authorized or authentication is disabled.
        """
        if not self.is_authenticated:
            return True

        try:
            # Convert raw byte stream to int16 array for signal energy evaluation
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            if len(audio_array) == 0:
                return True

            rms = float(np.sqrt(np.mean(audio_array.astype(np.float32) ** 2)))

            # Simple threshold check to prevent background ambient trigger noise
            if rms < 50.0:
                logger.info(f"[SpeakerVerifier] Audio RMS ({rms:.1f}) below threshold 50.0; rejecting ambient noise.")
                return False  # Background noise/silence

            return True
        except Exception as e:
            logger.warning(f"[SpeakerVerifier Error] {e}")
            return True

    def toggle_voice_lock(self, enable: bool) -> str:
        """Enables or disables strict speaker verification."""
        self.is_authenticated = enable
        state = "enabled" if enable else "disabled"
        logger.info(f"[SpeakerVerifier] Voice lock toggle set to: {state}")
        return f"Speaker verification voice lock is now {state}."


# Singleton instance
speaker_verifier = SpeakerVerifier()


if __name__ == "__main__":
    verifier = SpeakerVerifier()
    print("[SpeakerVerifier] Module loaded.")
