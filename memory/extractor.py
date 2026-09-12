import json
import logging
import re
from typing import Optional, Dict

import config
from memory.db import add_memory

logger = logging.getLogger(__name__)


class CognitiveMemoryExtractor:
    """
    Two-Stage Cognitive Memory Extractor.
    Stage 1: Fast filtering check via BackgroundBrain to evaluate if turn contains long-term facts.
    Stage 2: Structured JSON extraction categorizing facts into identity, preferences, projects, or relationships.
    """

    CATEGORIES = ["identity", "preferences", "projects", "relationships"]

    def __init__(self, background_brain=None):
        self.background_brain = background_brain

    def _get_background_brain(self):
        if self.background_brain is None:
            try:
                from brain.background_brain import BackgroundBrain
                self.background_brain = BackgroundBrain()
            except Exception as e:
                logger.error(f"[CognitiveMemoryExtractor] Failed to load BackgroundBrain: {e}")
        return self.background_brain

    def should_extract_memory(self, user_input: str, assistant_response: str) -> bool:
        """
        Stage 1 Filter: Evaluates if conversation turn contains long-term personal facts.
        """
        if not user_input or not user_input.strip():
            return False

        brain = self._get_background_brain()
        if not brain:
            return False

        prompt = (
            f"Analyze this conversation turn:\n"
            f"User: '{user_input.strip()}'\n"
            f"Assistant: '{assistant_response.strip()}'\n\n"
            f"Does this turn contain permanent personal details, user preferences, active project updates, or relationships?\n"
            f"Only extract facts explicitly stated by the User. Never extract information from the "
            f"Assistant's own response, apologies, or error messages as if they were facts about the user.\n"
            f"Reply strictly YES or NO."
        )

        try:
            res = brain.evaluate_background_task(prompt)
            if res and "YES" in res.upper():
                return True
            return False
        except Exception as e:
            logger.warning(f"[CognitiveMemoryExtractor Stage 1 Error] {e}")
            return False

    def extract_memory(self, user_input: str, assistant_response: str) -> Optional[dict]:
        """
        Stage 2 Extraction: Parses structured JSON fact and saves directly to persistent vector storage.
        """
        brain = self._get_background_brain()
        if not brain:
            return None

        prompt = (
            f"Extract the long-term fact from this turn in strict JSON format:\n"
            f'{{"category": "identity|preferences|projects|relationships", "fact": "Extracted core fact string"}}\n\n'
            f"User: '{user_input.strip()}'\n"
            f"Assistant: '{assistant_response.strip()}'\n\n"
            f"Only extract facts explicitly stated by the User. Never extract information from the "
            f"Assistant's own response, apologies, or error messages as if they were facts about the user.\n"
            f"Reply ONLY with the raw valid JSON object."
        )

        try:
            res = brain.evaluate_background_task(prompt)
            if not res or not res.strip():
                return None

            cleaned_json = res.strip()
            # Remove potential markdown code fences ```json ... ```
            cleaned_json = re.sub(r"```[a-zA-Z]*", "", cleaned_json).strip("` \n")

            match = re.search(r"\{.*\}", cleaned_json, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                category = data.get("category", "preferences").lower().strip()
                if category not in self.CATEGORIES:
                    category = "preferences"
                fact = data.get("fact", "").strip()

                if fact:
                    doc_id = add_memory(fact=fact, category=category)
                    logger.info(f"[CognitiveMemoryExtractor] Memory stored [{doc_id[:8]}]: [{category}] {fact}")
                    return {"id": doc_id, "category": category, "fact": fact}
            return None
        except Exception as e:
            logger.warning(f"[CognitiveMemoryExtractor Stage 2 Error] {e}")
            return None

    def process_turn(self, user_input: str, assistant_response: str) -> Optional[dict]:
        """
        Executes full two-stage cognitive memory workflow.
        """
        if not getattr(config, "ENABLE_TWO_STAGE_MEMORY", True):
            return None

        if self.should_extract_memory(user_input, assistant_response):
            return self.extract_memory(user_input, assistant_response)
        return None


if __name__ == "__main__":
    extractor = CognitiveMemoryExtractor()
    print("[CognitiveMemoryExtractor] Initialized cleanly.")
