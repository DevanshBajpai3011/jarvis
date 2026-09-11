import os
import wave
import math
import numpy as np
from scipy.signal import resample_poly

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    import pyaudio

import openwakeword
from openwakeword.model import Model
from typing import Optional, Callable
import config
from audio.feedback import play_wake_cue
from audio.listener import audio_listener


TARGET_RATE = 16000
TARGET_CHUNK_SIZE = 1280

class WakeWordListener:
    """
    Background wake word listener using openWakeWord, PyAudio/PyAudioWPatch,
    and an auto-sensing sample-rate adaptive pipeline.
    """

    def __init__(self, model_name: str = None, threshold: float = None, on_wake_callback: Optional[Callable[[], None]] = None):
        """
        Initializes openWakeWord model and detection settings.
        """
        self.on_wake_callback = on_wake_callback
        self.is_listening = False
        self.threshold = threshold if threshold is not None else getattr(config, "WAKEWORD_THRESHOLD", 0.50)
        self.model_name = model_name or getattr(config, "WAKEWORD_NAME", "hey_jarvis")
        self.gain_scaler = getattr(config, "WAKEWORD_GAIN_SCALER", 2.0)
        self.audio_buffer = np.array([], dtype=np.int16)
        
        # Ensure openWakeWord models are available locally
        try:
            openwakeword.utils.download_models()
        except Exception as e:
            print(f"[WakeWordListener Warning] Model availability check: {e}")

        self.oww_model = Model(wakeword_models=[self.model_name], inference_framework="onnx")
        print(f"[WakeWordListener] Loaded standard model '{self.model_name}' (threshold: {self.threshold}).")

    def trigger_wake(self):
        """Executes the wake callback without needing to import main.py."""
        if self.on_wake_callback:
            try:
                self.on_wake_callback()
            except Exception as e:
                print(f"[WakeWordListener Callback Error] {e}")

    def listen_for_wakeword(
        self,
        rms_callback: Optional[Callable[[float], None]] = None,
    ) -> bool:
        """
        Opens an auto-sensing continuous audio stream from pyaudio, resamples to 16000 Hz if needed,
        reads audio into a FIFO buffer, feeds into openWakeWord model,
        and triggers play_wake_cue() and returns True when wake word score >= threshold.
        """
        self.is_listening = True
        self.audio_buffer = np.array([], dtype=np.int16)

        pa = pyaudio.PyAudio()
        stream = None

        while self.is_listening:
            try:
                dev_info = pa.get_default_input_device_info()
                native_rate = int(dev_info.get("defaultSampleRate", 16000))
                native_channels = max(1, min(int(dev_info.get("maxInputChannels", 1)), 2))
                native_chunk_size = int(native_rate * 0.08)

                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=native_channels,
                    rate=native_rate,
                    input=True,
                    frames_per_buffer=native_chunk_size
                )
                
                print(f"[WakeWordListener] Bound to '{dev_info['name']}' ({native_rate}Hz, {native_channels}ch) -> Resampling to 16kHz")

                frame_count = 0
                while self.is_listening:
                    try:
                        raw_bytes = stream.read(native_chunk_size, exception_on_overflow=False)
                    except IOError as e:
                        print(f"[WakeWordListener Warning] Stream read error: {e}")
                        break

                    data = np.frombuffer(raw_bytes, dtype=np.int16)

                    # Mix down stereo to mono if needed
                    if native_channels > 1:
                        data = data.reshape(-1, native_channels).mean(axis=1).astype(np.int16)

                    # Dynamic Resampling
                    if native_rate != TARGET_RATE:
                        gcd = math.gcd(TARGET_RATE, native_rate)
                        up = TARGET_RATE // gcd
                        down = native_rate // gcd
                        resampled_data = resample_poly(data.astype(np.float32), up, down).astype(np.int16)
                    else:
                        resampled_data = data

                    self.audio_buffer = np.concatenate((self.audio_buffer, resampled_data))

                    # Inference Loop (process in TARGET_CHUNK_SIZE chunks)
                    while len(self.audio_buffer) >= TARGET_CHUNK_SIZE:
                        chunk = self.audio_buffer[:TARGET_CHUNK_SIZE]
                        self.audio_buffer = self.audio_buffer[TARGET_CHUNK_SIZE:]
                        
                        rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
                        frame_count += 1

                        if rms_callback:
                            audio_listener.monitor_mic_rms(chunk, rms_callback=rms_callback)

                        # Software pre-gain scaler to compensate for low-voltage laptop mic arrays
                        chunk = np.clip(chunk.astype(np.float32) * self.gain_scaler, -32768, 32767).astype(np.int16)
                        self.oww_model.predict(chunk)
                        score = self.oww_model.prediction_buffer[self.model_name][-1]

                        if frame_count % 25 == 0:
                            print(f"[Mic Active] Current RMS: {rms:6.1f} | Score: {score:.4f}")

                        if rms > 150:
                            print(f"[Speech] RMS: {rms:6.1f} | '{self.model_name}' score: {score:.4f}")

                        if score >= self.threshold:
                            print(f"\n[>>> WAKEWORD TRIGGERED <<<] Score: {score:.2f}\n")
                            play_wake_cue()
                            self.oww_model.reset()
                            self.trigger_wake()
                            
                            stream.stop_stream()
                            stream.close()
                            pa.terminate()
                            return True

            except KeyboardInterrupt:
                self.is_listening = False
                break
            except Exception as e:
                # Auto-recover PortAudio / buffer errors
                print(f"[WakeWordListener Error] Exception in stream setup/loop: {e}. Reconnecting...")
                import time
                time.sleep(1)
                try:
                    if stream:
                        stream.stop_stream()
                        stream.close()
                except:
                    pass
                continue

        try:
            if stream:
                stream.stop_stream()
                stream.close()
            pa.terminate()
        except:
            pass

        return False

    def record_phrase(
        self,
        duration: float = 10.0,
        output_filename: str = "temp_input.wav",
        sample_rate: int = TARGET_RATE,
        channels: int = 1,
        rms_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """
        Immediately after wake word trigger, records audio for fixed duration (or until silence)
        and saves to output_filename.
        """
        print(f"[WakeWordListener] Recording phrase (max {duration}s)...", flush=True)
        chunk_duration = 0.1
        chunk_samples = int(sample_rate * chunk_duration)
        max_chunks = int(duration / chunk_duration)
        silence_target_chunks = int(1.2 / chunk_duration)

        audio_chunks = []
        speech_started = False
        silence_counter = 0

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                frames_per_buffer=chunk_samples
            )
        except Exception as e:
            print(f"[WakeWordListener Error] PyAudio init error for recording: {e}")
            return ""

        try:
            for _ in range(max_chunks):
                raw_data = stream.read(chunk_samples, exception_on_overflow=False)
                data = np.frombuffer(raw_data, dtype=np.int16)
                audio_chunks.append(data.copy())

                rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
                if rms_callback:
                    try:
                        norm_rms = min(1.0, rms / 1200.0)
                        rms_callback(norm_rms)
                    except Exception:
                        pass

                if rms > 300:
                    speech_started = True
                    silence_counter = 0
                else:
                    if speech_started:
                        silence_counter += 1
                        if silence_counter >= silence_target_chunks:
                            print("[WakeWordListener] End of phrase detected (1.2s silence).", flush=True)
                            break
        except Exception as e:
            print(f"[WakeWordListener Error] Failed to record audio phrase: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        if not audio_chunks:
            raise RuntimeError("No audio recorded during phrase recording.")

        recorded_audio = np.concatenate(audio_chunks, axis=0)
        abs_path = os.path.abspath(output_filename)

        try:
            with wave.open(abs_path, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(recorded_audio.tobytes())
        except Exception as e:
            raise RuntimeError(f"Failed saving phrase audio to WAV file: {e}") from e

        print(f"[WakeWordListener] Saved recorded phrase to: {abs_path}", flush=True)
        return abs_path

    def listen_for_speech_timeout(
        self,
        timeout_seconds: int = 8,
        sample_rate: int = TARGET_RATE,
        rms_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[str]:
        """
        Continuously monitors mic input for voice activity (RMS threshold > noise floor)
        without requiring a wake word.
        """
        print(f"\n[WakeWordListener] Direct follow-up listen window active (max {timeout_seconds}s)...", flush=True)

        chunk_duration = 0.1
        chunk_samples = int(sample_rate * chunk_duration)
        max_wait_chunks = int(timeout_seconds / chunk_duration)

        speech_detected = False
        pa = pyaudio.PyAudio()
        
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                frames_per_buffer=chunk_samples
            )
        except Exception as e:
            print(f"[WakeWordListener Error] Error init PyAudio follow-up stream: {e}")
            return None

        try:
            for _ in range(max_wait_chunks):
                raw_data = stream.read(chunk_samples, exception_on_overflow=False)
                data = np.frombuffer(raw_data, dtype=np.int16)
                rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))

                if rms_callback:
                    try:
                        norm_rms = min(1.0, rms / 1200.0)
                        rms_callback(norm_rms)
                    except Exception:
                        pass

                if rms > 300:
                    speech_detected = True
                    print(f"[WakeWordListener] Speech detected in follow-up window (RMS: {rms:.1f}).", flush=True)
                    break
        except Exception as e:
            print(f"[WakeWordListener Error] Error during follow-up stream: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        if not speech_detected:
            print(f"[WakeWordListener] Follow-up window timed out after {timeout_seconds}s (silence).", flush=True)
            return None

        # Voice activity detected -> Record phrase
        return self.record_phrase(
            duration=10.0,
            output_filename="temp_input.wav",
            sample_rate=sample_rate,
            rms_callback=rms_callback,
        )


if __name__ == "__main__":
    listener = WakeWordListener()
    print("[WakeWordListener] Initialized successfully.")
