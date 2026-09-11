import asyncio
import ctypes
from typing import List, Dict
import winrt.windows.ui.notifications.management as mgmt
import winrt.windows.ui.notifications as notifications


class WindowsNotificationListener:
    def __init__(self):
        self.listener = None
        self._init_listener()

    def _init_listener(self):
        try:
            try:
                ctypes.windll.ole32.CoInitializeEx(None, 0x0)
            except Exception:
                pass

            if hasattr(mgmt.UserNotificationListener, "current"):
                self.listener = mgmt.UserNotificationListener.current
            elif hasattr(mgmt.UserNotificationListener, "get_current"):
                self.listener = mgmt.UserNotificationListener.get_current()
            else:
                self.listener = mgmt.UserNotificationListener()
        except Exception as e:
            print(f"[NotificationListener] Failed to obtain WinRT listener: {e}")

    async def request_access(self) -> bool:
        """Requests user permission to read Windows notifications."""
        if not self.listener:
            return False
        try:
            if hasattr(self.listener, "get_access_status"):
                status = self.listener.get_access_status()
                if status == mgmt.UserNotificationListenerAccessStatus.ALLOWED:
                    return True

            status = await asyncio.wait_for(self.listener.request_access_async(), timeout=3.0)
            return status == mgmt.UserNotificationListenerAccessStatus.ALLOWED
        except Exception as e:
            print(f"[NotificationListener] Access request error: {e}")
            return False

    async def get_unread_notifications(self, max_count: int = 5) -> List[Dict[str, str]]:
        """Fetches active unread Windows Toast notifications."""
        if not self.listener:
            return []

        results = []
        try:
            notifs_op = self.listener.get_notifications_async(notifications.NotificationKinds.TOAST)
            notifs = await asyncio.wait_for(notifs_op, timeout=4.0)

            for item in list(notifs)[-max_count:]:
                app_name = "System"
                try:
                    if item.app_info and hasattr(item.app_info, "display_info"):
                        disp = item.app_info.display_info
                        if hasattr(disp, "title") and disp.title:
                            app_name = disp.title
                        elif hasattr(disp, "display_name") and disp.display_name:
                            app_name = disp.display_name
                except Exception:
                    pass

                # Extract text bindings from toast content
                toast_binding = item.notification.visual.get_binding(notifications.KnownNotificationBindings.toast_generic)
                title = "Notification"
                body = ""
                if toast_binding:
                    text_elements = toast_binding.get_text_elements()
                    title = text_elements[0].text if len(text_elements) > 0 else "Notification"
                    body = text_elements[1].text if len(text_elements) > 1 else ""

                timestamp = ""
                try:
                    if hasattr(item, "creation_time") and hasattr(item.creation_time, "strftime"):
                        timestamp = item.creation_time.strftime("%H:%M:%S")
                except Exception:
                    pass

                results.append({
                    "id": str(item.id),
                    "app_name": app_name,
                    "title": title,
                    "body": body,
                    "timestamp": timestamp
                })
        except Exception as e:
            print(f"[NotificationListener] Failed to read notifications: {e}")

        return results


# Singleton instance
notification_service = WindowsNotificationListener()
