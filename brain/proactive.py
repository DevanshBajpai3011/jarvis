import asyncio
from tools.notification_listener import notification_service


class ProactiveMonitor:
    def __init__(self):
        self.seen_notification_ids = set()

    async def check_notifications_and_alert(self) -> str:
        """Polls new Windows notifications and returns actionable alerts for J.A.R.V.I.S. to speak."""
        has_access = await notification_service.request_access()
        if not has_access:
            return "Notification listener access not granted by Windows."

        new_notifications = await notification_service.get_unread_notifications(max_count=5)
        unhandled_alerts = []

        for notif in new_notifications:
            notif_id = notif["id"]
            if notif_id not in self.seen_notification_ids:
                self.seen_notification_ids.add(notif_id)

                # Ignore noisy system/background app updates
                app_lower = notif["app_name"].lower()
                if any(ignored in app_lower for ignored in ["defender", "update", "store"]):
                    continue

                unhandled_alerts.append(
                    f"Notification from {notif['app_name']}: '{notif['title']}' - {notif['body']}"
                )

        if not unhandled_alerts:
            return "No new actionable notifications."

        return "\n".join(unhandled_alerts)


proactive_monitor = ProactiveMonitor()
