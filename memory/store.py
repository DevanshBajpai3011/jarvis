"""
Memory Manager for context retrieval and LLM-driven automatic fact extraction.
"""

from memory.db import MemoryDB, add_memory, query_memories


class MemoryManager:
    """
    Manages context retrieval from ChromaDB and automatic fact extraction via OpenRouter / Gemini.
    """

    def __init__(self, db: MemoryDB = None, openrouter_brain=None):
        """
        Initializes MemoryManager with a MemoryDB instance and optional OpenRouterBrain instance.
        """
        self.db = db or MemoryDB()
        self._openrouter_brain = openrouter_brain

    @property
    def openrouter_brain(self):
        if self._openrouter_brain is None:
            try:
                from brain.openrouter_client import OpenRouterBrain
                self._openrouter_brain = OpenRouterBrain()
            except Exception:
                pass
        return self._openrouter_brain

    def get_relevant_context(self, user_input: str, n_results: int = 3) -> str:
        """
        Queries vector storage for facts relevant to user_input and returns formatted context string.

        Args:
            user_input (str): Input text query from user.
            n_results (int): Top N facts to retrieve (default 3).

        Returns:
            str: Formatted context string or empty string if no relevant memories exist.
        """
        if not user_input or not user_input.strip():
            return ""

        facts = self.db.query_memories(user_input, n_results=n_results)
        valid_facts = [f.strip() for f in facts if f and f.strip()]

        if not valid_facts:
            return ""

        formatted_facts = "\n".join([f"- {fact}" for fact in valid_facts])
        context_str = f"Known user context:\n{formatted_facts}"

        print(f"[Memory Context] Retrieved for prompt: '{user_input.strip()}' -> \n{context_str}", flush=True)
        return context_str

    def extract_and_remember(self, user_input: str, brain=None) -> str | None:
        """
        Uses OpenRouterBrain (or fallback Brain) to analyze user_input for long-term personal facts and stores them if found.

        Args:
            user_input (str): User statement or query.
            brain (Brain, optional): Fallback Brain instance for LLM inference.

        Returns:
            str | None: Extracted fact string if remembered, or None.
        """
        if not user_input or not user_input.strip():
            return None

        prompt = (
            f"Analyze the following user input: '{user_input.strip()}'\n"
            "Does this contain any personal facts, preferences, background details, or information about the user "
            "(e.g. name, exams, goals, study topics, drinks, hobbies, location)?\n"
            "If YES, reply ONLY with the extracted fact formatted as a short third-person sentence "
            "(e.g., 'User is studying for GATE ECE', 'User drinks oat milk coffee').\n"
            "If NO, reply strictly with 'NONE'."
        )

        try:
            result = None
            if self.openrouter_brain and self.openrouter_brain.client:
                result = self.openrouter_brain.think_background(prompt)

            if not result and brain:
                if hasattr(brain, "think_background"):
                    result = brain.think_background(prompt)
                elif hasattr(brain, "think"):
                    result = brain.think(prompt)

            if not result:
                return None

            cleaned_res = result.strip().split("\n")[0].strip()
            if cleaned_res.upper() == "NONE" or (cleaned_res.upper().startswith("NONE") and len(cleaned_res) < 10):
                return None

            fact = cleaned_res.lstrip("-*• ").strip("'\"")

            doc_id = self.db.add_memory(fact)
            print(f"[Memory Extractor] Extracted new fact: '{fact}'", flush=True)
            return fact
        except Exception as e:
            print(f"[MemoryManager Warning] Fact extraction failed: {e}", flush=True)
            return None


# Global singleton helper instance
_memory_manager_instance = None


def get_memory_manager() -> MemoryManager:
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager()
    return _memory_manager_instance


def get_relevant_context(user_input: str, n_results: int = 3) -> str:
    return get_memory_manager().get_relevant_context(user_input, n_results)


def extract_and_remember(user_input: str, brain) -> str | None:
    return get_memory_manager().extract_and_remember(user_input, brain)


if __name__ == "__main__":
    mm = MemoryManager()
    context = mm.get_relevant_context("What do I study?")
    print("[MemoryManager Test] Context output:")
    print(context)
