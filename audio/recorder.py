import os
import wave
import sounddevice as sd
import numpy as np


class AudioRecorder:
    """
    Microphone audio recorder using sounddevice, numpy, and wave.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels

    def record_until_keypress(self, output_filename: str = "temp_input.wav") -> str:
        """
        Starts non-blocking audio stream recording from default microphone,
        waits for user Enter keypress, and saves captured audio as a WAV file.

        Args:
            output_filename (str): Target filename to save WAV recording.

        Returns:
            str: Path to saved WAV file.
        """
        audio_chunks = []

        def callback(indata, frames, time_info, status):
            if status:
                print(f"Audio stream warning: {status}", flush=True)
            audio_chunks.append(indata.copy())

        print("\n[AudioRecorder] Recording... Press Enter to stop.", flush=True)

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                callback=callback,
            ):
                input()
        except sd.PortAudioError as e:
            error_msg = f"No microphone detected or audio input device error: {e}"
            print(f"[AudioRecorder Error] {error_msg}")
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to record audio: {e}"
            print(f"[AudioRecorder Error] {error_msg}")
            raise RuntimeError(error_msg) from e

        if not audio_chunks:
            error_msg = "No audio data was recorded."
            print(f"[AudioRecorder Error] {error_msg}")
            raise RuntimeError(error_msg)

        recorded_audio = np.concatenate(audio_chunks, axis=0)

        try:
            with wave.open(output_filename, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit PCM = 2 bytes per sample
                wf.setframerate(self.sample_rate)
                wf.writeframes(recorded_audio.tobytes())
        except Exception as e:
            error_msg = f"Failed writing audio WAV file: {e}"
            print(f"[AudioRecorder Error] {error_msg}")
            raise RuntimeError(error_msg) from e

        abs_path = os.path.abspath(output_filename)
        print(f"[AudioRecorder] Saved recording to: {abs_path}", flush=True)
        return abs_path


if __name__ == "__main__":
    recorder = AudioRecorder()
    try:
        saved_file = recorder.record_until_keypress("test_recording.wav")
        print(f"Success! Recorded file saved at: {saved_file}")
    except RuntimeError as e:
        print(f"Recording test failed: {e}")
