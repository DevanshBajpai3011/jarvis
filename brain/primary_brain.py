import os
import json
import logging
from datetime import datetime
from typing import Optional, Callable, Generator, Dict, List
from PIL import Image

import config
from google import genai
from google.genai import errors, types
from brain.persona import build_system_prompt
from brain.tools import JARVIS_TOOLS, execute_tool_call

logger = logging.getLogger(__name__)

# Caps chained tool calls within a single turn (mirrors google-genai AFC's own
# default `maximum_remote_calls`). Manual dispatch needs its own cap now that
# AFC is disabled (BUGS.md Bug #15) -- without one, a model stuck requesting
# tools forever would loop indefinitely.
MAX_TOOL_ITERATIONS = 10

CHAIN_CAPPED_MSG = (
    "I attempted that, sir, but it required more steps than I could safely "
    "complete in one go. I wasn't able to finish it."
)


def _tool_call_signature(func_name: str, func_args: dict) -> str:
    """
    Canonical, argument-order-independent identity for a tool call, used for
    exact-match dedup against calls already executed this turn (BUGS.md Bug #17).
    Two calls only collide if both the name AND every argument value match --
    a genuinely different second call to the same tool (e.g. a second reminder
    with different text) gets its own signature and executes normally.
    """
    try:
        args_json = json.dumps(func_args, sort_keys=True, default=str)
    except Exception:
        args_json = str(sorted(func_args.items()))
    return f"{func_name}::{args_json}"


def _execute_tool_with_dedup(
    func_name: str,
    func_args: dict,
    tool_history: List[str],
    executed_calls: Dict[str, str],
    action_callback: Optional[Callable[[str], None]],
    display_callback: Optional[Callable[[str, str], None]],
) -> str:
    """
    Executes a tool call while tracking it in turn-level tool_history/executed_calls
    (BUGS.md Bug #17). tool_history lets a model-fallback transition see what
    already ran this turn instead of starting blind; executed_calls catches an
    exact replay (same name, same arguments) of a call already made this turn and
    reuses its result instead of re-running it -- skipping action_callback/
    display_callback too, so UI narration doesn't double-fire either.
    """
    signature = _tool_call_signature(func_name, func_args)
    if signature in executed_calls:
        tool_result = executed_calls[signature]
        logger.info(
            f"[PrimaryBrain] Skipping re-execution of '{func_name}' -- exact same "
            "arguments already executed earlier this turn; reusing that result."
        )
        tool_history.append(
            f"[Tool '{func_name}' was already executed earlier this turn with "
            f"these exact arguments -- reusing that result instead of running it "
            f"again. Output: \"{tool_result}\"]"
        )
        return tool_result

    tool_result = execute_tool_call(
        func_name,
        func_args,
        action_callback=action_callback,
        display_callback=display_callback,
    )
    executed_calls[signature] = tool_result
    tool_history.append(f"[Tool '{func_name}' executed. Output: \"{tool_result}\"]")
    return tool_result


