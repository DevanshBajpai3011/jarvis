import os
import logging
import ctypes
import platform
import psutil
import screen_brightness_control as sbc

logger = logging.getLogger(__name__)

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
except Exception:
    HAS_NVML = False

try:
    import wmi
    import pythoncom
    HAS_WMI = True
except Exception:
    HAS_WMI = False

# Windows Virtual Key Codes for Volume Control
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002


def get_power_draw_watts(cpu_pct: float = None, is_plugged: bool = None) -> tuple:
    """
    Computes estimated system power draw in watts. This is the single shared
    implementation used by both ui/overlay.py's TelemetryWorker (HUD display) and
    get_power_draw() below (LLM-callable tool), so the two surfaces can't silently
    drift out of sync with each other.

    Combines a live NVIDIA GPU wattage reading (via pynvml, when available) with
    either a WMI battery-discharge-rate reading (when on battery) or a rough
    CPU-load-based wattage estimate (when on AC power, since Windows exposes no
    simple universal CPU-package-power API without vendor-specific drivers).

    Args:
        cpu_pct (float, optional): Current CPU utilization percent. Queried via psutil if omitted.
        is_plugged (bool, optional): Whether AC power is connected. Queried via psutil if omitted.

    Returns:
        tuple[float, str, float]: (total_watts, human-readable label e.g. "45 W (AC)", gpu_watts).
    """
    if cpu_pct is None:
        cpu_pct = psutil.cpu_percent(interval=0.5)
    if is_plugged is None:
        battery = psutil.sensors_battery()
        is_plugged = battery.power_plugged if battery else True

    gpu_watts = 0.0
    if HAS_NVML:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            gpu_watts = float(pynvml.nvmlDeviceGetPowerUsage(handle)) / 1000.0
        except Exception:
            gpu_watts = 0.0

    if not is_plugged and HAS_WMI:
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI(namespace="root\\wmi")
            items = c.BatteryStatus()
            if items and len(items) > 0:
                rate_mw = getattr(items[0], "DischargingRate", None)
                if rate_mw and rate_mw > 0:
                    watts = rate_mw / 1000.0
                    return watts, f"{watts:.1f} W", gpu_watts
        except Exception:
            pass
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    cpu_watts = 10.0 + (cpu_pct / 100.0) * 35.0
    total_watts = cpu_watts + gpu_watts
    tag = "AC" if is_plugged else "BAT"
    return total_watts, f"{total_watts:.0f} W ({tag})", gpu_watts


def get_power_draw() -> str:
    """
    Retrieve current CPU and GPU power draw in watts.

    Reports an estimated total system power draw (combining a CPU-load-based
    estimate or battery discharge rate with a live NVIDIA GPU wattage reading),
    the GPU's own power draw, and whether the system is running on AC or battery.
    """
    try:
        total_watts, watts_label, gpu_watts = get_power_draw_watts()
        battery = psutil.sensors_battery()
        is_plugged = battery.power_plugged if battery else True

        return (
            f"Power Draw:\n"
            f"- Estimated Total System Power: {watts_label}\n"
            f"- GPU Power Draw: {gpu_watts:.1f} W\n"
            f"- Power Source: {'Plugged In (AC)' if is_plugged else 'On Battery'}"
        )
    except Exception as e:
        logger.error(f"[OSTools] Failed to retrieve power draw: {e}")
        return f"Failed to retrieve power draw: {e}"


def set_system_volume(level: int) -> str:
    """
    Sets master volume percentage (0-100) on Windows without requiring administrator privileges.
    Uses pycaw if available, falling back to ctypes virtual key presses.
    """
    logger.info(f"[OSTools] Setting system volume to {level}%")

    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        if hasattr(devices, "EndpointVolume"):
            volume = devices.EndpointVolume
        else:
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))

        scalar = max(0.0, min(1.0, float(level) / 100.0))
        volume.SetMasterVolumeLevelScalar(scalar, None)
        return f"System volume set to {level}%"

    except Exception as pycaw_err:
        logger.warning(f"[OSTools] pycaw volume control failed ({pycaw_err}); falling back to ctypes virtual key events.")

        try:
            user32 = ctypes.windll.user32
            target_level = max(0, min(100, int(level)))

            for _ in range(50):
                user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                user32.keybd_event(VK_VOLUME_DOWN, 0, KEYEVENTF_KEYUP, 0)

            presses = target_level // 2
            for _ in range(presses):
                user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                user32.keybd_event(VK_VOLUME_UP, 0, KEYEVENTF_KEYUP, 0)

            return f"System volume set to {target_level}%"
        except Exception as e:
            logger.error(f"[OSTools] Error setting volume via key events: {e}")
            return f"Error setting volume: {e}"


