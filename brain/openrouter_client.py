from datetime import datetime
import config
from openai import OpenAI


class OpenRouterBrain:
    """
    Background LLM client wrapper using OpenRouter API and OpenAI SDK for non-voice processing tasks.
    """

    DEFAULT_FALLBACK_MODELS = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-lite-001:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
    ]

    def __init__(self, api_key: str = None, model_name: str = None):
        """
        Initializes OpenRouter client pointing to OpenRouter API endpoint.

        Args:
            api_key (str, optional): OpenRouter API key override.
            model_name (str, optional): OpenRouter model identifier override.
        """
        self.api_key = api_key or getattr(config, "OPENROUTER_API_KEY", "")
        self.model_name = model_name or getattr(config, "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

        self.client = None
        if self.api_key and self.api_key != "your_openrouter_api_key_here":
            try:
                self.client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.api_key,
                )
            except Exception:
                pass

    def think_background(self, prompt: str, system_instruction: str = "") -> str:
        """
        Sends background processing tasks (fact extraction, summarization, query parsing)
        to OpenRouter with silent fallbacks and dynamic real-time timestamp prepended.

        Args:
            prompt (str): Input prompt or task query.
            system_instruction (str, optional): System instructions for model behavior.

        Returns:
            str: Generated text response or empty string on failure.
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
            except Exception:
                continue

        return ""


if __name__ == "__main__":
    client = OpenRouterBrain()
    res = client.think_background("Reply with OK if online.")
    print("[OpenRouterBrain Test] Reply:", res)
