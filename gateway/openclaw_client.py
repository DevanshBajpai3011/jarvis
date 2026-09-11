import asyncio
import json
import logging
import threading
import time
from typing import Callable, Optional
import websockets

import config

logger = logging.getLogger(__name__)


class OpenClawGatewayClient:
    """
    Async WebSocket Client connecting J.A.R.V.I.S. to the OpenClaw Gateway.
    Passively listens for server events and triggers without sending unprompted frames.
    """

    def __init__(self, ws_url: str = None, api_key: str = None, hud_callback=None):
        self.ws_url = ws_url or getattr(config, "OPENCLAW_WS_URL", "ws://localhost:18789")
        self.api_key = api_key or getattr(config, "OPENCLAW_API_KEY", "")
        self.hud_callback = hud_callback
        self.is_connected = False
        self.status = "DISCONNECTED"

        self._trigger_handlers = []
        self._status_callbacks = []
        self._ws = None
        self._loop = None
        self._thread = None
        self.running = False

    def register_trigger_handler(self, handler_func: Callable[[dict], None]):
        """Registers a callback function to handle incoming triggers/webhooks from OpenClaw."""
        if handler_func not in self._trigger_handlers:
            self._trigger_handlers.append(handler_func)

    def register_status_callback(self, callback_func: Callable[[str], None]):
        """Registers a callback function to be notified when connection status changes."""
        if callback_func not in self._status_callbacks:
            self._status_callbacks.append(callback_func)

    def _update_status(self, new_status: str):
        self.status = new_status
        self.is_connected = (new_status == "CONNECTED")
        logger.info(f"[OpenClawGateway] Status updated to: {new_status}")

        if self.hud_callback:
            try:
                hud_text = "GATEWAY: ONLINE" if self.is_connected else "GATEWAY: OFFLINE"
                self.hud_callback(hud_text)
            except Exception as e:
                logger.error(f"[OpenClawGateway] Error in hud_callback: {e}")

        for cb in self._status_callbacks:
            try:
                cb(new_status)
            except Exception as e:
                logger.error(f"[OpenClawGateway] Error in status callback: {e}")

    def start(self):
        """Starts the background asyncio event loop thread for persistent WebSocket monitoring."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops the background event loop and closes WebSocket connection."""
        self.running = False
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._close_ws(), self._loop)

    async def _close_ws(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.connect_loop())

    async def connect_loop(self):
        while self.running:
            try:
                headers = {}
                api_key = getattr(config, "OPENCLAW_API_KEY", "") or self.api_key
                ws_url = getattr(config, "OPENCLAW_WS_URL", "ws://localhost:18789") or self.ws_url

                if api_key and api_key.strip():
                    headers["Authorization"] = f"Bearer {api_key.strip()}"

                async with websockets.connect(
                    ws_url,
                    additional_headers=headers if headers else None,
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    self._ws = ws
                    self._update_status("CONNECTED")
                    print("[OpenClaw] Connected to gateway socket successfully.", flush=True)

                    # Listen passively for server events/messages
                    async for message in ws:
                        self._handle_message(message)

            except websockets.exceptions.ConnectionClosed as e:
                self._update_status("DISCONNECTED")
                print(f"[OpenClaw] Disconnected: Code {e.code} ({e.reason})", flush=True)
            except Exception as e:
                self._update_status("DISCONNECTED")
                print(f"[OpenClaw] Socket error: {e}", flush=True)

            await asyncio.sleep(3)

    def _handle_message(self, message: str):
        try:
            data = json.loads(message)
            print(f"[OpenClaw Event] {data}", flush=True)

            # Notify registered trigger handlers
            for handler in self._trigger_handlers:
                try:
                    handler(data)
                except Exception as ex:
                    logger.error(f"[OpenClawGateway] Handler execution error: {ex}")

        except Exception as e:
            print(f"[OpenClaw] Raw message: {message}", flush=True)

    def send_message(self, channel: str, recipient: str, text: str) -> bool:
        """
        Thread-safe RPC method to send an outgoing message via OpenClaw Gateway.
        """
        if not self.is_connected or not self._ws or not self._loop:
            logger.warning("[OpenClawGateway] Cannot send message: Client is disconnected.")
            return False

        payload = {
            "type": "req",
            "id": f"msg_{int(time.time() * 1000)}",
            "method": "send_message",
            "params": {
                "channel": channel,
                "recipient": recipient,
                "text": text,
            },
        }

        asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(payload)), self._loop)
        return True


if __name__ == "__main__":
    client = OpenClawGatewayClient()
    client.register_status_callback(lambda s: print(f"[Test Callback] OpenClaw Status: {s}"))
    client.start()
    print("[OpenClawGateway] Client started in background.")
    time.sleep(3)
    client.stop()
