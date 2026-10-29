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

        # Handoff slot for a recording stream pre-opened by listen_for_wakeword() before
        # play_wake_cue() plays (BUGS.md Bug #10, fix attempt #2) -- record_phrase() picks
        # this up if present instead of opening its own, eliminating the dead gap where no
        # stream was open at all between the old detection stream closing and a new
        # recording stream opening (previously measured at ~380ms on this machine, easily
        # enough to lose the first spoken word).
        self._pending_pa = None
        self._pending_stream = None

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
                            self.oww_model.reset()
                            self.trigger_wake()

                            # Open the recording stream BEFORE playing the wake cue and
                            # before tearing down the detection stream, so real capture
                            # is already live when the cue starts -- eliminates the dead
                            # gap where no stream was open at all (BUGS.md Bug #10, fix
                            # attempt #2). Best-effort: if this fails (e.g. the device
                            # doesn't support a second simultaneous open), fall through
                            # with no pending stream and record_phrase() opens its own
                            # afterward exactly as before -- degraded, not broken.
                            try:
                                pending_pa = pyaudio.PyAudio()
                                pending_chunk_samples = int(TARGET_RATE * 0.1)
                                pending_stream = pending_pa.open(
                                    format=pyaudio.paInt16,
                                    channels=1,
                                    rate=TARGET_RATE,
                                    input=True,
                                    frames_per_buffer=pending_chunk_samples,
                                )
                                self._pending_pa = pending_pa
                                self._pending_stream = pending_stream
                            except Exception as pending_err:
                                print(
                                    f"[WakeWordListener Warning] Could not pre-open "
                                    f"recording stream before wake cue: {pending_err}"
                                )
                                self._pending_pa = None
                                self._pending_stream = None

                            play_wake_cue()

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
        duration: float = None,
        output_filename: str = "temp_input.wav",
        sample_rate: int = TARGET_RATE,
        channels: int = 1,
        rms_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """
        Immediately after wake word trigger, records audio until dynamic trailing-silence
        is detected or a hard maximum duration is reached, whichever comes first, and
        saves to output_filename.

        Endpointing (BUGS.md Bug #10 -- fix attempt #2, `[2026-09-26]`, PENDING LIVE
        VERIFICATION, not yet confirmed; fix attempt #1 from `[2026-09-17]` did not
        resolve the bug per real user voice testing). The first VAD_CALIBRATION_SECONDS
        of this recording are used to measure this room's actual ambient noise level, and
        the real speech/silence threshold is set dynamically as
        ambient_stat * VAD_THRESHOLD_MULTIPLIER -- not a flat constant. RMS is computed
        from the signal after the same software pre-gain (self.gain_scaler) applied in
        listen_for_wakeword() -- silence detection must judge the same boosted signal the
        rest of the pipeline already relies on, not the raw, quieter one. The gain is
        applied only for the RMS/threshold decision; the WAV saved to disk is still the
        original, unboosted audio, to avoid any gain-related clipping artifacts degrading
        STT accuracy.

        Calibration statistic (changed in fix attempt #2): a high percentile (90th) of the
        calibration window, not the mean. Fix attempt #1 used mean-of-4-chunks (0.4s) and
        a fixed VAD_MIN_THRESHOLD=150.0 as a safety floor; real voice testing then measured
        actual ambient floors of 6.8-72 RMS across four separate real recordings, all of
        which produced the exact same effective threshold of 150 -- the floor was
        dominating in every real case, collapsing "dynamic" calibration back into a static
        value. The floor itself was the wrong mechanism: no fixed constant can correctly
        sit above every anomalously-quiet mean-of-a-tiny-sample while also staying below
        every real room's normal ambient level, because those two things overlap. A
        percentile over a slightly longer window (VAD_CALIBRATION_SECONDS, 0.4->0.7s) is
        naturally robust to a momentary quiet instant without needing a rescuing floor --
        VAD_MIN_THRESHOLD is now 20.0, a true degenerate-case guard (a calibration reading
        at or near true zero) rather than the primary mechanism.

        Known limitation: if the user starts speaking immediately upon wake-word trigger,
        within the calibration window, that speech gets folded into the "ambient" sample,
        inflating the floor and threshold. Not fully solved here -- flagged in CHANGELOG.md.

        Onset debounce: a single chunk above threshold does not by itself mark speech as
        started -- VAD_ONSET_SECONDS of *sustained* above-threshold audio is required
        first. Without this, live testing showed a brief transient (not real speech)
        could flag speech_started=True, after which normal quiet ambient audio reads as
        trailing silence and ends the recording early, capturing nothing real.

        Known limitation, inherent to pure RMS-based endpointing (pre-dates this fix, not
        introduced by it): this cannot distinguish continued speech from other loud,
        non-speech noise (typing, a chair creak, background chatter) once speech_started
        is True -- either keeps resetting silence_counter, so the recording can run to
        the full hard cap even after the user has actually finished talking. Live testing
        observed this directly. A real fix would need content-aware voice activity
        detection, not just loudness; out of scope here.

        Stream pre-opening (fix attempt #2, front-clipping): if listen_for_wakeword()
        pre-opened a recording stream before playing the wake cue (see that method), this
        picks it up instead of opening a fresh one, so capture was already live during the
        cue -- eliminating the dead gap (measured ~380ms on this machine) where no stream
        was open at all between the old detection stream closing and a new one opening,
        which was losing the first spoken word. Falls back to opening its own stream if no
        pending one exists or its format doesn't match the requested sample_rate/channels.
        """
        if duration is None:
            duration = getattr(config, "VAD_HARD_CAP_SECONDS", 10.0)
        trailing_silence_seconds = getattr(config, "VAD_TRAILING_SILENCE_SECONDS", 2.0)
        threshold_multiplier = getattr(config, "VAD_THRESHOLD_MULTIPLIER", 1.4)
        calibration_seconds = getattr(config, "VAD_CALIBRATION_SECONDS", 0.7)
        onset_seconds = getattr(config, "VAD_ONSET_SECONDS", 0.2)
        min_threshold = getattr(config, "VAD_MIN_THRESHOLD", 20.0)

        print(f"[WakeWordListener] Recording phrase (max {duration}s)...", flush=True)
        chunk_duration = 0.1
        chunk_samples = int(sample_rate * chunk_duration)
        max_chunks = int(duration / chunk_duration)
        silence_target_chunks = max(1, int(trailing_silence_seconds / chunk_duration))
        calibration_chunks = max(1, int(calibration_seconds / chunk_duration))
        onset_target_chunks = max(1, int(onset_seconds / chunk_duration))

        audio_chunks = []
        calibration_rms_values = []
        speech_threshold = None
        speech_started = False
        onset_counter = 0
        silence_counter = 0

        # Reuse a stream listen_for_wakeword() pre-opened before the wake cue, if one
        # exists and matches this call's requested format -- see the docstring above and
        # BUGS.md Bug #10 (fix attempt #2). Otherwise open fresh, exactly as before.
        pa = None
        stream = None
        if self._pending_stream is not None and self._pending_pa is not None:
            if sample_rate == TARGET_RATE and channels == 1:
                pa = self._pending_pa
                stream = self._pending_stream
                print("[WakeWordListener] Reusing pre-opened recording stream (no post-cue gap).", flush=True)
            else:
                # Format mismatch -- discard the pending stream rather than risk
                # capturing at the wrong rate/channel count.
                try:
                    self._pending_stream.stop_stream()
                    self._pending_stream.close()
                    self._pending_pa.terminate()
                except Exception:
                    pass
            self._pending_pa = None
            self._pending_stream = None

        if stream is None:
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

                # Same software pre-gain applied to wake-word detection -- silence
                # detection must judge the boosted signal, not the raw, quieter one.
                boosted = np.clip(data.astype(np.float32) * self.gain_scaler, -32768, 32767)
                rms = float(np.sqrt(np.mean(boosted ** 2)))
                if rms_callback:
                    try:
                        norm_rms = min(1.0, rms / 1200.0)
                        rms_callback(norm_rms)
                    except Exception:
                        pass

                if speech_threshold is None:
                    calibration_rms_values.append(rms)
                    if len(calibration_rms_values) >= calibration_chunks:
                        # 90th percentile, not mean (fix attempt #2) -- a plain mean over
                        # a short window is easily dragged down by one momentary quiet
                        # instant, producing an unrepresentatively low ambient estimate.
                        # The 90th percentile reflects the louder, more typical tail of
                        # the calibration window instead, so it's naturally robust to a
                        # brief lull without needing a rescuing absolute floor to do the
                        # real work (see config.py for the fix attempt #1 failure mode
                        # this replaces). VAD_MIN_THRESHOLD below is now only a true
                        # degenerate-case guard, not the primary mechanism.
                        ambient_stat = float(np.percentile(calibration_rms_values, 90))
                        speech_threshold = max(ambient_stat * threshold_multiplier, min_threshold)
                        print(
                            f"[WakeWordListener] Ambient level calibrated at "
                            f"{ambient_stat:.1f} RMS (90th pct) -> speech threshold "
                            f"{speech_threshold:.1f} (x{threshold_multiplier}).",
                            flush=True,
                        )
                    continue

                if rms > speech_threshold:
                    if speech_started:
                        silence_counter = 0
                    else:
                        onset_counter += 1
                        if onset_counter >= onset_target_chunks:
                            speech_started = True
                            silence_counter = 0
                        # else: still confirming a sustained onset, not yet real speech
                else:
                    onset_counter = 0
                    if speech_started:
                        silence_counter += 1
                        if silence_counter >= silence_target_chunks:
                            print(
                                f"[WakeWordListener] End of phrase detected "
                                f"({trailing_silence_seconds}s silence).",
                                flush=True,
                            )
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
            duration=getattr(config, "VAD_HARD_CAP_SECONDS", 10.0),
            output_filename="temp_input.wav",
            sample_rate=sample_rate,
            rms_callback=rms_callback,
        )


if __name__ == "__main__":
    listener = WakeWordListener()
    print("[WakeWordListener] Initialized successfully.")
