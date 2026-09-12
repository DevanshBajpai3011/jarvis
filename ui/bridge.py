import os
import logging
import threading
import time
from typing import Optional, Callable
from PySide6.QtCore import QObject, QThread, Signal, Slot
import config
from brain import Orchestrator
from ui.overlay import JarvisOverlay

logger = logging.getLogger(__name__)


class CommandWorker(QThread):
    """
    Worker thread that executes LLM reasoning, vision capture, tool execution,
    and TTS speech output off the main GUI thread via Orchestrator.
    """
    status_changed = Signal(str)
    message_generated = Signal(str, str)  # (sender, text)
    action_logged = Signal(str)  # action description
    display_requested = Signal(str, str)  # (title, markdown_content)
    response_generated = Signal(str)  # full response text
    finished_processing = Signal()

    def __init__(self, user_input: str, orchestrator: Orchestrator, on_complete_callback: Optional[Callable[[], None]] = None):
        super().__init__()
        self.user_input = user_input
        self.orchestrator = orchestrator
        self.on_complete_callback = on_complete_callback

    def run(self):
        transcript = self.user_input.strip()
        if not transcript:
            self.finished_processing.emit()
            return

        try:
            self.status_changed.emit("THINKING")
            res = self.orchestrator.process_input(
                user_text=transcript,
                status_callback=self.status_changed.emit,
                message_callback=self.message_generated.emit,
                action_callback=self.action_logged.emit,
                display_callback=self.display_requested.emit,
                on_complete_callback=self.on_complete_callback,
            )
            response_text = res.get("response", "")
            if response_text:
                self.response_generated.emit(response_text)
        except Exception as e:
            logger.error(f"[CommandWorker Error] {e}")
            err_msg = "An error occurred while processing your request, sir."
            self.message_generated.emit("J.A.R.V.I.S.", err_msg)
        finally:
            self.status_changed.emit("STANDBY")
            self.finished_processing.emit()



class VoiceListenerWorker(QThread):
    """
    Background listener thread running openWakeWord detection loop with live RMS audio energy callbacks
    and post-reply follow-up turn-taking.
    """
    status_changed = Signal(str)
    speech_detected = Signal(str)
    rms_updated = Signal(float)

    def __init__(self, listener, stt):
        super().__init__()
        self.listener = listener
        self.stt = stt
        self.running = True

        # _voice_enabled, _followup_requested, and _followup_timeout are read/written from
        # both this thread (run()) and the GUI/CommandWorker thread (via the voice_enabled
        # property, trigger_followup_listen(), toggle_voice_listener(), etc.) -- guarded by
        # _state_lock rather than relying on bare attribute access across threads.
        self._state_lock = threading.Lock()
        self._voice_enabled = True
        self._followup_requested = False
        self._followup_timeout = getattr(config, "FOLLOW_UP_LISTEN_TIMEOUT", 8)

        # Set by CommandWorker's thread (via on_tts_complete) once a full turn -- memory
        # retrieval, LLM call, and TTS playback -- has actually finished. The ambient loop
        # waits on this instead of immediately re-entering the blocking, timeout-less
        # listen_for_wakeword() call, which previously meant the follow-up window almost
        # never got checked at a useful moment (see CHANGELOG.md for the full writeup).
        self._turn_complete_event = threading.Event()

    @property
    def voice_enabled(self) -> bool:
        with self._state_lock:
            return self._voice_enabled

    @voice_enabled.setter
    def voice_enabled(self, value: bool) -> None:
        with self._state_lock:
            self._voice_enabled = value

    def trigger_followup_listen(self, timeout: float = 8.0):
        """
        Requests a direct mic listening window (no wake word needed) once the current
        turn finishes. Called from CommandWorker's thread via on_tts_complete.
        """
        with self._state_lock:
            if self._voice_enabled:
                self._followup_timeout = timeout
                self._followup_requested = True

    def _consume_followup_request(self):
        with self._state_lock:
            requested = self._followup_requested
            timeout = self._followup_timeout
            self._followup_requested = False
            return requested, timeout

    def signal_turn_complete(self):
        """
        Called from CommandWorker's thread (via on_tts_complete) once a full turn has
        actually finished, so the ambient loop -- blocked in _wait_for_turn_complete()
        after handing off a transcript -- knows it's safe to check for a follow-up
        request or resume normal wake-word listening.
        """
        self._turn_complete_event.set()

    def _wait_for_turn_complete(self, max_wait: float = 60.0, grace: float = 1.0) -> None:
        """
        Blocks until CommandWorker signals the current turn is fully done, instead of
        immediately looping back into the blocking, timeout-less listen_for_wakeword()
        call. max_wait is a safety net in case something goes wrong downstream and
        signal_turn_complete() never fires (e.g. an exception before on_tts_complete
        runs) -- without it this thread would otherwise hang here forever. Once the
        event fires, _followup_requested is given a brief grace window to become visible
        before returning control to run(), which re-checks it at the top of the loop.
        """
        fired = self._turn_complete_event.wait(timeout=max_wait)
        if not fired:
            logger.warning(
                f"[Turn-Taking] Turn-complete signal not received within {max_wait}s "
                "safety-net timeout; resuming ambient listening anyway."
            )
            return

        grace_deadline = time.time() + grace
        while time.time() < grace_deadline:
            with self._state_lock:
                if self._followup_requested:
                    return
            time.sleep(0.05)

    def run(self):
        while self.running:
            if not self.voice_enabled:
                self.msleep(200)
                continue

            # 1. Handle Post-Reply Follow-Up Turn-Taking Window
            followup_requested, followup_timeout = self._consume_followup_request()
            if followup_requested:
                timeout = followup_timeout
                logger.info(f"[Turn-Taking] Opening {timeout}s direct mic listening window...")
                try:
                    self.status_changed.emit("LISTENING (FOLLOW-UP)")
                    wav_path = self.listener.listen_for_speech_timeout(
                        timeout_seconds=int(timeout),
                        rms_callback=self.rms_updated.emit
                    )

                    if wav_path:
                        self.status_changed.emit("THINKING")
                        transcript = self.stt.transcribe(wav_path)
                        if transcript and transcript.strip():
                            logger.info(f"[Turn-Taking] Follow-up utterance captured: '{transcript.strip()}'")
                            self._turn_complete_event.clear()
                            self.speech_detected.emit(transcript.strip())
                            self._wait_for_turn_complete()
                        else:
                            logger.info(f"[Turn-Taking] {timeout}s window completed without speech. Returning to standby.")
                            self.status_changed.emit("STANDBY")
                    else:
                        logger.info(f"[Turn-Taking] {timeout}s window timed out (silence). Returning to standby.")
                        self.status_changed.emit("STANDBY")
                except Exception as e:
                    logger.error(f"[Turn-Taking Error] {e}")
                    self.status_changed.emit("STANDBY")
                continue

            # 2. Standard Ambient Wake-Word Listener Loop
            try:
                self.status_changed.emit("STANDBY")
                detected = self.listener.listen_for_wakeword(
                    rms_callback=self.rms_updated.emit
                )
                if detected and self.running and self.voice_enabled:
                    self.status_changed.emit("LISTENING")
                    wav_path = self.listener.record_phrase(
                        duration=10.0,
                        output_filename="temp_input.wav",
                        rms_callback=self.rms_updated.emit
                    )

                    self.status_changed.emit("THINKING")
                    transcript = self.stt.transcribe(wav_path)
                    if transcript and transcript.strip():
                        self._turn_complete_event.clear()
                        self.speech_detected.emit(transcript.strip())
                        self._wait_for_turn_complete()
            except Exception as e:
                logger.error(f"[VoiceListenerWorker Error] {e}")
                self.msleep(1000)

    def stop(self):
        self.running = False
        self._turn_complete_event.set()
        self.wait(1000)


