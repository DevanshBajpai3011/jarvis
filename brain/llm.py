import os
from datetime import datetime
from typing import Optional, Callable
import config
from google import genai
from google.genai import errors, types
from brain.persona import JARVIS_SYSTEM_PROMPT, build_system_prompt
from brain.tools import JARVIS_TOOLS, execute_tool_call
from PIL import Image


class Brain:
    """
    LLM interaction engine using the official google-genai SDK with multimodal and tool-calling support.
    """

    def __init__(self, api_key: str = None, model_name: str = None):
        """
        Initializes the Gemini client using config settings.

        Args:
            api_key (str, optional): Gemini API key override.
            model_name (str, optional): Model identifier override.
        """
        self.api_key = api_key or getattr(config, "GEMINI_API_KEY", "")
        self.model_name = model_name or getattr(config, "DEFAULT_MODEL", "gemini-3.6-flash")

        self.client = None
        if self.api_key and self.api_key != "your_gemini_api_key_here":
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[Brain Error] Failed to initialize Gemini Client: {e}")

    def think(
        self,
        user_prompt: str,
        context: str = "",
        image_path: str = None,
        action_callback: Optional[Callable[[str], None]] = None,
        display_callback: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        """
        Processes user prompt with J.A.R.V.I.S. system instructions, recalled context, tool declarations,
        and optional image input using Gemini LLM. Prepends dynamic real-time timestamp.

        Args:
            user_prompt (str): Input text query from user.
            context (str, optional): Relevant memories/context retrieved from memory store.
            image_path (str, optional): Path to an image file to attach for visual analysis.
            action_callback (Callable, optional): Callback to log executed tool actions.

        Returns:
            str: Generated response text or fallback error message.
        """
        fallback_msg = "I am having trouble connecting to my central servers at the moment, sir."
        image_fallback_msg = "I encountered an issue processing the visual input, sir."

        if not user_prompt or not user_prompt.strip():
            if not image_path:
                return "I am at your service, sir."
            user_prompt = "Describe this image."

        if not self.client:
            print("[Brain Warning] Gemini API client is uninitialized or missing API key.")
            return fallback_msg

        img_obj = None
        if image_path:
            if not os.path.exists(image_path):
                print(f"[Brain Warning] Specified image file not found: {image_path}")
                return image_fallback_msg
            try:
                img_obj = Image.open(image_path)
            except Exception as e:
                print(f"[Brain Error] Failed to open image file '{image_path}': {e}")
                return image_fallback_msg

        base_prompt = build_system_prompt(user_prompt)
        system_instruction = base_prompt
        if context and context.strip():
            system_instruction = f"{base_prompt}\n\n{context.strip()}"

        config_obj = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=JARVIS_TOOLS,
            # AFC bypasses execute_tool_call()/execute_registered_tool(), which is
            # where action_callback/display_callback UI side-effects actually fire
            # (display_content() itself is a no-op stub). Disabling AFC restores
            # this codebase's own manual dispatch as the real execution path.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M:%S %p")
        timed_prompt = f"[System Time: {now_str}]\n{user_prompt.strip()}"

        if img_obj is not None:
            contents = [img_obj, timed_prompt]
        else:
            contents = timed_prompt

        models_to_try = [self.model_name]
        for fallback in ["gemini-flash-latest", "gemini-3.1-flash-lite", "gemini-2.0-flash-lite", "gemini-3.6-flash"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        collected_errors = []
        try:
            for target_model in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=target_model,
                        contents=contents,
                        config=config_obj,
                    )

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
                        for call in function_calls:
                            func_name = getattr(call, "name", "")
                            func_args = getattr(call, "args", {})
                            if isinstance(func_args, dict) or hasattr(func_args, "items"):
                                func_args_dict = dict(func_args)
                            else:
                                func_args_dict = {}

                            tool_result = execute_tool_call(
                                func_name,
                                func_args_dict,
                                action_callback=action_callback,
                                display_callback=display_callback,
                            )

                            followup_prompt = (
                                f"{timed_prompt}\n\n"
                                f"[System Note: Tool '{func_name}' was executed. Output: \"{tool_result}\"]\n"
                                f"Synthesize a concise, natural, polite spoken J.A.R.V.I.S. response."
                            )
                            followup_response = self.client.models.generate_content(
                                model=target_model,
                                contents=followup_prompt,
                                config=types.GenerateContentConfig(system_instruction=system_instruction)
                            )
                            if followup_response and followup_response.text:
                                return followup_response.text.strip()
                            return tool_result

                    if response and response.text:
                        return response.text.strip()

                except (errors.APIError, Exception) as e:
                    collected_errors.append(f"{target_model}: {e}")
                    continue

            error_summary = "; ".join(collected_errors) if collected_errors else "Unknown error"
            print(f"[Brain Error] All Gemini API model attempts failed. Details: {error_summary}", flush=True)
            return fallback_msg
        finally:
            if img_obj is not None:
                try:
                    img_obj.close()
                except Exception:
                    pass


if __name__ == "__main__":
    brain = Brain()
    print("[Brain] System test:")
    reply = brain.think("Hello Jarvis, introduce yourself.")
    print(f"JARVIS: {reply}")
