import logging
import threading
from typing import Callable, Optional, Generator

import config
from brain.primary_brain import PrimaryBrain
from brain.background_brain import BackgroundBrain

logger = logging.getLogger(__name__)


class BrainRouter:
    """
    Dual-Brain Router orchestrating Primary Streaming Voice Brain (Gemini 2.5 Flash)
    and Background Agent Brain (Meta Llama 3.3 70B via OpenRouter).
    Ensures sub-second voice audio synthesis while asynchronously running background evaluation tasks.
    """

    def __init__(self):
        self.primary_brain = PrimaryBrain()
        self.background_brain = BackgroundBrain()
        self.dual_brain_enabled = getattr(config, "ENABLE_DUAL_BRAIN", True)

    def stream_dialogue(
        self,
        user_prompt: str,
        context: str = "",
        image_path: str = None,
        action_callback: Optional[Callable[[str], None]] = None,
        display_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Generator[str, None, None]:
        """
        Routes incoming user prompt directly to Primary Streaming Brain for instant voice audio generation.

        Args:
            user_prompt (str): Input prompt from user.
            context (str): Memory context string.
            image_path (str): Visual analysis image path.
            action_callback (Callable): Action logging callback.
            display_callback (Callable): Visual display card callback.

        Yields:
            str: Streaming response text tokens.
        """
        logger.info("[BrainRouter] Routing dialogue query to Primary Voice Brain (Gemini 2.5 Flash)...")
        for chunk in self.primary_brain.stream_think(
            user_prompt=user_prompt,
            context=context,
            image_path=image_path,
            action_callback=action_callback,
            display_callback=display_callback,
        ):
            yield chunk

    def dispatch_background_task(
        self,
        prompt: str,
        system_instruction: str = "",
        callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Asynchronously dispatches background tasks (memory extraction, context summarization, self-healing checks)
        to Background Agent Brain (Llama 3.3 70B) on a detached daemon thread without delaying voice playback.

        Args:
            prompt (str): Background task query.
            system_instruction (str): Guidelines.
            callback (Callable, optional): Callback invoked with model response upon completion.
        """
        if not prompt or not prompt.strip():
            return

        def _worker():
            try:
                logger.info("[BrainRouter] Dispatching background task to Background Agent Brain (Llama 3.3 70B)...")
                res = self.background_brain.evaluate_background_task(prompt, system_instruction)
                if callback and res:
                    callback(res)
            except Exception as e:
                logger.error(f"[BrainRouter Background Error] {e}")

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def trigger_post_turn_cognitive_extraction(self, user_input: str, assistant_response: str):
        """
        Asynchronously triggers two-stage cognitive memory extraction after a conversation turn completes.
        Executes on a detached daemon thread with zero latency added to primary voice output.
        """
        if not getattr(config, "ENABLE_TWO_STAGE_MEMORY", True):
            return

        def _extraction_worker():
            try:
                from memory.extractor import CognitiveMemoryExtractor
                extractor = CognitiveMemoryExtractor(background_brain=self.background_brain)
                extracted_data = extractor.process_turn(user_input, assistant_response)
                if extracted_data:
                    logger.info(f"[BrainRouter Memory] Extracted fact: {extracted_data}")
            except Exception as e:
                logger.error(f"[BrainRouter Cognitive Memory Error] {e}")

        thread = threading.Thread(target=_extraction_worker, daemon=True)
        thread.start()

    def execute_tool_with_self_healing(self, action_name: str, params: dict, executor_func: Callable[[str, dict], Any]) -> Any:
        """
        Executes a tool call wrapped in a try...except loop connected directly to SelfHealer.
        If an exception occurs, triggers non-blocking vocal cue and attempts parameter patching/retry.
        """
        try:
            return executor_func(action_name, params)
        except Exception as err:
            import traceback
            tb_str = traceback.format_exc()
            logger.warning(f"[BrainRouter] Tool '{action_name}' failed: {err}. Initiating SelfHealer...")

            if getattr(config, "ENABLE_SELF_HEALING", True):
                from brain.healer import SelfHealer
                healer = SelfHealer(background_brain=self.background_brain)
                failed_step = {"action": action_name, "params": params}
                heal_res = healer.heal_and_retry(failed_step, tb_str, executor_func=executor_func)

                if heal_res.get("success"):
                    logger.info(f"[BrainRouter] SelfHealer successfully recovered tool '{action_name}'!")
                    return heal_res.get("result")

            raise err


if __name__ == "__main__":
    router = BrainRouter()
    print("[BrainRouter] Initialized successfully. Streaming primary dialogue test:")
    for chunk in router.stream_dialogue("Good evening J.A.R.V.I.S."):
        print(chunk, end="", flush=True)
    print()
