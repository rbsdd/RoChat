"""
WebSocket client — runs in a background thread, emits Qt signals.

Handles:
  - Auto-reconnect on disconnect
  - Thread-safe send queue
  - Signal-based API for the UI layer
"""

import asyncio
import json
import logging
import threading

from PyQt5.QtCore import QObject, pyqtSignal

try:
    import websockets
except ImportError:
    raise SystemExit("websockets package is required: pip install websockets")

logger = logging.getLogger(__name__)


class WSClient(QObject):
    """Threaded WebSocket client with Qt signal interface."""

    # ── signals ──────────────────────────────────────────────────────
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    message_received = pyqtSignal(dict)   # chat message
    auth_success = pyqtSignal(dict)
    auth_failed = pyqtSignal(str)
    joined_server = pyqtSignal(dict)
    user_joined = pyqtSignal(dict)
    user_left = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    RECONNECT_DELAY = 5  # seconds

    def __init__(self, server_url: str):
        super().__init__()
        self.server_url = server_url
        self._ws = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._send_queue: asyncio.Queue | None = None

    # ── public API (main thread) ─────────────────────────────────────

    def start(self):
        """Launch the background I/O thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the background thread to stop."""
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def send(self, data: dict):
        """Enqueue *data* for sending (thread-safe)."""
        if self._loop and self._running and self._send_queue is not None:
            self._loop.call_soon_threadsafe(self._send_queue.put_nowait, data)

    def authenticate(self, user_id: str, username: str):
        self.send({"type": "auth", "user_id": user_id, "username": username})

    def join_server(self, place_id: str, job_id: str):
        self.send({"type": "join", "place_id": place_id, "job_id": job_id})

    def leave_server(self):
        self.send({"type": "leave"})

    def send_message(self, channel: str, text: str):
        self.send({"type": "message", "channel": channel, "text": text})

    # ── background thread ────────────────────────────────────────────

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._send_queue = asyncio.Queue()
        try:
            self._loop.run_until_complete(self._connect_loop())
        except Exception as exc:
            logger.error("WS thread fatal: %s", exc)
        finally:
            self._loop.close()

    async def _connect_loop(self):
        """Connect, read messages, auto-reconnect."""
        while self._running:
            try:
                async with websockets.connect(self.server_url) as ws:
                    self._ws = ws
                    self.connected.emit()
                    logger.info("Connected to %s", self.server_url)

                    sender = asyncio.create_task(self._sender())
                    try:
                        async for raw in ws:
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            self._dispatch(data)
                    finally:
                        sender.cancel()
            except Exception as exc:
                logger.warning("Connection error: %s", exc)
                self.error_occurred.emit(str(exc))

            self._ws = None
            self.disconnected.emit()

            if self._running:
                logger.info("Reconnecting in %ss…", self.RECONNECT_DELAY)
                await asyncio.sleep(self.RECONNECT_DELAY)

    async def _sender(self):
        """Drain the send queue and write to the socket."""
        while True:
            data = await self._send_queue.get()
            try:
                if self._ws:
                    await self._ws.send(json.dumps(data, ensure_ascii=False))
            except Exception as exc:
                logger.error("Send error: %s", exc)

    def _dispatch(self, data: dict):
        """Route an incoming server message to the right signal."""
        t = data.get("type")
        if t == "auth_ok":
            self.auth_success.emit(data)
        elif t == "auth_fail":
            self.auth_failed.emit(data.get("reason", "Unknown error"))
        elif t == "joined":
            self.joined_server.emit(data)
        elif t == "message":
            self.message_received.emit(data)
        elif t == "user_joined":
            self.user_joined.emit(data)
        elif t == "user_left":
            self.user_left.emit(data)
