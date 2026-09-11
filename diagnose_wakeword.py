import math
import wave
import numpy as np
from scipy.signal import resample_poly
from openwakeword.model import Model

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    import pyaudio

def run_diagnostics():
    p = pyaudio.PyAudio()
    dev_info = p.get_default_input_device_info()
    
    native_rate = int(dev_info.get("defaultSampleRate", 16000))
    native_channels = max(1, min(int(dev_info.get("maxInputChannels", 1)), 2))
    native_chunk_size = int(native_rate * 0.08)  # 80ms chunk
    target_rate = 16000
    target_chunk_size = 1280

    print("=" * 60)
    print(" AUDIO TELEMETRY & WAKEWORD DIAGNOSTIC")
    print("=" * 60)
    print(f"Device Name:        {dev_info['name']}")
    print(f"Native Rate:        {native_rate} Hz")
    print(f"Native Channels:    {native_channels}")
    print(f"Native Chunk Size:  {native_chunk_size} frames")
    print(f"Target Rate:        {target_rate} Hz (1280 chunk)")
    print("=" * 60)

    # Initialize openWakeWord
    print("[*] Loading openWakeWord 'hey_jarvis' model...")
    oww_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    
    stream = p.open(
        format=pyaudio.paInt16,
        channels=native_channels,
        rate=native_rate,
        input=True,
        frames_per_buffer=native_chunk_size
    )

    print("\n[!] RECORDING FOR 5 SECONDS...")
    print("[!] Say 'Hey Jarvis' clearly 2 or 3 times now!\n")

    audio_buffer = np.array([], dtype=np.int16)
    saved_frames_16k = []
    chunk_count = 0
    max_score = 0.0

    print(f"{'Chunk':<6} | {'RMS':<8} | {'Min/Max':<14} | {'Score':<8} | {'Status'}")
    print("-" * 55)

    for _ in range(int(native_rate / native_chunk_size * 5)):
        raw_bytes = stream.read(native_chunk_size, exception_on_overflow=False)
        data = np.frombuffer(raw_bytes, dtype=np.int16)

        # Convert stereo to mono
        if native_channels > 1:
            data = data.reshape(-1, native_channels).mean(axis=1).astype(np.int16)

        # Resample to 16kHz
        if native_rate != target_rate:
            gcd = math.gcd(target_rate, native_rate)
            up = target_rate // gcd
            down = native_rate // gcd
            resampled = resample_poly(data.astype(np.float32), up, down).astype(np.int16)
        else:
            resampled = data

        audio_buffer = np.append(audio_buffer, resampled)

        # Process 1280 chunks
        while len(audio_buffer) >= target_chunk_size:
            chunk_count += 1
            chunk = audio_buffer[:target_chunk_size]
            audio_buffer = audio_buffer[target_chunk_size:]
            saved_frames_16k.append(chunk)

            rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
            min_val, max_val = chunk.min(), chunk.max()
            
            oww_model.predict(chunk)
            score = oww_model.prediction_buffer["hey_jarvis"][-1]
            if score > max_score:
                max_score = score

            bar = "#" * int(score * 30)
            status = f"TRIGGER ({score:.2f})" if score >= 0.5 else bar
            print(f"{chunk_count:<6} | {rms:<8.1f} | [{min_val:6}, {max_val:5}] | {score:<8.4f} | {status}")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # Save output wav to inspect sound quality
    wav_out = "debug_rdp_capture.wav"
    with wave.open(wav_out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(np.concatenate(saved_frames_16k).tobytes())

    print("\n" + "=" * 60)
    print(f"Max Confidence Score Reached: {max_score:.4f}")
    print(f"Saved 16kHz resampled audio to: {wav_out}")
    print("=" * 60)

if __name__ == "__main__":
    run_diagnostics()