def _build_contents_with_history(timed_prompt: str, tool_history: List[str]) -> str:
    """
    Builds the follow-up prompt from everything executed so far this turn.
    Shared by stream_think() and _non_streaming_retry() so a model-fallback
    transition mid-turn (BUGS.md Bug #17) sees the same accumulated context
    regardless of which path produced it.
    """
    return (
        f"{timed_prompt}\n\n" + "\n\n".join(tool_history) +
        "\n\nIf this fully answers the request, synthesize a concise, "
        "natural, polite spoken J.A.R.V.I.S. response now -- never claim "
        "an action succeeded if the tool output above shows it did not. "
        "If another tool call is genuinely still needed to finish the "
        "request, call it."
    )


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
            # AFC bypasses execute_tool_call()/execute_registered_tool(), which is
            # where action_callback/display_callback UI side-effects actually fire
            # (display_content() itself is a no-op stub). Disabling AFC restores
            # this codebase's own manual dispatch as the real execution path.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M:%S %p")
        timed_prompt = f"[System Time: {now_str}]\n{user_prompt.strip()}"

        contents = [img_obj, timed_prompt] if img_obj is not None else timed_prompt

        models_to_try = [self.model_name, "gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-2.0-flash-lite"]

        # Turn-level (not per-model) so a model-fallback transition doesn't lose
        # track of tools already executed under a previous, abandoned model
        # attempt in this same turn (BUGS.md Bug #17). executed_calls additionally
        # catches an exact replay (same name + same arguments) and skips
        # re-execution entirely rather than just informing the next model about it.
        tool_history: List[str] = []
        executed_calls: Dict[str, str] = {}

        try:
            for target_model in models_to_try:
                try:
                    next_contents = contents if not tool_history else _build_contents_with_history(timed_prompt, tool_history)
                    next_config = config_obj
                    has_yielded = False
                    chain_capped = False

                    for iteration in range(MAX_TOOL_ITERATIONS):
                        response_stream = self.client.models.generate_content_stream(
                            model=target_model,
                            contents=next_contents,
                            config=next_config,
                        )

                        function_call_this_round = None
                        has_yielded_this_round = False
                        for chunk in response_stream:
                            function_calls = getattr(chunk, "function_calls", None)
                            if function_calls:
                                function_call_this_round = function_calls[0]
                                break

                            if chunk and chunk.text:
                                has_yielded_this_round = True
                                has_yielded = True
                                yield chunk.text

                        if function_call_this_round is None:
                            if has_yielded_this_round:
                                return
                            # Genuinely empty this round -- fall through to the
                            # known-bug retry logic below (unchanged). next_contents
                            # already reflects tool_history as of just before this
                            # round, so the non-streaming retry sees the identical
                            # request, including anything executed earlier this turn.
                            break

                        func_name = getattr(function_call_this_round, "name", "")
                        func_args = dict(getattr(function_call_this_round, "args", {}))
                        _execute_tool_with_dedup(
                            func_name,
                            func_args,
                            tool_history,
                            executed_calls,
                            action_callback,
                            display_callback,
                        )
                        next_contents = _build_contents_with_history(timed_prompt, tool_history)
                        next_config = types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=JARVIS_TOOLS,
                            response_modalities=["TEXT"],
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                        )
                    else:
                        chain_capped = True

                    if chain_capped:
                        logger.warning(
                            f"[PrimaryBrain] Model '{target_model}' requested more than "
                            f"{MAX_TOOL_ITERATIONS} chained tool calls in one turn -- "
                            "stopping and reporting honestly instead of guessing at completion."
                        )
                        yield CHAIN_CAPPED_MSG
                        return

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
                        next_contents,
                        system_instruction,
                        timed_prompt,
                        action_callback,
                        display_callback,
                        tool_history,
                        executed_calls,
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
        tool_history: List[str],
        executed_calls: Dict[str, str],
    ) -> Optional[str]:
        """
        Non-streaming fallback for the known Gemini 3.x empty-stream bug (see stream_think).
        Redoes the same request via generate_content() -- same model, same tools, same
        system_instruction/context -- and runs any resulting function call through the same
        tool-execution + follow-up synthesis pattern as brain/llm.py's Brain.think().

        Supports chained tool calls (capped at MAX_TOOL_ITERATIONS, mirroring the
        streaming path and google-genai AFC's own default budget) -- if the model
        requests another tool after seeing the first tool's result, it is executed
        too, and so on, before a final answer is returned.

        tool_history/executed_calls are the SAME turn-level objects stream_think()
        uses -- passed by reference and mutated in place (BUGS.md Bug #17), not
        copied, so (a) if this retry executes a tool and then still fails/returns
        None, whatever it ran is still visible to stream_think() for the next
        model in its fallback chain, and (b) an exact-repeat call already executed
        earlier this turn -- by this retry or any prior model attempt -- is
        reused instead of re-run.

        Returns the final response text, or None if the retry is also empty/fails.
        """
        next_contents = contents

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = self.client.models.generate_content(
                    model=target_model,
                    contents=next_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=JARVIS_TOOLS,
                        response_modalities=["TEXT"],
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
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

            if not function_calls:
                if response and response.text:
                    return response.text.strip()
                return None

            call = function_calls[0]
            func_name = getattr(call, "name", "")
            func_args = getattr(call, "args", {})
            func_args_dict = dict(func_args) if isinstance(func_args, dict) or hasattr(func_args, "items") else {}

            _execute_tool_with_dedup(
                func_name,
                func_args_dict,
                tool_history,
                executed_calls,
                action_callback,
                display_callback,
            )
            next_contents = _build_contents_with_history(timed_prompt, tool_history)

        logger.warning(
            f"[PrimaryBrain] Model '{target_model}' (non-streaming retry) requested "
            f"more than {MAX_TOOL_ITERATIONS} chained tool calls in one turn -- "
            "stopping and reporting honestly instead of guessing at completion."
        )
        return CHAIN_CAPPED_MSG


if __name__ == "__main__":
    pb = PrimaryBrain()
    print("[PrimaryBrain] Test stream output:")
    for chunk in pb.stream_think("Good morning J.A.R.V.I.S."):
        print(chunk, end="", flush=True)
    print()
