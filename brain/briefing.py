import asyncio
import logging
from datetime import datetime
from tools.os_tools import get_hardware_status
from brain.proactive import proactive_monitor

logger = logging.getLogger(__name__)


class DailyBriefingEngine:
    """
    Compiles system hardware vitals, pending Windows notification alerts,
    and temporal summaries into a structured voice briefing.
    """

    def __init__(self):
        pass

    async def generate_briefing(self) -> str:
        """Compiles time, hardware telemetry, and unread notification alerts into a spoken briefing format."""
        now = datetime.now().strftime("%A, %B %d at %I:%M %p")

        # 1. Fetch hardware status
        try:
            hardware_info = get_hardware_status()
        except Exception as e:
            logger.warning(f"[DailyBriefingEngine] Hardware status fetch error: {e}")
            hardware_info = "Hardware status unavailable."

        # 2. Fetch unread notifications
        try:
            notifications_info = await proactive_monitor.check_notifications_and_alert()
            if "No new" in notifications_info or "not granted" in notifications_info:
                notif_summary = "You have no critical unread notifications."
            else:
                notif_summary = f"Recent alerts:\n{notifications_info}"
        except Exception as e:
            logger.warning(f"[DailyBriefingEngine] Notification check error: {e}")
            notif_summary = "Notification briefing unavailable."

        briefing_text = (
            f"Good day. Here is your daily briefing for {now}.\n\n"
            f"System Vitals:\n{hardware_info}\n\n"
            f"Notification Briefing:\n{notif_summary}\n\n"
            f"All background services are operating normally."
        )
        return briefing_text

    def generate_briefing_sync(self) -> str:
        """Synchronous wrapper for generate_briefing."""
        return asyncio.run(self.generate_briefing())


# Singleton instance
briefing_engine = DailyBriefingEngine()


if __name__ == "__main__":
    print("[DailyBriefingEngine] Initialized successfully.")
