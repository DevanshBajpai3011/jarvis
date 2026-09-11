import json
import re
import logging
from typing import List, Dict, Any
from brain.openrouter_client import OpenRouterBrain
from brain.llm import Brain

logger = logging.getLogger(__name__)


class TaskPlanner:
    """
    Decomposes multi-step user requests into structured JSON execution plans.
    """

    def __init__(self, openrouter_client: OpenRouterBrain = None, gemini_brain: Brain = None):
        self.openrouter = openrouter_client or OpenRouterBrain()
        self.gemini = gemini_brain or Brain()

    def decompose_goal(self, user_goal: str) -> List[Dict[str, Any]]:
        """
        Decomposes a complex user goal into a sequential list of structured step dicts.

        Args:
            user_goal (str): High-level task or objective specified by the user.

        Returns:
            List[Dict[str, Any]]: List of step dictionaries.
        """
        if not user_goal or not user_goal.strip():
            return []

        system_prompt = (
            "You are a task decomposition planner for J.A.R.V.I.S. "
            "Your objective is to break down a high-level user goal into a sequential JSON list of executable sub-tasks.\n\n"
            "Allowed tool actions and argument schemas:\n"
            "- 'open_app': {'app_name': string}\n"
            "- 'set_reminder': {'text': string, 'time': string}\n"
            "- 'run_script': {'script_name': string}\n"
            "- 'capture_screen': {'output_filename': string}\n"
            "- 'web_search': {'query': string}\n"
            "- 'speak': {'message': string}\n\n"
            "Format requirements:\n"
            "Return ONLY a valid JSON array of objects without markdown fences, where each object has:\n"
            "  'step' (int), 'action' (string), and 'args' (object).\n"
            "Example output:\n"
            "[\n"
            "  {\"step\": 1, \"action\": \"open_app\", \"args\": {\"app_name\": \"code\"}},\n"
            "  {\"step\": 2, \"action\": \"set_reminder\", \"args\": {\"text\": \"Review project\", \"time\": \"6pm\"}},\n"
            "  {\"step\": 3, \"action\": \"speak\", \"args\": {\"message\": \"Workspace setup complete, sir.\"}}\n"
            "]"
        )

        user_prompt = f"Decompose this goal into sub-tasks: \"{user_goal.strip()}\""

        raw_response = ""

        # Attempt decomposition with OpenRouter first to preserve Gemini voice quota
        try:
            raw_response = self.openrouter.think_background(user_prompt, system_instruction=system_prompt)
        except Exception as e:
            logger.warning(f"OpenRouter decomposition failed: {e}")

        # Fallback to Gemini if OpenRouter response is empty
        if not raw_response or not raw_response.strip():
            try:
                raw_response = self.gemini.think(f"{system_prompt}\n\n{user_prompt}")
            except Exception as e:
                logger.error(f"Gemini decomposition fallback failed: {e}")

        if not raw_response or not raw_response.strip():
            return self._fallback_plan(user_goal)

        # Parse JSON from response
        steps = self._parse_json_plan(raw_response)
        if steps:
            return steps

        # If JSON parsing failed, use fallback plan parser
        return self._fallback_plan(user_goal, raw_response)

    def _parse_json_plan(self, text: str) -> List[Dict[str, Any]]:
        cleaned = text.strip()

        # Remove markdown code block fences if present
        json_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", cleaned, re.IGNORECASE)
        if json_match:
            cleaned = json_match.group(1).strip()
        elif cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                valid_steps = []
                for i, item in enumerate(data, start=1):
                    if isinstance(item, dict) and "action" in item:
                        step_num = item.get("step", i)
                        action = str(item.get("action", "")).strip()
                        args = item.get("args", {})
                        if not isinstance(args, dict):
                            args = {}
                        valid_steps.append({
                            "step": step_num,
                            "action": action,
                            "args": args
                        })
                if valid_steps:
                    return valid_steps
        except Exception as e:
            logger.debug(f"JSON parsing error: {e}")

        return []

    def _fallback_plan(self, user_goal: str, raw_text: str = "") -> List[Dict[str, Any]]:
        """
        Creates a fallback plan if JSON parsing or LLM generation fails.
        """
        logger.info(f"Using fallback plan generator for goal: '{user_goal}'")
        goal_lower = user_goal.lower()

        steps = []
        step_counter = 1

        if any(kw in goal_lower for kw in ["code", "vscode", "editor"]):
            steps.append({"step": step_counter, "action": "open_app", "args": {"app_name": "code"}})
            step_counter += 1
        elif any(kw in goal_lower for kw in ["notepad", "note"]):
            steps.append({"step": step_counter, "action": "open_app", "args": {"app_name": "notepad"}})
            step_counter += 1
        elif any(kw in goal_lower for kw in ["calc", "calculator"]):
            steps.append({"step": step_counter, "action": "open_app", "args": {"app_name": "calc"}})
            step_counter += 1

        if "reminder" in goal_lower or "remind" in goal_lower:
            steps.append({"step": step_counter, "action": "set_reminder", "args": {"text": user_goal, "time": "unspecified"}})
            step_counter += 1

        if not steps:
            steps.append({
                "step": 1,
                "action": "speak",
                "args": {"message": f"Processing request: {user_goal}"}
            })

        return steps


class AgenticPlanner(TaskPlanner):
    """
    Agentic Planner decomposing multi-step tasks into structured JSON execution graphs:
    [{"step": 1, "action": "tool_name", "params": {...}}, ...]
    """

    def create_plan(self, user_goal: str) -> List[Dict[str, Any]]:
        steps = self.decompose_goal(user_goal)
        for s in steps:
            if "params" not in s and "args" in s:
                s["params"] = s["args"]
        return steps

