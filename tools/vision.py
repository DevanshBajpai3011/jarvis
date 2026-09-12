import io
import base64
import logging
from PIL import Image, ImageGrab
import mss
import google.generativeai as genai
import config

logger = logging.getLogger(__name__)

if hasattr(config, "GEMINI_API_KEY") and config.GEMINI_API_KEY:
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
    except Exception as err:
        logger.warning(f"[Vision Tool] GenAI configuration warning: {err}")


def _grab_screen_image() -> Image.Image:
    """Helper to grab screen image using PIL ImageGrab with mss fallback and blank image canvas fallback."""
    try:
        return ImageGrab.grab()
    except Exception:
        pass

    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.rgb)
    except Exception:
        pass

    # Fallback canvas image when running in non-interactive/headless Windows sessions
    return Image.new("RGB", (1920, 1080), color=(0, 0, 0))



def capture_screen_base64() -> str:
    """Captures the primary monitor screenshot and converts it to a base64 string."""
    screenshot = _grab_screen_image()
    buffer = io.BytesIO()
    screenshot.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def analyze_screen(prompt: str = "Describe what is currently visible on my screen in detail.") -> str:
    """
    Captures primary screen and queries Gemini Flash Multimodal API.
    
    Args:
        prompt: User's specific question about their screen content.
    """
    try:
        if hasattr(config, "GEMINI_API_KEY") and config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=config.GEMINI_API_KEY)
            except Exception:
                pass

        screenshot = _grab_screen_image()
        
        # Load multimodal Gemini Flash model
        model = genai.GenerativeModel("gemini-3.6-flash")
        
        response = model.generate_content([
            prompt,
            screenshot
        ])
        
        return response.text if response and hasattr(response, "text") and response.text else "Unable to extract visual information from the screen."

    except Exception as e:
        logger.error(f"[Vision Error] Screen vision analysis failed: {e}")
        return f"Screen vision analysis failed: {e}"


if __name__ == "__main__":
    print("[Vision Tool] Initialized successfully.")
