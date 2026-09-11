import logging
from typing import Dict, Any, Optional, Callable
from tools.manager import REGISTERED_TOOLS, execute_registered_tool

logger = logging.getLogger(__name__)

# List of tool functions passed to Gemini API
JARVIS_TOOLS = REGISTERED_TOOLS


def execute_tool_call(
    function_name: str,
    function_args: Dict[str, Any],
    action_callback: Optional[Callable[[str], None]] = None,
    display_callback: Optional[Callable[[str, str], None]] = None,
) -> str:
    """
    Routes and executes function calls requested by the Gemini / LLM tools.
    """
    return execute_registered_tool(
        function_name=function_name,
        function_args=function_args,
        action_callback=action_callback,
        display_callback=display_callback,
    )
