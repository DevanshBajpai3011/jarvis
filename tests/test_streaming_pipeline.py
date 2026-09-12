"""
Manual diagnostic script (like tests/test_self_healer.py -- not a pytest
suite, no assertions) proving that PrimaryBrain's real Gemini streaming call
can be wired through SentenceChunker and into the existing 3-tier TTS system,
with each completed sentence spoken as soon as it's confirmed ready while the
rest of the LLM response is still streaming in from Gemini.

This is Step 2 of the streaming-TTS rewrite (see CHANGELOG.md; Step 1 was
utils/sentence_chunker.py). It is deliberately isolated: it does NOT touch
brain/orchestrator.py, brain/agent.py (AutonomousAgent), or brain/planner.py
(TaskPlanner) -- proving the pipeline works standalone before Step 3 tackles
how it should interact with the shared self.brain instance those other
classes rely on (see the earlier scoping-diagnosis CHANGELOG entry for why
that's a real, separate design question).

Architecture: the main thread pulls raw text deltas from
PrimaryBrain.stream_think() and feeds them into a SentenceChunker. Each
confirmed sentence is pushed onto a queue.Queue immediately. A separate
daemon thread drains that queue and calls tts.manager.get_tts_manager().speak()
on each sentence in turn -- since that call blocks until the sentence has
fully finished playing before returning, sentences are guaranteed to play
strictly one after another with no possibility of overlap, while the main
thread keeps consuming more of the LLM stream in the background rather than
waiting for audio playback.

Only tests the plain streaming branch of stream_think() (a factual prompt
unlikely to trigger a mid-stream tool call) -- the tool-calling-mid-stream
branch is separate, never-battle-tested code not exercised here.

Run manually: python tests/test_streaming_pipeline.py
"""
import sys
import os
import time
import queue
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brain.primary_brain import PrimaryBrain
from utils.sentence_chunker import SentenceChunker
from tts.manager import get_tts_manager

PROMPT = "Tell me three interesting facts about the solar system, each as its own complete sentence."


def tts_worker(sentence_queue: "queue.Queue", tts_manager, timings: dict, log: list):
    """
    Pulls completed sentences off the queue and speaks them strictly one at a
    time -- each speak() call blocks until that sentence's audio has fully
    finished playing before the loop advances to the next item, which is
    what guarantees no overlap between sentences by construction.
    """
    sentence_num = 0
    while True:
        item = sentence_queue.get()
        if item is None:
            sentence_queue.task_done()
            break
        sentence_num += 1
        t_handoff = time.time()
        if sentence_num == 1:
            timings["first_sentence_handoff"] = t_handoff
        log.append(f"[TTS] Handing off sentence {sentence_num} to speak(): {item!r}")
        print(log[-1], flush=True)
        tts_manager.speak(item)
        t_done = time.time()
        log.append(f"[TTS] Finished playing sentence {sentence_num} (took {t_done - t_handoff:.2f}s incl. synthesis+playback)")
        print(log[-1], flush=True)
        sentence_queue.task_done()


def main():
    print("=" * 70)
    print("STREAMING PIPELINE TEST: PrimaryBrain -> SentenceChunker -> TTS")
    print("=" * 70)
    print(f"PROMPT: {PROMPT!r}")
    print()

    brain = PrimaryBrain()
    chunker = SentenceChunker()
    tts_manager = get_tts_manager()

    sentence_queue = queue.Queue()
    timings = {}
    log = []

    worker = threading.Thread(target=tts_worker, args=(sentence_queue, tts_manager, timings, log), daemon=True)
    worker.start()

    t_start = time.time()
    timings["request_start"] = t_start

    full_response_parts = []
    raw_chunk_count = 0
    sentences_queued = 0
    try:
        for delta in brain.stream_think(PROMPT):
            raw_chunk_count += 1
            full_response_parts.append(delta)
            ready_sentences = chunker.add_chunk(delta)
            for sentence in ready_sentences:
                sentences_queued += 1
                print(f"[Main] Sentence {sentences_queued} confirmed at t={time.time() - t_start:.2f}s, queued for TTS: {sentence!r}")
                sentence_queue.put(sentence)
    finally:
        final_remainder = chunker.flush()
        if final_remainder:
            sentences_queued += 1
            print(f"[Main] Final flush() remainder at t={time.time() - t_start:.2f}s, queued for TTS: {final_remainder!r}")
            sentence_queue.put(final_remainder)
        sentence_queue.put(None)  # sentinel: no more sentences coming

    t_stream_done = time.time()
    print()
    print(f"[Main] LLM stream finished after {t_stream_done - t_start:.2f}s ({raw_chunk_count} raw text deltas received, {sentences_queued} sentences produced).")
    print(f"[Main] Full response text: {''.join(full_response_parts)!r}")
    print("[Main] Waiting for TTS worker to finish speaking any remaining queued sentences...")

    sentence_queue.join()
    worker.join(timeout=10)
    t_all_done = time.time()

    print()
    print("=" * 70)
    print("TIMING SUMMARY")
    print("=" * 70)
    first_handoff = timings.get("first_sentence_handoff")
    if first_handoff:
        print(f"(a) Time to FIRST sentence handed to TTS (request start -> speak() called): {first_handoff - t_start:.2f}s")
    else:
        print("(a) No sentence was ever handed to TTS before the stream ended.")
    print(f"(b) Total time to finish speaking the ENTIRE response (request start -> last audio done): {t_all_done - t_start:.2f}s")
    print()
    print("Old sequential baseline (from the earlier latency-breakdown diagnosis):")
    print("  9.47s blocking LLM call (Brain.think(), full response before anything else happens)")
    print("  + 4.55s TTS Tier-1 SYNTHESIS ONLY (that measurement excluded actual audio playback time)")
    print("  = 14.02s of total silence before the FIRST word could even be synthesized,")
    print("    let alone heard -- and that 14.02s does not yet include playback time at all.")
    print()
    print("Caveat: (b) above DOES include actual audio playback time (tts_manager.speak() blocks")
    print("until each sentence finishes playing), which the old 4.55s figure explicitly excluded --")
    print("so (b) is not a like-for-like comparison against the old numbers on its own. The")
    print("meaningful comparison is (a): how much silence the user experiences before ANY audio")
    print("starts, old (14.02s, whole response) vs. new (this run's measured value above, one")
    print("sentence's worth of streaming instead of the whole response).")


if __name__ == "__main__":
    main()
