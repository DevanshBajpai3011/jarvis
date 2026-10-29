import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-3.6-flash")
PIPER_VOICE_MODEL = os.getenv("PIPER_VOICE_MODEL", "en_GB-alan-medium")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
STREAMING_TTS = os.getenv("STREAMING_TTS", "true").lower() == "true"
ENABLE_FOLLOW_UP_MODE = os.getenv("ENABLE_FOLLOW_UP_MODE", "true").lower() == "true"
FOLLOW_UP_LISTEN_TIMEOUT = int(os.getenv("FOLLOW_UP_LISTEN_TIMEOUT", "8"))
WAKEWORD_NAME = os.getenv("WAKEWORD_NAME", "hey_jarvis")
CUSTOM_WAKEWORD_PATH = os.getenv("CUSTOM_WAKEWORD_PATH", "models/jarvis.onnx")
WAKEWORD_THRESHOLD = float(os.getenv("WAKEWORD_THRESHOLD", "0.35"))
WAKEWORD_GAIN_SCALER = float(os.getenv("WAKEWORD_GAIN_SCALER", "2.0"))

# Voice-activity endpointing for wakeword/listener.py::record_phrase(), centralized here
# instead of hardcoded in three places (BUGS.md Bug #10). VAD_HARD_CAP_SECONDS matches
# the previous hardcoded default (10.0) unchanged. VAD_THRESHOLD_MULTIPLIER: record_phrase()
# calibrates a per-recording ambient noise floor instead of using a flat RMS cutoff (this
# machine's fan noise alone measured RMS ~350-500 unboosted -- see Bug #10), and sets the
# actual speech threshold to ambient_stat * VAD_THRESHOLD_MULTIPLIER. 1.4 is a middle-of-
# range choice between ~1.3 (more sensitive to quiet speech, less margin above ambient
# jitter) and ~1.5 (more margin against ambient noise, slightly more likely to clip a very
# soft trailing word).
#
# --- Fix attempt #2 (`[2026-09-26]`) -- real user voice testing found fix attempt #1
# (`[2026-09-17]`) did not resolve the bug; see BUGS.md Bug #10 for the full history. ---
#
# VAD_CALIBRATION_SECONDS raised 0.4 -> 0.7s (7 chunks instead of 4): the calibration
# statistic itself changed too (see wakeword/listener.py) from a plain mean to a high
# percentile of the calibration window, which needs a few more samples to be meaningful.
#
# VAD_MIN_THRESHOLD: fix attempt #1 set this to 150.0, reasoned from this session's own
# scripted test observations (treated as unusually-quiet outliers needing a safety floor
# above them). Real live voice testing then measured actual ambient floors of 6.8, 16.0,
# 7.6, and 72.0 RMS across four separate real recordings -- meaning those "outliers" were
# in fact the normal range for this room, and 150.0 sat *above* all four real
# ambient*1.4 values (9.5, 22.4, 10.6, 100.8), collapsing the "dynamic" calibration back
# into a static 150 in every real case observed -- reintroducing the exact static-
# threshold problem this fix exists to solve, just at a different number. That reasoning
# does not hold and this is not "retune the constant" -- the mechanism was wrong: a fixed
# absolute floor can never be correct for every room, because "how quiet is too quiet to
# trust" isn't a universal constant. Lowered to 20.0 and demoted to what it should always
# have been -- a true degenerate-case guard (protects only against a calibration reading
# at or near true zero, e.g. a disconnected/muted mic), sitting well below every one of
# the four real observed ambient*1.4 values above, so the calibrated value is what
# actually governs threshold in normal rooms now, not this floor.
#
# VAD_TRAILING_SILENCE_SECONDS raised 1.2 -> 2.0s: independent of the threshold-value bug
# above, real testing showed 1.2s is short for a natural human thinking-pause (which
# commonly runs 1.5-3+ seconds) -- even a perfectly-calibrated threshold cannot rescue a
# pause where the user genuinely stops vocalizing for longer than this window, since
# during a true pause RMS sits at the ambient floor itself, below any speech threshold by
# construction. This is an explicit latency/pause-tolerance trade-off, not a byproduct of
# the calibration fix.
VAD_HARD_CAP_SECONDS = float(os.getenv("VAD_HARD_CAP_SECONDS", "10.0"))
VAD_TRAILING_SILENCE_SECONDS = float(os.getenv("VAD_TRAILING_SILENCE_SECONDS", "2.0"))
VAD_THRESHOLD_MULTIPLIER = float(os.getenv("VAD_THRESHOLD_MULTIPLIER", "1.4"))
VAD_CALIBRATION_SECONDS = float(os.getenv("VAD_CALIBRATION_SECONDS", "0.7"))
VAD_ONSET_SECONDS = float(os.getenv("VAD_ONSET_SECONDS", "0.2"))
VAD_MIN_THRESHOLD = float(os.getenv("VAD_MIN_THRESHOLD", "20.0"))

AUDIO_CHUNK_SIZE = int(os.getenv("AUDIO_CHUNK_SIZE", "1280"))
AUDIO_RATE = int(os.getenv("AUDIO_RATE", "16000"))
AUDIO_CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))

# Faster-Whisper device/compute-type selection. "auto" detects CUDA via ctranslate2
# and picks float16 on GPU / int8 on CPU; set explicitly to override auto-detection.
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # "auto" | "cuda" | "cpu"
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "auto")  # "auto" | "float16" | "int8"






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
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gemini-3.6-flash")
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