def set_display_brightness(level_percent: int) -> str:
    """Set primary display brightness level (0-100%)."""
    try:
        level_percent = max(0, min(100, int(level_percent)))
        sbc.set_brightness(level_percent)
        return f"Display brightness set to {level_percent}%."
    except Exception as e:
        logger.error(f"[OSTools] Failed to set display brightness: {e}")
        return f"Failed to set display brightness: {e}"


def get_hardware_status() -> str:
    """Retrieve current battery level, power status, CPU usage, RAM usage, and power draw."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent

        battery_info = "Desktop / No Battery Detected"
        battery = psutil.sensors_battery()
        is_plugged = True
        if battery:
            is_plugged = battery.power_plugged
            plugged = "Plugged In" if battery.power_plugged else "On Battery"
            battery_info = f"{battery.percent}% ({plugged})"

        brightness = sbc.get_brightness(display=0)
        brightness_str = f"{brightness[0]}%" if brightness else "Unknown"

        _, power_label, _ = get_power_draw_watts(cpu_pct=cpu, is_plugged=is_plugged)

        return (
            f"Hardware Status:\n"
            f"- CPU Usage: {cpu}%\n"
            f"- RAM Usage: {ram}%\n"
            f"- Display Brightness: {brightness_str}\n"
            f"- Battery: {battery_info}\n"
            f"- Power Draw: {power_label}"
        )
    except Exception as e:
        logger.error(f"[OSTools] Failed to retrieve hardware metrics: {e}")
        return f"Failed to retrieve hardware metrics: {e}"


def shutdown_system(confirm: bool = False) -> str:
    """Safely shuts down the computer. Requires explicit user consent (`confirm=True`)."""
    if not confirm:
        return "CONFIRMATION_REQUIRED: Shutting down the computer will close all running applications. Ask the user for explicit permission before setting confirm=True."

    if platform.system() == "Windows":
        os.system("shutdown /s /t 5")
        return "Initiating system shutdown in 5 seconds."
    return "Shutdown command is configured for Windows systems."


def restart_system(confirm: bool = False) -> str:
    """Restarts the computer. Requires explicit user consent (`confirm=True`)."""
    if not confirm:
        return "CONFIRMATION_REQUIRED: Restarting the system will interrupt active tasks. Ask the user for explicit permission before setting confirm=True."

    if platform.system() == "Windows":
        os.system("shutdown /r /t 5")
        return "Initiating system restart in 5 seconds."
    return "Restart command is configured for Windows systems."


def sleep_system() -> str:
    """Puts the computer into sleep mode."""
    if platform.system() == "Windows":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return "Entering sleep mode."
    return "Sleep command is configured for Windows systems."


def create_and_save_file(filepath: str, content: str, open_after_save: bool = True) -> str:
    """
    Saves text content to any target path on the system.
    Creates missing directories automatically and launches the file if requested.
    """
    try:
        from tools.file_search import resolve_path_shortcut
        target_path = resolve_path_shortcut(filepath)

        # Default to .txt if no extension provided
        if not target_path.suffix:
            target_path = target_path.with_suffix(".txt")

        # Create parent directories if missing
        target_path.parent.mkdir(parents=True, exist_ok=True)

        target_path.write_text(content, encoding="utf-8")

        if open_after_save:
            os.startfile(str(target_path))

        return f"File successfully saved to '{target_path}'"

    except Exception as e:
        logger.error(f"[OSTools] Failed to save file: {e}")
        return f"Failed to save file: {e}"


def open_target_item(path_str: str) -> str:
    """Opens any file or folder directly using default system application."""
    try:
        from tools.file_search import resolve_path_shortcut
        target_path = resolve_path_shortcut(path_str)

        if not target_path.exists():
            return f"Cannot open: Target path '{target_path}' does not exist."

        os.startfile(str(target_path))
        return f"Opened '{target_path}'"
    except Exception as e:
        logger.error(f"[OSTools] Failed to open item: {e}")
        return f"Failed to open item: {e}"


if __name__ == "__main__":
    print(get_hardware_status())

