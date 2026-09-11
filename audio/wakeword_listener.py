import logging
from typing import Optional, Callable
import config

logger = logging.getLogger(__name__)


def get_wakeword_listener(model_name: str = None, threshold: float = None, on_wake_callback: Optional[Callable[[], None]] = None):
    """Factory helper to obtain a WakeWordListener without top-level circular imports."""
    from wakeword.listener import WakeWordListener
    target_model = model_name or getattr(config, "WAKEWORD_NAME", "jarvis")
    target_threshold = threshold if threshold is not None else getattr(config, "WAKEWORD_THRESHOLD", 0.4)
    return WakeWordListener(model_name=target_model, threshold=target_threshold, on_wake_callback=on_wake_callback)


class SingleWordWakeWordListener:
    """
    Single-word 'jarvis' activation wake word listener wrapper.
    """

    def __init__(self, model_name: str = None, threshold: float = None, on_wake_callback: Optional[Callable[[], None]] = None):
        self._listener = get_wakeword_listener(model_name=model_name, threshold=threshold, on_wake_callback=on_wake_callback)

    def __getattr__(self, name):
        return getattr(self._listener, name)


__all__ = ["SingleWordWakeWordListener", "get_wakeword_listener"]


if __name__ == "__main__":
    listener = SingleWordWakeWordListener()
    print(f"[SingleWordWakeWordListener] Loaded model '{listener.model_name}' threshold={listener.threshold}.")
