import sys
import logging
from PySide6.QtWidgets import QApplication
from brain import Orchestrator
from ui import JarvisOverlay, SystemBridge

logger = logging.getLogger(__name__)


def main():
    print("JARVIS online.")
    print("Initializing PySide6 GUI Application and integrated system engines...")

    app = QApplication(sys.argv)
    app.setApplicationName("J.A.R.V.I.S. Voice AI")

    # 1. Instantiate JarvisOverlay UI window
    overlay = JarvisOverlay()

    # 2. Instantiate Orchestrator (unifies STT, TTS, Gemini, OpenRouter, Memory, Vision, Tools, Agent)
    orchestrator = Orchestrator()

    # 3. Instantiate SystemBridge (connects UI signals & starts background VoiceListenerWorker thread)
    bridge = SystemBridge(overlay=overlay, orchestrator=orchestrator)

    # 4. Clean exit handling upon application exit
    app.aboutToQuit.connect(bridge.stop)

    # 5. Display overlay GUI
    overlay.show()

    print("[JARVIS] System fully online and ready. Displaying GUI overlay...", flush=True)

    # Run PySide6 main event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
