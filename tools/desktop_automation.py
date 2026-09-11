import os
import logging
import pyautogui

logger = logging.getLogger(__name__)

# Safety settings for PyAutoGUI
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.1


class DesktopGUITool:
    """
    Desktop GUI & Game Automation Tool using PyAutoGUI and Windows API wrappers.
    """

    def click_at_coordinates(self, x: int, y: int) -> str:
        """Clicks on screen at specific (x, y) pixel coordinates."""
        try:
            pyautogui.click(int(x), int(y))
            return f"Successfully clicked at screen coordinates ({x}, {y})."
        except Exception as e:
            return f"Failed to click at coordinates ({x}, {y}): {e}"

    def type_keystrokes(self, text: str) -> str:
        """Types keystrokes into the currently focused window."""
        try:
            pyautogui.write(text, interval=0.02)
            return f"Successfully typed keystrokes: '{text}'"
        except Exception as e:
            return f"Failed to type keystrokes: {e}"

    def focus_window(self, title: str) -> str:
        """Focuses a window matching title string."""
        if not title:
            return "Window title is required."
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title)
            if windows:
                win = windows[0]
                win.activate()
                return f"Successfully focused window: '{win.title}'"
            return f"No active window found matching title '{title}'."
        except Exception as e:
            return f"Failed to focus window '{title}': {e}"

    def locate_element_on_screen(self, image_path: str) -> str:
        """Locates image template on screen and returns (x, y) coordinates."""
        if not image_path or not os.path.exists(image_path):
            return f"Template image not found: {image_path}"
        try:
            location = pyautogui.locateOnScreen(image_path, confidence=0.8)
            if location:
                center = pyautogui.center(location)
                return f"Found element template at coordinates ({center.x}, {center.y})."
            return "Element template not found on current screen."
        except Exception as e:
            return f"Error locating element template on screen: {e}"


# Helper functions
def desktop_click(x: int, y: int) -> str:
    return DesktopGUITool().click_at_coordinates(x, y)


def desktop_type(text: str) -> str:
    return DesktopGUITool().type_keystrokes(text)


def desktop_focus_window(title: str) -> str:
    return DesktopGUITool().focus_window(title)


def desktop_locate_element(image_path: str) -> str:
    return DesktopGUITool().locate_element_on_screen(image_path)


if __name__ == "__main__":
    tool = DesktopGUITool()
    print("[DesktopGUITool] Loaded successfully.")
