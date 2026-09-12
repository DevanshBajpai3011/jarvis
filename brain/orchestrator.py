import os
import re
import logging
import queue
import threading
import concurrent.futures
from typing import Optional, Callable, Dict, Any

from wakeword import WakeWordListener
from stt import WhisperSTT
from tts import PiperTTS, get_tts_manager, TTSManager, speech_engine, SpeechEngine
from brain.persona import JARVIS_SYSTEM_PROMPT
from brain.llm import Brain
from brain.primary_brain import PrimaryBrain
from brain.openrouter_client import OpenRouterBrain
from brain.planner import TaskPlanner
from brain.state import ExecutionState
from brain.agent import AutonomousAgent
from memory import MemoryManager
from vision import VisionCapturer
from tools import FileParser, open_application, manage_reminder, execute_whitelisted_script
from utils.sentence_chunker import SentenceChunker

logger = logging.getLogger(__name__)


def find_file_in_text(text: str) -> Optional[str]:
    """
    Scans input text for potential file paths or mentioned files.
    Returns file_path if an existing file is found on disk, else None.
    """
    if not text:
        return None
    quoted_paths = re.findall(r'["\']([^"\']+)["\']', text)
    for q in quoted_paths:
        if os.path.isfile(q):
            return q
    tokens = text.split()
    for token in tokens:
        clean_token = token.strip(".,;:!?()[]'\"")
        if os.path.isfile(clean_token):
            return clean_token
    return None


