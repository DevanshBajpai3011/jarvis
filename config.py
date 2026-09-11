import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.0-flash")
PIPER_VOICE_MODEL = os.getenv("PIPER_VOICE_MODEL", "en_GB-alan-medium")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
STREAMING_TTS = os.getenv("STREAMING_TTS", "true").lower() == "true"
ENABLE_FOLLOW_UP_MODE = os.getenv("ENABLE_FOLLOW_UP_MODE", "true").lower() == "true"
FOLLOW_UP_LISTEN_TIMEOUT = int(os.getenv("FOLLOW_UP_LISTEN_TIMEOUT", "8"))
WAKEWORD_NAME = os.getenv("WAKEWORD_NAME", "hey_jarvis")
CUSTOM_WAKEWORD_PATH = os.getenv("CUSTOM_WAKEWORD_PATH", "models/jarvis.onnx")
WAKEWORD_THRESHOLD = float(os.getenv("WAKEWORD_THRESHOLD", "0.50"))
AUDIO_CHUNK_SIZE = int(os.getenv("AUDIO_CHUNK_SIZE", "1280"))
AUDIO_RATE = int(os.getenv("AUDIO_RATE", "16000"))
AUDIO_CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))






# Fish Audio TTS parameters
TTS_ENGINE = os.getenv("TTS_ENGINE", "fish")  # Options: "fish", "piper"
FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "")
FISH_AUDIO_MODEL_ID = os.getenv("FISH_AUDIO_MODEL_ID", "s2.1-pro-free")
FISH_AUDIO_VOICE_REF_ID = os.getenv("FISH_AUDIO_VOICE_REF_ID", None)
PIPER_SAMPLE_RATE = int(os.getenv("PIPER_SAMPLE_RATE", "22050"))
FISH_AUDIO_SAMPLE_RATE = int(os.getenv("FISH_AUDIO_SAMPLE_RATE", "24000"))
ENABLE_OFFLINE_TTS_FALLBACK = os.getenv("ENABLE_OFFLINE_TTS_FALLBACK", "true").lower() == "true"
ENABLE_3TIER_TTS = os.getenv("ENABLE_3TIER_TTS", "true").lower() == "true"
GOOGLE_TTS_LANG = os.getenv("GOOGLE_TTS_LANG", "en")
GOOGLE_TTS_TLD = os.getenv("GOOGLE_TTS_TLD", "co.uk")  # British accent to match J.A.R.V.I.S. tone

# OpenClaw Gateway parameters
OPENCLAW_WS_URL = os.getenv("OPENCLAW_WS_URL", "ws://localhost:18789")
OPENCLAW_API_KEY = os.getenv("OPENCLAW_API_KEY", "")
ENABLE_OPENCLAW_GATEWAY = os.getenv("ENABLE_OPENCLAW_GATEWAY", "true").lower() == "true"
OPENCLAW_WS_URL = "ws://localhost:18789"
OPENCLAW_API_KEY = ""
ENABLE_OPENCLAW_GATEWAY = True

# Dual-Brain Architecture parameters
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")
BACKGROUND_MODEL_PRIMARY = os.getenv("BACKGROUND_MODEL_PRIMARY", "meta-llama/llama-3.3-70b-instruct")
BACKGROUND_MODEL_FALLBACK = os.getenv("BACKGROUND_MODEL_FALLBACK", "google/gemini-2.0-flash-001")
ENABLE_DUAL_BRAIN = os.getenv("ENABLE_DUAL_BRAIN", "true").lower() == "true"

# Two-Stage Cognitive Memory parameters
ENABLE_TWO_STAGE_MEMORY = os.getenv("ENABLE_TWO_STAGE_MEMORY", "true").lower() == "true"
MEMORY_CATEGORIES = ["identity", "preferences", "projects", "relationships"]

# Agentic Planning & Self-Healing options
ENABLE_AGENTIC_PLANNER = os.getenv("ENABLE_AGENTIC_PLANNER", "true").lower() == "true"
ENABLE_SELF_HEALING = os.getenv("ENABLE_SELF_HEALING", "true").lower() == "true"
MAX_HEALING_ATTEMPTS = int(os.getenv("MAX_HEALING_ATTEMPTS", "2"))

# OS Automation & Data Processing parameters
ENABLE_PLAYWRIGHT_AUTOMATION = os.getenv("ENABLE_PLAYWRIGHT_AUTOMATION", "true").lower() == "true"
ENABLE_DESKTOP_GUI_AUTOMATION = os.getenv("ENABLE_DESKTOP_GUI_AUTOMATION", "true").lower() == "true"
ENABLE_DATA_PROCESSING_TOOLS = os.getenv("ENABLE_DATA_PROCESSING_TOOLS", "true").lower() == "true"
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"

if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
    print("WARNING: GEMINI_API_KEY is not set or contains the default placeholder in .env file.")

if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_openrouter_api_key_here":
    print("WARNING: OPENROUTER_API_KEY is not set or contains the default placeholder in .env file.")
