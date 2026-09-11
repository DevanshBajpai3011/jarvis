import queue
import threading
import wave
import io
import time
import logging
from typing import Optional
import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioStreamPlayer:
    """
    Continuous Audio Output Stream Player with residual byte buffering for odd-byte chunk alignment.
    Eliminates hardware reset clicks and pauses between TTS sentence chunks
    by maintaining a single background sounddevice OutputStream fed from a thread-safe Queue.
    Includes pre-buffering to ensure smooth gapless speech playback.
    """

    def __init__(self, default_samplerate: int = 22050):
        self.default_samplerate = default_samplerate
        self.audio_queue = queue.Queue()
        self.is_playing = False
        self.interrupt_event: Optional[threading.Event] = None
        self._thread = None
        self._lock = threading.Lock()
        self._byte_buffer = bytearray()

    def play_chunks(self, chunk_generator, prebuffer_count: int = 2, interrupt_event: Optional[threading.Event] = None):
        """
        Consumes audio WAV/PCM bytes from a chunk generator, pre-buffers initial chunks,
        and streams them seamlessly through a single continuous sounddevice OutputStream.

        Args:
            chunk_generator: Generator or iterable yielding WAV bytes or PCM arrays.
            prebuffer_count (int): Number of initial chunks to buffer before starting playback.
            interrupt_event (threading.Event, optional): Thread flag to signal instant barge-in interruption.
        """
        self.interrupt_event = interrupt_event
        self._byte_buffer.clear()
        buffer = []
        gen_iter = iter(chunk_generator)

        # 1. Pre-buffer initial chunks to prevent gaps
        for _ in range(prebuffer_count):
            if self.interrupt_event and self.interrupt_event.is_set():
                return
            try:
                chunk = next(gen_iter)
                if chunk:
                    buffer.append(chunk)
            except StopIteration:
                break

        if not buffer:
            return

        # 2. Put pre-buffered chunks into the Queue
        for chunk in buffer:
            self.audio_queue.put(chunk)

        # 3. Start background playback loop if not running
        with self._lock:
            if not self.is_playing:
                self.is_playing = True
                self._thread = threading.Thread(target=self._playback_loop, daemon=True)
                self._thread.start()

        # 4. Stream remaining chunks into the Queue
        for chunk in gen_iter:
            if self.interrupt_event and self.interrupt_event.is_set():
                break
            if chunk:
                self.audio_queue.put(chunk)

        # Sentinel to mark end of current stream sequence
        self.audio_queue.put(None)

        # Wait for current stream sequence to finish playing
        if self._thread and self._thread.is_alive():
            self._thread.join()

    def stop(self):
        """Immediately interrupts playback and flushes remaining queued audio chunks."""
        with self._lock:
            self.is_playing = False
            if self.interrupt_event:
                self.interrupt_event.set()
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except Exception:
                break

    def _playback_loop(self):
        """
        Background worker thread consuming audio chunks from the queue
        and writing PCM frames to sounddevice stream.
        """
        logger.info("[AudioStreamPlayer] Continuous playback stream started.")
        current_stream = None
        current_rate = self.default_samplerate

        try:
            while self.is_playing:
                if self.interrupt_event and self.interrupt_event.is_set():
                    logger.info("[AudioStreamPlayer] Playback interrupted by interrupt_event.")
                    break

                try:
                    chunk = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if chunk is None:
                    # End of stream sequence
                    break

                # Extract PCM array and samplerate from chunk
                audio_array, samplerate = self._decode_chunk(chunk)
                if audio_array is None or len(audio_array) == 0:
                    self.audio_queue.task_done()
                    continue

                # Initialize or recreate OutputStream if sample rate changed
                if current_stream is None or current_rate != samplerate:
                    if current_stream is not None:
                        try:
                            current_stream.stop()
                            current_stream.close()
                        except Exception:
                            pass

                    current_rate = samplerate
                    current_stream = sd.OutputStream(
                        samplerate=current_rate,
                        channels=1,
                        dtype="int16",
                    )
                    current_stream.start()

                # Write audio PCM array to active sounddevice stream in 1024-sample blocks
                block_size = 1024
                interrupted = False
                for i in range(0, len(audio_array), block_size):
                    if self.interrupt_event and self.interrupt_event.is_set():
                        interrupted = True
                        break
                    sub_block = audio_array[i : i + block_size]
                    current_stream.write(sub_block)

                self.audio_queue.task_done()
                if interrupted:
                    logger.info("[AudioStreamPlayer] Interrupted during sub-block playback.")
                    break

        except Exception as e:
            logger.error(f"[AudioStreamPlayer Error] {e}")
        finally:
            if current_stream:
                try:
                    current_stream.stop()
                    current_stream.close()
                except Exception:
                    pass
            self._byte_buffer.clear()
            with self._lock:
                self.is_playing = False
            logger.info("[AudioStreamPlayer] Playback stream finished cleanly.")


    def _decode_chunk(self, chunk) -> tuple[np.ndarray, int]:
        """
        Decodes input chunk (WAV bytes, raw bytes/bytearray, tuple, or numpy array)
        into (np.int16 array, samplerate) with residual byte buffering for 2-byte sample alignment.
        """
        if isinstance(chunk, tuple):
            raw_data, rate = chunk[0], chunk[1]
            if isinstance(raw_data, (bytes, bytearray)):
                self._byte_buffer.extend(raw_data)
                usable_len = (len(self._byte_buffer) // 2) * 2
                if usable_len > 0:
                    usable_bytes = bytes(self._byte_buffer[:usable_len])
                    self._byte_buffer = self._byte_buffer[usable_len:]
                    arr = np.frombuffer(usable_bytes, dtype=np.int16)
                    return arr, rate
                else:
                    return np.array([], dtype=np.int16), rate
            elif isinstance(raw_data, np.ndarray):
                return raw_data, rate

        if isinstance(chunk, np.ndarray):
            return chunk, self.default_samplerate

        if isinstance(chunk, (bytes, bytearray)):
            # Check if chunk is WAV file bytes
            if isinstance(chunk, bytes) and chunk.startswith(b"RIFF"):
                try:
                    with wave.open(io.BytesIO(chunk), "rb") as wf:
                        samplerate = wf.getframerate()
                        n_channels = wf.getnchannels()
                        sampwidth = wf.getsampwidth()
                        raw_frames = wf.readframes(wf.getnframes())

                        dtype = np.int16 if sampwidth == 2 else np.int32
                        arr = np.frombuffer(raw_frames, dtype=dtype)
                        if n_channels > 1:
                            arr = arr.reshape(-1, n_channels)[:, 0]
                        return arr, samplerate
                except Exception:
                    pass

            self._byte_buffer.extend(chunk)
            usable_len = (len(self._byte_buffer) // 2) * 2
            if usable_len > 0:
                usable_bytes = bytes(self._byte_buffer[:usable_len])
                self._byte_buffer = self._byte_buffer[usable_len:]
                arr = np.frombuffer(usable_bytes, dtype=np.int16)
                return arr, self.default_samplerate
            else:
                return np.array([], dtype=np.int16), self.default_samplerate

        return None, self.default_samplerate


if __name__ == "__main__":
    player = AudioStreamPlayer()
    print("[AudioStreamPlayer] Initialized successfully with odd-byte alignment buffer.")
