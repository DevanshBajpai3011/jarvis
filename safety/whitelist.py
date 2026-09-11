import os
import datetime
import logging
from typing import Tuple, Dict, Set

logger = logging.getLogger(__name__)

LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, "security.log")

# Pre-approved application whitelist
ALLOWED_APPS: Dict[str, str] = {
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "code": "code",
    "vscode": "code",
    "browser": "chrome",
    "chrome": "chrome",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
}

# Pre-approved script whitelist
ALLOWED_SCRIPTS: Dict[str, str] = {
    "clean_temp": "scripts/clean_temp.py",
    "backup": "scripts/backup.py",
    "system_info": "scripts/system_info.py",
}

# Permitted reminder actions
ALLOWED_REMINDER_ACTIONS: Set[str] = {"add", "list", "remove", "delete"}


def log_security_event(action: str, allowed: bool, details: str) -> None:
    """
    Appends a security audit log event to safety/security.log.
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        status = "ALLOWED" if allowed else "DENIED"
        log_entry = f"[{timestamp}] [{status}] Action: {action} | Details: {details}\n"

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"Failed writing to security log: {e}")


def is_app_allowed(app_name: str) -> Tuple[bool, str]:
    """
    Checks whether an application is whitelisted for execution.

    Args:
        app_name (str): Friendly name or key of the application.

    Returns:
        Tuple[bool, str]: (True, executable_path) if whitelisted, otherwise (False, "").
    """
    if not app_name:
        log_security_event("APP_EXEC", False, "Empty app name provided.")
        return False, ""

    key = app_name.strip().lower()
    if key in ALLOWED_APPS:
        exe_path = ALLOWED_APPS[key]
        log_security_event("APP_EXEC", True, f"App '{app_name}' matched executable '{exe_path}'")
        return True, exe_path

    log_security_event("APP_EXEC", False, f"App '{app_name}' is not in ALLOWED_APPS whitelist.")
    return False, ""


def is_script_allowed(script_name: str) -> Tuple[bool, str]:
    """
    Checks whether a script is whitelisted for execution.

    Args:
        script_name (str): Friendly name or key of the script.

    Returns:
        Tuple[bool, str]: (True, script_path) if whitelisted, otherwise (False, "").
    """
    if not script_name:
        log_security_event("SCRIPT_EXEC", False, "Empty script name provided.")
        return False, ""

    key = script_name.strip().lower()
    if key in ALLOWED_SCRIPTS:
        script_path = ALLOWED_SCRIPTS[key]
        log_security_event("SCRIPT_EXEC", True, f"Script '{script_name}' matched path '{script_path}'")
        return True, script_path

    log_security_event("SCRIPT_EXEC", False, f"Script '{script_name}' is not in ALLOWED_SCRIPTS whitelist.")
    return False, ""
