import os
import logging
from datetime import datetime
from typing import Optional, Callable, Generator
from PIL import Image

import config
from google import genai
from google.genai import errors, types
from brain.persona import build_system_prompt
from brain.tools import JARVIS_TOOLS, execute_tool_call

logger = logging.getLogger(__name__)


class PrimaryBrain:
    """
    Primary Streaming Voice Brain targeting Gemini 2.5 Flash / Gemini 2.0 Flash.
    Optimized for sub-second streaming audio dialogue output with response_modalities=["TEXT"].
    """

    def __init__(self, api_key: str = None, model_name: str = None):
        self.api_key = api_key or getattr(config, "GEMINI_API_KEY", "")
        self.model_name = model_name or getattr(config, "PRIMARY_MODEL", "gemini-3.6-flash")

        self.client = None
        if self.api_key and self.api_key != "your_gemini_api_key_here":
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"[PrimaryBrain] Failed to initialize Gemini Client: {e}")

    def stream_think(
        self,
        user_prompt: str,
        context: str = "",
        image_path: str = None,
        action_callback: Optional[Callable[[str], None]] = None,
        display_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Generator[str, None, None]:
        """
        Streams response text chunks from primary Gemini model for sub-second audio output.

        Args:
            user_prompt (str): Input prompt.
            context (str): Memory or context string.
            image_path (str): Optional image path.
            action_callback (Callable): Callback for tool actions.
            display_callback (Callable): Callback for visual cards.

        Yields:
            str: Response text chunks.
        """
        fallback_msg = "I am having trouble connecting to my central primary brain, sir."
        if not user_prompt or not user_prompt.strip():
            if not image_path:
                yield "I am at your service, sir."
                return
            user_prompt = "Describe this image."

        if not self.client:
            yield fallback_msg
            return

        img_obj = None
        if image_path and os.path.exists(image_path):
            try:
                img_obj = Image.open(image_path)
            except Exception:
                pass

        base_prompt = build_system_prompt(user_prompt)
        system_instruction = f"{base_prompt}\n\n{context.strip()}" if context and context.strip() else base_prompt

        config_obj = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=JARVIS_TOOLS,
            response_modalities=["TEXT"],
        )

        now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M:%S %p")
        timed_prompt = f"[System Time: {now_str}]\n{user_prompt.strip()}"

        contents = [img_obj, timed_prompt] if img_obj is not None else timed_prompt

        models_to_try = [self.model_name, "gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-2.0-flash-lite"]

        try:
            for target_model in models_to_try:
                try:
                    response_stream = self.client.models.generate_content_stream(
                        model=target_model,
                        contents=contents,
                        config=config_obj,
                    )

                    has_yielded = False
                    for chunk in response_stream:
                        # Check function calls
                        function_calls = getattr(chunk, "function_calls", None)
                        if function_calls:
                            for call in function_calls:
                                func_name = getattr(call, "name", "")
                                func_args = dict(getattr(call, "args", {}))
                                tool_result = execute_tool_call(
                                    func_name,
                                    func_args,
                                    action_callback=action_callback,
                                    display_callback=display_callback,
                                )
                                followup_prompt = (
                                    f"{timed_prompt}\n\n[Tool '{func_name}' executed. Output: \"{tool_result}\"]\n"
                                    "Synthesize a concise, natural, polite spoken J.A.R.V.I.S. response."
                                )
                                followup_stream = self.client.models.generate_content_stream(
                                    model=target_model,
                                    contents=followup_prompt,
                                    config=types.GenerateContentConfig(
                                        system_instruction=system_instruction,
                                        response_modalities=["TEXT"],
                                    ),
                                )
                                for f_chunk in followup_stream:
                                    if f_chunk and f_chunk.text:
                                        yield f_chunk.text
                                return

                        if chunk and chunk.text:
                            has_yielded = True
                            yield chunk.text

                    if has_yielded:
                        return

                    # KNOWN ISSUE: Gemini 3.x streaming (generate_content_stream) can return a
                    # fully empty response (finish_reason=STOP, no exception, no text, no
                    # function_call) when `tools` is combined with `system_instruction` and/or
                    # `response_modalities` on the same request. Confirmed via live testing
                    # (Sept 2026) against gemini-3.6-flash; not seen on gemini-3.1-flash-lite
                    # under the identical config. This is a known issue across Gemini 3.x with
                    # streaming + function calling (multiple public reports), with no fix from
                    # Google as of Sept 2026. The documented workaround is to redo the same
                    # request non-streaming. Do NOT remove this retry as "redundant" -- without
                    # it, this exact request shape silently falls through the entire model
                    # fallback chain to the generic hardcoded error message. See BUGS.md.
                    logger.warning(
                        f"[PrimaryBrain] Model '{target_model}' streaming returned empty with "
                        "tools active -- retrying non-streaming per known Gemini 3.x limitation."
                    )
                    retry_text = self._non_streaming_retry(
                        target_model,
                        contents,
                        system_instruction,
                        timed_prompt,
                        action_callback,
                        display_callback,
                    )
                    if retry_text:
                        yield retry_text
                        return

                    logger.warning(
                        f"[PrimaryBrain] Model '{target_model}' non-streaming retry also "
                        "returned empty -- treating as a genuine failure, trying next model."
                    )
                except Exception as ex:
                    logger.warning(f"[PrimaryBrain] Model '{target_model}' stream failed: {ex}")
                    continue

            yield fallback_msg

        finally:
            if img_obj is not None:
                try:
                    img_obj.close()
                except Exception:
                    pass

    def _non_streaming_retry(
        self,
        target_model: str,
        contents,
        system_instruction: str,
        timed_prompt: str,
        action_callback: Optional[Callable[[str], None]],
        display_callback: Optional[Callable[[str, str], None]],
    ) -> Optional[str]:
        """
        Non-streaming fallback for the known Gemini 3.x empty-stream bug (see stream_think).
        Redoes the same request via generate_content() -- same model, same tools, same
        system_instruction/context -- and runs any resulting function call through the same
        tool-execution + follow-up synthesis pattern as brain/llm.py's Brain.think().

        Returns the final response text, or None if the retry is also empty/fails.
        """
        try:
            response = self.client.models.generate_content(
                model=target_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=JARVIS_TOOLS,
                    response_modalities=["TEXT"],
                ),
            )
        except Exception as ex:
            logger.warning(f"[PrimaryBrain] Model '{target_model}' non-streaming retry raised: {ex}")
            return None

        function_calls = getattr(response, "function_calls", None)
        if not function_calls and response and response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            if function_calls is None:
                                function_calls = []
                            function_calls.append(part.function_call)

        if function_calls:
            call = function_calls[0]
            func_name = getattr(call, "name", "")
            func_args = getattr(call, "args", {})
            func_args_dict = dict(func_args) if isinstance(func_args, dict) or hasattr(func_args, "items") else {}

            tool_result = execute_tool_call(
                func_name,
                func_args_dict,
                action_callback=action_callback,
                display_callback=display_callback,
            )
            followup_prompt = (
                f"{timed_prompt}\n\n[Tool '{func_name}' executed. Output: \"{tool_result}\"]\n"
                "Synthesize a concise, natural, polite spoken J.A.R.V.I.S. response."
            )
            try:
                followup_response = self.client.models.generate_content(
                    model=target_model,
                    contents=followup_prompt,
                    config=types.GenerateContentConfig(system_instruction=system_instruction),
                )
            except Exception as ex:
                logger.warning(f"[PrimaryBrain] Model '{target_model}' non-streaming followup raised: {ex}")
                return tool_result
            if followup_response and followup_response.text:
                return followup_response.text.strip()
            return tool_result

        if response and response.text:
            return response.text.strip()
        return None


if __name__ == "__main__":
    pb = PrimaryBrain()
    print("[PrimaryBrain] Test stream output:")
    for chunk in pb.stream_think("Good morning J.A.R.V.I.S."):
        print(chunk, end="", flush=True)
    print()
