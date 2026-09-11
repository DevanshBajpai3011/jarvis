import numpy as np
import sounddevice as sd


def play_wake_cue(frequency: float = 800.0, duration_ms: float = 150.0, samplerate: int = 44100) -> None:
    """
    Generates and plays a soft 800 Hz sine wave beep tone with fade envelope.
    Handles device errors gracefully to prevent crashing if the audio device is busy.

    Args:
        frequency (float): Tone frequency in Hz (default 800.0 Hz).
        duration_ms (float): Duration in milliseconds (default 150.0 ms).
        samplerate (int): Audio sample rate in Hz (default 44100 Hz).
    """
    try:
        duration = duration_ms / 1000.0
        n_samples = int(samplerate * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)

        # Generate sine wave tone
        sine_wave = np.sin(2.0 * np.pi * frequency * t)

        # Apply soft fade-in and fade-out envelope (10 ms duration or 10% of samples)
        fade_len = min(int(samplerate * 0.01), n_samples // 2)
        if fade_len > 0:
            envelope = np.ones(n_samples, dtype=np.float32)
            envelope[:fade_len] = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
            envelope[-fade_len:] = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
            sine_wave = sine_wave * envelope

        # Scale volume to comfortable level (0.3)
        audio_data = (sine_wave * 0.3).astype(np.float32)

        sd.play(audio_data, samplerate=samplerate)
        sd.wait()
    except Exception as e:
        print(f"[AudioFeedback Warning] Could not play wake cue audio: {e}")


if __name__ == "__main__":
    print("[AudioFeedback] Playing test wake cue...")
    play_wake_cue()
    print("[AudioFeedback] Cue finished.")