class Orchestrator:
    """
    Central system orchestrator unifying speech, vision, memory, LLM reasoning,
    tool execution, and autonomous task planning into a coordinated pipeline.
    """

    SCREEN_KEYWORDS = [
        "look at my screen", "what's on my screen", "see my screen",
        "check my screen", "screen capture", "my screen"
    ]
    WEBCAM_KEYWORDS = [
        "look at me", "take a picture", "take a photo",
        "webcam", "see me", "snapshot"
    ]
    AUTONOMOUS_KEYWORDS = [
        "plan and", "set up my workspace", "setup my workspace",
        "do the following steps", "execute task", "multi-step",
        "workflow", "run pipeline"
    ]

    def __init__(
        self,
        listener: Optional[WakeWordListener] = None,
        stt: Optional[WhisperSTT] = None,
        brain: Optional[Brain] = None,
        primary_brain: Optional[PrimaryBrain] = None,
        openrouter_brain: Optional[OpenRouterBrain] = None,
        memory_manager: Optional[MemoryManager] = None,
        tts: Optional[SpeechEngine] = None,
        vision_capturer: Optional[VisionCapturer] = None,
        file_parser: Optional[FileParser] = None,
        autonomous_agent: Optional[AutonomousAgent] = None,
    ):
        logger.info("[Orchestrator] Initializing unified system orchestrator...")
        self.listener = listener or WakeWordListener()
        self.stt = stt or WhisperSTT()
        # self.brain (non-streaming Brain) is kept separate from self.primary_brain
        # (streaming PrimaryBrain) deliberately -- TaskPlanner and AutonomousAgent both
        # need a synchronous, complete-string .think() (TaskPlanner even parses the
        # result as JSON), which PrimaryBrain does not provide at all (only
        # .stream_think()). Sharing one instance between them was considered and
        # rejected; see CHANGELOG.md's Step 3 entry for the full blast-radius analysis.
        self.brain = brain or Brain()
        self.primary_brain = primary_brain or PrimaryBrain()
        self.openrouter_brain = openrouter_brain or OpenRouterBrain()
        self.memory_manager = memory_manager or MemoryManager()
        self.tts = tts or speech_engine
        self.vision_capturer = vision_capturer or VisionCapturer()
        self.file_parser = file_parser or FileParser()
        self.autonomous_agent = autonomous_agent or AutonomousAgent(
            planner=TaskPlanner(openrouter_client=self.openrouter_brain, gemini_brain=self.brain)
        )

    def process_input(
        self,
        user_text: Optional[str] = None,
        audio_file: Optional[str] = None,
        image_path: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        message_callback: Optional[Callable[[str, str], None]] = None,
        action_callback: Optional[Callable[[str], None]] = None,
        display_callback: Optional[Callable[[str, str], None]] = None,
        on_complete_callback: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:

        """
        Coordinates the end-to-end processing pipeline for text, audio, or vision inputs.

        Args:
            user_text (str, optional): Direct typed or spoken input string.
            audio_file (str, optional): Path to WAV audio recording to transcribe via STT.
            image_path (str, optional): Explicit image file path for visual analysis.
            status_callback (Callable, optional): Function/Signal to update status (e.g. 'THINKING', 'SPEAKING').
            message_callback (Callable, optional): Function/Signal to output messages (sender, content).
            action_callback (Callable, optional): Function/Signal to log executed system actions (e.g., 'Opened Notepad').
            display_callback (Callable, optional): Function/Signal to update UI elements.

        Returns:
            Dict[str, Any]: Result dictionary containing 'transcript', 'response', and 'status'.
        """
        def update_status(status: str):
            if status_callback:
                try:
                    status_callback(status)
                except Exception as e:
                    logger.warning(f"Status callback error: {e}")

        def emit_message(sender: str, content: str):
            if message_callback:
                try:
                    message_callback(sender, content)
                except Exception as e:
                    logger.warning(f"Message callback error: {e}")

        def emit_action(action_desc: str):
            if action_callback:
                try:
                    action_callback(action_desc)
                except Exception as e:
                    logger.warning(f"Action callback error: {e}")

        transcript = user_text or ""

        # Step 1: Handle audio transcription if audio_file provided and user_text is empty
        if not transcript and audio_file and os.path.exists(audio_file):
            update_status("THINKING")
            logger.info(f"[Orchestrator] Transcribing audio file: {audio_file}")
            transcript = self.stt.transcribe(audio_file)
            if transcript:
                emit_message("YOU", transcript)

        if not transcript or not transcript.strip():
            fallback_res = "I didn't quite catch that, sir."
            emit_message("J.A.R.V.I.S.", fallback_res)
            update_status("SPEAKING")
            if self.tts:
                self.tts.speak(fallback_res)
            update_status("STANDBY")
            return {"transcript": "", "response": fallback_res, "status": "empty"}

        transcript_clean = transcript.strip()
        transcript_lower = transcript_clean.lower()
        active_image_path = image_path

        # Step 2: Check for Multi-Step Autonomous Goal Trigger
        if any(kw in transcript_lower for kw in self.AUTONOMOUS_KEYWORDS):
            logger.info(f"[Orchestrator] Autonomous task trigger detected for prompt: '{transcript_clean}'")
            update_status("EXECUTING")
            emit_action(f"Autonomous Goal: {transcript_clean[:30]}")
            response = self.autonomous_agent.execute_goal(transcript_clean, brain=self.brain, tts=self.tts)
            emit_message("J.A.R.V.I.S.", response)
            update_status("STANDBY")
            return {"transcript": transcript_clean, "response": response, "status": "completed"}

        # Step 3: Single-Turn Pipeline Processing
        update_status("THINKING")

        recalled_context = ""
        # Parallel Vector Memory Context Retrieval
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            memory_future = executor.submit(self.memory_manager.get_relevant_context, transcript_clean)

            # File Reference Parsing
            file_path = find_file_in_text(transcript_clean)
            if file_path:
                logger.info(f"[Orchestrator] Found file reference: {file_path}")
                emit_action(f"Parsed file '{os.path.basename(file_path)}'")
                parsed = self.file_parser.parse_file(file_path)
                if parsed["type"] == "text":
                    file_info = f"\n\n--- Content of {os.path.basename(file_path)} ---\n{parsed['content']}"
                    recalled_context = f"{recalled_context}{file_info}".strip()
                elif parsed["type"] == "image":
                    active_image_path = parsed["content"]

            # Vision Capture Intent Detection
            if not active_image_path and any(kw in transcript_lower for kw in self.SCREEN_KEYWORDS):
                update_status("EXECUTING")
                active_image_path = self.vision_capturer.capture_screen()
                if active_image_path:
                    logger.info(f"[Orchestrator] Screen capture grabbed: {active_image_path}")
                    emit_action("Captured screen content")

            if not active_image_path and any(kw in transcript_lower for kw in self.WEBCAM_KEYWORDS):
                update_status("EXECUTING")
                active_image_path = self.vision_capturer.capture_webcam()
                if active_image_path:
                    logger.info(f"[Orchestrator] Webcam snapshot grabbed: {active_image_path}")
                    emit_action("Captured webcam photo")

            try:
                retrieved_mem = memory_future.result(timeout=2.0) or ""
                if retrieved_mem:
                    recalled_context = f"{retrieved_mem}\n{recalled_context}".strip()
            except Exception as mem_err:
                logger.warning(f"[Orchestrator] Parallel memory retrieval note: {mem_err}")

        # LLM Generation & Tool Execution -- streamed: PrimaryBrain.stream_think()
        # feeds a SentenceChunker, and each confirmed sentence is handed to TTS on a
        # dedicated background thread the moment it's ready, while the LLM stream
        # keeps running for the rest of the response (proven in
        # tests/test_streaming_pipeline.py, Step 2 of the streaming-TTS rewrite).
        update_status("SPEAKING")

        chunker = SentenceChunker()
        sentence_queue: "queue.Queue" = queue.Queue()

        def _tts_worker():
            while True:
                item = sentence_queue.get()
                if item is None:
                    sentence_queue.task_done()
                    break
                text, is_last = item
                try:
                    if is_last and on_complete_callback:
                        try:
                            self.tts.speak(text, on_complete_callback=on_complete_callback)
                        except TypeError:
                            self.tts.speak(text)
                            on_complete_callback()
                    else:
                        self.tts.speak(text)
                except Exception as tts_err:
                    logger.warning(f"[Orchestrator] TTS playback error: {tts_err}")
                sentence_queue.task_done()

        tts_thread = None
        if self.tts:
            tts_thread = threading.Thread(target=_tts_worker, daemon=True)
            tts_thread.start()

        # held_sentence implements a one-behind buffer: we don't know a confirmed
        # sentence is the LAST one until either another sentence arrives after it
        # (proving it wasn't last) or the stream ends -- this is what lets
        # on_complete_callback attach to the correct (final) speak() call without
        # touching the turn-completion signal logic itself (that's Step 4).
        held_sentence = None
        full_response_parts = []
        try:
            for delta in self.primary_brain.stream_think(
                transcript_clean,
                context=recalled_context,
                image_path=active_image_path,
                action_callback=emit_action,
                display_callback=display_callback
            ):
                full_response_parts.append(delta)
                if self.tts:
                    for sentence in chunker.add_chunk(delta):
                        if held_sentence is not None:
                            sentence_queue.put((held_sentence, False))
                        held_sentence = sentence
        finally:
            if self.tts:
                final_remainder = chunker.flush()
                if final_remainder:
                    if held_sentence is not None:
                        sentence_queue.put((held_sentence, False))
                    held_sentence = final_remainder

                if held_sentence is not None:
                    sentence_queue.put((held_sentence, True))
                elif on_complete_callback:
                    # Nothing was ever produced -- don't leave the follow-up window
                    # mechanism (or anything else waiting on this signal) hanging.
                    try:
                        on_complete_callback()
                    except Exception as cb_err:
                        logger.warning(f"[Orchestrator] on_complete_callback error: {cb_err}")

                sentence_queue.put(None)

        response = "".join(full_response_parts)
        emit_message("J.A.R.V.I.S.", response)

        if tts_thread:
            sentence_queue.join()
            tts_thread.join(timeout=60)

        # Background Cognitive Memory Extraction & Memory Store Update
        try:
            from brain.router import BrainRouter
            router = BrainRouter()
            router.trigger_post_turn_cognitive_extraction(transcript_clean, response)
        except Exception as e:
            logger.warning(f"[Orchestrator] Background cognitive memory update failed: {e}")

        update_status("STANDBY")
        return {
            "transcript": transcript_clean,
            "response": response,
            "image_path": active_image_path,
            "status": "completed"
        }
