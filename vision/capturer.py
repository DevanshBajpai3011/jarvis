import os
import logging
from typing import Optional
import mss
import cv2
from PIL import Image

logger = logging.getLogger(__name__)


class VisionCapturer:
    """
    Handles real-time screen capture and webcam snapshots for vision processing.
    """

    def __init__(self, temp_dir: str = "temp_vision"):
        self.temp_dir = temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)

    def _ensure_dir(self, filepath: str) -> None:
        """Ensures the destination directory for the given filepath exists."""
        dirname = os.path.dirname(os.path.abspath(filepath))
        if dirname:
            os.makedirs(dirname, exist_ok=True)

    def capture_screen(self, output_filename: str = "temp_vision/screen.jpg") -> Optional[str]:
        """
        Captures the primary display monitor screenshot and saves it as JPEG (quality 85).
        Returns the saved file path on success, or None if capture fails or lacks permissions.
        """
        try:
            self._ensure_dir(output_filename)
            with mss.mss() as sct:
                # Primary monitor is sct.monitors[1] if available, otherwise sct.monitors[0]
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)

                # Convert raw mss screenshot to PIL Image (RGB)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)

                # Compress/save in JPEG format with quality 85 to optimize payload size
                img.save(output_filename, format="JPEG", quality=85)
                logger.info(f"Screen captured successfully and saved to {output_filename}")
                return output_filename
        except Exception as e:
            logger.warning(f"Failed to capture screen: {e}")
            return None

    def capture_webcam(self, output_filename: str = "temp_vision/webcam.jpg") -> Optional[str]:
        """
        Captures a single frame from default webcam (index 0) and saves it as JPEG (quality 85).
        Returns the saved file path on success, or None if frame capture fails or camera is unavailable.
        """
        cap = None
        try:
            self._ensure_dir(output_filename)
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.warning("Failed to open default webcam (camera index 0).")
                return None

            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning("Failed to read frame from webcam.")
                return None

            # Convert BGR frame from OpenCV to RGB for PIL image creation
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame)

            # Compress/save in JPEG format with quality 85
            img.save(output_filename, format="JPEG", quality=85)
            logger.info(f"Webcam image captured successfully and saved to {output_filename}")
            return output_filename
        except Exception as e:
            logger.warning(f"Error during webcam capture: {e}")
            return None
        finally:
            if cap is not None:
                cap.release()
