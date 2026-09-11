import os
import asyncio
import logging
from datetime import datetime
from openai import OpenAI

import config

logger = logging.getLogger(__name__)


class BackgroundBrain:
    """
    Background Agent Brain using OpenRouter / OpenAI SDK targeting Meta Llama 3.3 70B Instruct.
    Handles non-blocking background reasoning, memory extraction, intent evaluation, and error analysis completely
    decoupled from the primary voice response loop.
    """

    # Free-tier OpenRouter model availability rotates constantly — OpenRouter
    # deprecates or paywalls specific ":free" model slugs without warning. That is
    # exactly what happened to the three models previously hardcoded here (all three
    # started returning 404 "unavailable for free" errors). A live reachability test
    # on 2026-09-12 additionally found 8+ other well-known ":free" slugs also broken
    # the same way. "openrouter/free" is OpenRouter's own auto-router that always
    # selects from whatever free models are CURRENTLY available, and is deliberately
    # kept as the primary model for exactly this reason. Do NOT "fix" a future
    # failure here by hardcoding a fresh list of specific free model names without
    # understanding why that's precisely what broke last time — verify with a real
    # test call against the live OpenRouter catalog first.
    DEFAULT_FALLBACK_MODELS = [
        "openrouter/free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ]

    def __init__(self, api_key: str = None, model_name: str = None):
        self.api_key = api_key or getattr(config, "OPENROUTER_API_KEY", "")
        self.model_name = model_name or getattr(config, "BACKGROUND_MODEL", "openrouter/free")

        self.client = None
        if self.api_key and self.api_key != "your_openrouter_api_key_here":
            try:
                self.client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.api_key,
                )
            except Exception as e:
                logger.error(f"[BackgroundBrain] Failed to initialize OpenAI/OpenRouter client: {e}")

    def evaluate_background_task(self, prompt: str, system_instruction: str = "") -> str:
        """
        Synchronous execution helper for background evaluation tasks.

        Args:
            prompt (str): Task prompt or user statement.
            system_instruction (str): System instruction guidelines.

        Returns:
            str: Model output string or empty string on failure.
        """
        if not prompt or not prompt.strip():
            return ""

        if not self.client:
            return ""

        now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M:%S %p")
        timed_prompt = f"[System Time: {now_str}]\n{prompt.strip()}"

        messages = []
        if system_instruction and system_instruction.strip():
            messages.append({"role": "system", "content": system_instruction.strip()})
        messages.append({"role": "user", "content": timed_prompt})

        models_to_try = [self.model_name]
        for model in self.DEFAULT_FALLBACK_MODELS:
            if model not in models_to_try:
                models_to_try.append(model)

        for target_model in models_to_try:
            try:
                response = self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                )
                if response and response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    if content:
                        return content.strip()
            except Exception as ex:
                logger.warning(f"[BackgroundBrain] Model '{target_model}' evaluation failed: {ex}")
                continue

        return ""

    async def evaluate_background_task_async(self, prompt: str, system_instruction: str = "") -> str:
        """
        Async non-blocking wrapper for evaluate_background_task.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.evaluate_background_task, prompt, system_instruction)


if __name__ == "__main__":
    bb = BackgroundBrain()
    print("[BackgroundBrain] Test background evaluation...")
    res = bb.evaluate_background_task("Summarize: The user loves tea and lives in London.")
    print("Output:", res)
