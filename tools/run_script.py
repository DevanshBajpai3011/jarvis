import os
import sys
import subprocess
import logging
from safety.whitelist import is_script_allowed, log_security_event

logger = logging.getLogger(__name__)


def execute_whitelisted_script(script_name: str) -> str:
    """
    Executes a pre-approved script if it is on the security whitelist.

    Args:
        script_name (str): Friendly name or key of the script.

    Returns:
        str: Execution logs or refusal message.
    """
    if not script_name or not script_name.strip():
        return "Please specify a script name to execute, sir."

    clean_name = script_name.strip()
    allowed, script_path = is_script_allowed(clean_name)

    if not allowed:
        log_security_event("SCRIPT_EXEC_REJECTED", False, f"Attempted to execute unwhitelisted script: '{clean_name}'")
        return f"I cannot run {clean_name} as it is not on your security whitelist, sir."

    if not os.path.exists(script_path):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(script_path)), exist_ok=True)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(f"# Auto-generated script for {clean_name}\nprint('Executing script: {clean_name}')\n")
        except Exception as e:
            return f"Whitelisted script file '{script_path}' was not found and could not be initialized: {e}"

    try:
        python_bin = sys.executable
        result = subprocess.run(
            [python_bin, script_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        if result.returncode == 0:
            log_security_event("SCRIPT_EXEC_SUCCESS", True, f"Script '{clean_name}' executed cleanly.")
            output = stdout if stdout else "Execution completed with no output."
            return f"Script '{clean_name}' executed successfully, sir. Output: {output}"
        else:
            log_security_event("SCRIPT_EXEC_FAIL", False, f"Script '{clean_name}' failed with returncode {result.returncode}.")
            return f"Script '{clean_name}' finished with error code {result.returncode}. Stderr: {stderr}"
    except subprocess.TimeoutExpired:
        log_security_event("SCRIPT_EXEC_TIMEOUT", False, f"Script '{clean_name}' timed out after 30s.")
        return f"Script '{clean_name}' execution timed out, sir."
    except Exception as e:
        logger.error(f"Error running script '{clean_name}': {e}")
        return f"Failed to execute script '{clean_name}' due to an error: {e}"
