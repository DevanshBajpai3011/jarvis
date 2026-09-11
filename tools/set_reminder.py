import os
import json
import datetime
import logging
from typing import List, Dict, Any
from safety.whitelist import ALLOWED_REMINDER_ACTIONS, log_security_event

logger = logging.getLogger(__name__)

REMINDERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reminders.json")


def _load_reminders() -> List[Dict[str, Any]]:
    if not os.path.exists(REMINDERS_FILE):
        return []
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read reminders file: {e}")
        return []


def _save_reminders(reminders: List[Dict[str, Any]]) -> bool:
    try:
        with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(reminders, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save reminders file: {e}")
        return False


def manage_reminder(action: str, reminder_text: str = "", time_str: str = "") -> str:
    """
    Manages user reminders by adding new entries or listing pending reminders.

    Args:
        action (str): Action to perform ('add', 'list', 'clear').
        reminder_text (str, optional): Content/description of the reminder.
        time_str (str, optional): Scheduled time or timestamp string for the reminder.

    Returns:
        str: Spoken confirmation message.
    """
    if not action or not action.strip():
        return "Please specify a reminder action, sir."

    clean_action = action.strip().lower()

    if clean_action not in ALLOWED_REMINDER_ACTIONS and clean_action != "clear":
        log_security_event("REMINDER_REJECTED", False, f"Invalid reminder action: '{action}'")
        return f"I cannot perform the reminder action '{action}', sir."

    reminders = _load_reminders()

    if clean_action == "add":
        if not reminder_text or not reminder_text.strip():
            return "Please provide details for the reminder, sir."

        new_entry = {
            "id": len(reminders) + 1,
            "text": reminder_text.strip(),
            "time": time_str.strip() if time_str else "Unspecified time",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        reminders.append(new_entry)
        if _save_reminders(reminders):
            log_security_event("REMINDER_ADD", True, f"Added reminder: '{reminder_text}'")
            if time_str:
                return f"Reminder set for {time_str}: '{reminder_text.strip()}', sir."
            return f"Reminder added: '{reminder_text.strip()}', sir."
        else:
            return "Failed to save reminder due to a file error, sir."

    elif clean_action == "list":
        if not reminders:
            return "You have no pending reminders, sir."

        reminder_lines = [f"{r['id']}. {r['text']} (Scheduled for: {r['time']})" for r in reminders]
        summary = "; ".join(reminder_lines)
        return f"Here are your pending reminders, sir: {summary}."

    elif clean_action in ("clear", "remove", "delete"):
        reminders.clear()
        _save_reminders(reminders)
        return "All reminders have been cleared, sir."

    return "Unknown reminder action, sir."
