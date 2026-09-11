import os
import re
import shutil
import subprocess
import logging
from typing import Tuple, List, Dict
from safety import log_security_event

logger = logging.getLogger(__name__)

# Destructive keyword guard to prevent unsafe system actions
DESTRUCTIVE_KEYWORDS = [
    "rmdir", "del", "format", "reg", "bcdedit", "diskpart",
    "remove-item", "system32", "vssadmin", "wbadmin", "erase",
    "icacls", "takeown", "net user", "sfc /scannow"
]

# Standard fallback system utilities
COMMON_SYSTEM_EXES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "code": "code.cmd",
    "vscode": "code.cmd",
    "edge": "msedge.exe",
    "chrome": "chrome.exe",
}


def get_start_menu_shortcuts() -> Dict[str, str]:
    """
    Dynamically scans Windows Start Menu program directories for available .lnk shortcuts.

    Returns:
        Dict[str, str]: Map of lowercase shortcut name -> absolute file path.
    """
    search_dirs = [
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]

    shortcuts = {}
    for s_dir in search_dirs:
        if not os.path.exists(s_dir):
            continue
        for root, _, files in os.walk(s_dir):
            for file in files:
                if file.lower().endswith(".lnk"):
                    clean_name = file[:-4].strip().lower()
                    full_path = os.path.join(root, file)
                    shortcuts[clean_name] = full_path

    return shortcuts


def match_app_shortcut(app_name: str) -> Tuple[bool, str, str]:
    """
    Fuzzy matches the requested application name against discovered Start Menu shortcuts
    or system executables.

    Args:
        app_name (str): Friendly name of application requested by user.

    Returns:
        Tuple[bool, str, str]: (is_matched, launch_path, display_name)
    """
    query = app_name.strip().lower()
    shortcuts = get_start_menu_shortcuts()

    # 1. Exact match in Start Menu shortcuts
    if query in shortcuts:
        return True, shortcuts[query], query.title()

    # 2. Word token or substring match in Start Menu shortcuts
    for name, path in shortcuts.items():
        if query in name or name in query:
            return True, path, name.title()

    # 3. Fuzzy token overlap match
    query_tokens = set(re.findall(r'\w+', query))
    for name, path in shortcuts.items():
        name_tokens = set(re.findall(r'\w+', name))
        if query_tokens and query_tokens.issubset(name_tokens):
            return True, path, name.title()

    # 4. Check common system executables or PATH
    if query in COMMON_SYSTEM_EXES:
        exe_name = COMMON_SYSTEM_EXES[query]
        exe_path = shutil.which(exe_name) or exe_name
        return True, exe_path, query.title()

    exe_found = shutil.which(query)
    if exe_found:
        return True, exe_found, query.title()

    return False, "", ""


def open_application(app_name: str) -> str:
    """
    Dynamically launches an application by searching Windows Start Menu shortcuts
    or system PATH with destructive command protection.

    Args:
        app_name (str): Target application name.

    Returns:
        str: Status confirmation message for TTS output.
    """
    if not app_name or not app_name.strip():
        log_security_event("APP_EXEC", False, "Empty application name requested.")
        return "Please specify an application to open, sir."

    query_lower = app_name.strip().lower()

    # Destructive Command Rejection Guard
    if any(kw in query_lower for kw in DESTRUCTIVE_KEYWORDS):
        log_security_event("APP_EXEC", False, f"Refused destructive command in request: '{app_name}'")
        return f"I cannot launch {app_name} as it is flagged as a restricted system operation, sir."

    is_matched, launch_path, display_name = match_app_shortcut(app_name)

    if not is_matched:
        log_security_event("APP_EXEC", False, f"No application shortcut or executable found matching '{app_name}'")
        return f"I could not locate {app_name} on your system, sir."

    try:
        logger.info(f"[OpenApp] Launching '{display_name}' via path: {launch_path}")
        if launch_path.lower().endswith(".lnk"):
            os.startfile(launch_path)
        else:
            subprocess.Popen([launch_path], shell=True)

        log_security_event("APP_EXEC", True, f"Successfully launched '{display_name}' ({launch_path})")
        return f"Opened {display_name} successfully, sir."
    except Exception as e:
        logger.error(f"[OpenApp Error] Failed launching '{app_name}': {e}")
        log_security_event("APP_EXEC", False, f"Error launching '{app_name}': {e}")
        return f"I encountered an issue launching {app_name}, sir."


if __name__ == "__main__":
    print("[OpenApp Test]:", open_application("notepad"))