class SystemBridge(QObject):
    """
    Routes events seamlessly between the PySide6 UI overlay and backend system engines via Orchestrator.
    """
    display_requested = Signal(str, str)  # (title, markdown_content)

    def __init__(self, overlay: JarvisOverlay, orchestrator: Optional[Orchestrator] = None):
        super().__init__()
        self.overlay = overlay
        self.orchestrator = orchestrator or Orchestrator()

        self.current_cmd_worker: Optional[CommandWorker] = None

        # Initialize background voice listener worker
        self.voice_worker = VoiceListenerWorker(self.orchestrator.listener, self.orchestrator.stt)
        self.voice_worker.status_changed.connect(self._on_worker_status_changed)
        self.voice_worker.speech_detected.connect(self._on_voice_speech_detected)
        self.voice_worker.rms_updated.connect(self.overlay.signals.audio_rms_updated.emit)

        # Connect overlay and display signals
        self.display_requested.connect(self.show_display_card)
        self.overlay.signals.display_card_requested.connect(self.show_display_card)
        self.overlay.signals.command_submitted.connect(self.submit_text_command)
        self.overlay.signals.voice_toggle_clicked.connect(self.toggle_voice_listener)
        self.overlay.signals.system_online_toggled.connect(self.toggle_system_online)

        # Start background voice listener
        self.voice_worker.start()
        self.overlay.signals.append_message.emit("J.A.R.V.I.S.", "System online and standing by, sir.")

        # Initialize OpenClaw Gateway Client if enabled
        if getattr(config, "ENABLE_OPENCLAW_GATEWAY", True):
            from gateway import OpenClawGatewayClient
            self.openclaw_client = OpenClawGatewayClient()
            self.openclaw_client.register_status_callback(self._on_openclaw_status_changed)
            self.openclaw_client.register_trigger_handler(self._on_openclaw_trigger_received)
            self.openclaw_client.start()
        else:
            self.openclaw_client = None

    @Slot(str, str)
    def show_display_card(self, title: str, content: str):
        """
        Instantiates and pops up DisplayCardModal on the main GUI thread.
        """
        from ui.display_card import DisplayCardModal
        logger.info(f"[SystemBridge] Displaying visual card '{title}'")
        modal = DisplayCardModal(title=title, markdown_content=content, parent=self.overlay)
        modal.show()

    @Slot(str)
    def submit_text_command(self, text: str):
        """
        Bypasses STT and feeds typed user input directly into the orchestrator pipeline.
        """
        if not text or not text.strip():
            return

        self.overlay.signals.append_message.emit("YOU", text.strip())
        self._process_command(text.strip())

    @Slot(bool)
    def toggle_voice_listener(self, enabled: bool):
        """
        Pauses or resumes background openWakeWord microphone listening.
        """
        self.voice_worker.voice_enabled = enabled
        if enabled:
            self.overlay.signals.update_status.emit("STANDBY")
            logger.info("[SystemBridge] Voice listener enabled.")
        else:
            self.overlay.signals.update_status.emit("STANDBY")
            logger.info("[SystemBridge] Voice listener paused.")

    @Slot(bool)
    def toggle_system_online(self, online: bool):
        """
        Toggles overall system Online / Offline state.
        When Offline: Mutes microphone and pauses wake-word engine.
        When Online: Activates wake-word listener.
        """
        self.voice_worker.voice_enabled = online
        if online:
            self.overlay.signals.update_status.emit("STANDBY")
            logger.info("[SystemBridge] System set ONLINE.")
        else:
            self.overlay.signals.update_status.emit("STANDBY")
            logger.info("[SystemBridge] System set OFFLINE (Voice muted).")

    def _on_voice_speech_detected(self, transcript: str):
        self.overlay.signals.append_message.emit("YOU", transcript)
        self._process_command(transcript)

    def _process_command(self, user_input: str):
        if self.current_cmd_worker and self.current_cmd_worker.isRunning():
            logger.warning("Another command is currently processing.")
            return

        def on_tts_complete():
            if getattr(config, "ENABLE_FOLLOW_UP_MODE", True) and self.voice_worker.voice_enabled:
                timeout = getattr(config, "FOLLOW_UP_LISTEN_TIMEOUT", 8)
                logger.info(f"[Turn-Taking] TTS speech output completed cleanly. Triggering {timeout}s post-reply follow-up mic window.")
                self.voice_worker.trigger_followup_listen(timeout=timeout)
            # Always signal turn completion, regardless of whether follow-up mode applies,
            # so the ambient listener thread (blocked in _wait_for_turn_complete()) knows
            # it's safe to resume -- either into the follow-up window above, or back into
            # normal wake-word listening.
            self.voice_worker.signal_turn_complete()

        self.current_cmd_worker = CommandWorker(
            user_input=user_input,
            orchestrator=self.orchestrator,
            on_complete_callback=on_tts_complete,
        )
        self.current_cmd_worker.status_changed.connect(self._on_worker_status_changed)
        self.current_cmd_worker.message_generated.connect(self._on_message_generated)
        self.current_cmd_worker.action_logged.connect(self._on_action_logged)
        self.current_cmd_worker.display_requested.connect(self.display_requested.emit)
        self.current_cmd_worker.response_generated.connect(self._on_response_generated)
        self.current_cmd_worker.finished_processing.connect(self._on_cmd_finished)
        self.current_cmd_worker.start()

    def _on_worker_status_changed(self, status: str):
        self.overlay.signals.update_status.emit(status)

    def _on_message_generated(self, sender: str, text: str):
        self.overlay.signals.append_message.emit(sender, text)

    def _on_action_logged(self, action_text: str):
        self.overlay.signals.add_recent_command.emit(action_text)

    def _on_response_generated(self, response_text: str):
        pass


    def _on_cmd_finished(self):
        self.current_cmd_worker = None

    def _on_openclaw_status_changed(self, status: str):
        val = "ONLINE" if status == "CONNECTED" else ("RECONNECTING" if status == "RECONNECTING" else "OFFLINE")
        logger.info(f"[Bridge] OpenClaw Gateway Status: {val}")
        if hasattr(self.overlay, "update_openclaw_status"):
            self.overlay.update_openclaw_status(status)
        self.overlay.signals.add_recent_command.emit(f"GATEWAY: {val}")

    def _on_openclaw_trigger_received(self, data: dict):
        if not data:
            return
        cmd_text = data.get("text") or data.get("trigger") or data.get("message") or data.get("command", "")
        if cmd_text and isinstance(cmd_text, str) and cmd_text.strip():
            logger.info(f"[Bridge] OpenClaw Inbound Trigger Received: '{cmd_text.strip()}'")
            self.overlay.signals.append_message.emit("OPENCLAW", cmd_text.strip())
            self._process_command(cmd_text.strip())

    def stop(self):
        """Stops background worker threads and cleans up resources."""
        if hasattr(self, 'openclaw_client') and self.openclaw_client:
            self.openclaw_client.stop()
        if hasattr(self, 'voice_worker') and self.voice_worker:
            self.voice_worker.stop()
