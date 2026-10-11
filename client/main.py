#!/usr/bin/env python3
"""
RoChat — main entry point.

Wires together:
  ConfigManager  →  LoginDialog  →  RobloxAPI  →  WSClient  →  ChatOverlay  →  OverlayManager
"""

import sys
import os
import logging
from datetime import datetime, timezone

# PyInstaller --onefile path fix
if getattr(sys, "frozen", False):
    _base = sys._MEIPASS  # type: ignore[attr-defined]
else:
    _base = os.path.dirname(os.path.abspath(__file__))
if _base not in sys.path:
    sys.path.insert(0, _base)

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer

from login_dialog import LoginDialog
from roblox_api import RobloxAPI
from ws_client import WSClient
from chat_overlay import ChatOverlay
from window_manager import OverlayManager
import config_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rochat")


# Global exception hook to prevent crashes
def exception_hook(exctype, value, tb):
    logger.error("Uncaught exception: %s", value, exc_info=(exctype, value, tb))
    sys.__excepthook__(exctype, value, tb)


sys.excepthook = exception_hook


class RoChat:
    """Application controller."""

    PRESENCE_POLL_MS = 2_500   # check Roblox presence every 2.5 s
    OVERLAY_TICK_MS = 250      # overlay Z-order check

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("RoChat")

        self.roblox: RobloxAPI | None = None
        self.ws: WSClient | None = None
        self.overlay: ChatOverlay | None = None
        self.overlay_mgr: OverlayManager | None = None

        self._place_id: str | None = None
        self._job_id: str | None = None
        self._username: str = ""
        self._server_url: str = "ws://localhost:8765"

    def run(self) -> int:
        cfg = config_manager.load_config()
        saved_cookie = cfg.get("cookie", "")
        saved_server = cfg.get("server_url", "ws://localhost:8765")
        auto_login = cfg.get("auto_login", True)

        cookie = ""
        server_url = saved_server

        # Attempt auto-login if saved credentials exist
        if saved_cookie and auto_login:
            logger.info("Attempting auto-login with saved credentials...")
            test_api = RobloxAPI(saved_cookie)
            if test_api.authenticate():
                self.roblox = test_api
                cookie = saved_cookie
                server_url = saved_server
                logger.info("Auto-login successful for %s!", self.roblox.username)

        # If auto-login was not possible, show the login dialog
        if not self.roblox:
            dlg = LoginDialog(initial_cookie=saved_cookie, initial_server=saved_server)
            if dlg.exec_() != LoginDialog.Accepted:
                return 0

            cookie = dlg.get_cookie()
            server_url = dlg.get_server_url()
            remember = dlg.is_remember_checked()

            if not cookie:
                return 0

            self.roblox = RobloxAPI(cookie)
            if not self.roblox.authenticate():
                QMessageBox.critical(
                    None, "Ошибка авторизации",
                    "Не удалось войти в аккаунт Roblox.\nПроверьте .ROBLOSECURITY ключ и повторите попытку.",
                )
                return 1

            if remember:
                config_manager.save_config(cookie, server_url, auto_login=True)
            else:
                config_manager.clear_config()

        self._username = self.roblox.username or "Player"
        self._server_url = server_url

        # Build overlay
        self.overlay = ChatOverlay()
        self.overlay.send_message.connect(self._on_send)
        self.overlay.logout_requested.connect(self._on_logout)
        self.overlay.set_connecting()
        self.overlay.show()

        # Initial prompt to player
        self.overlay.add_message(
            "server", "Система",
            "Добро пожаловать в RoChat! Для начала общения войдите в любой плейс Roblox.",
            _now(), is_system=True,
        )

        # Overlay Z-order manager
        hwnd = int(self.overlay.winId())
        self.overlay_mgr = OverlayManager(hwnd)

        # WebSocket client
        self.ws = WSClient(self._server_url)
        self.ws.connected.connect(self._on_ws_connected)
        self.ws.disconnected.connect(self._on_ws_disconnected)
        self.ws.auth_success.connect(self._on_auth_ok)
        self.ws.auth_failed.connect(self._on_auth_fail)
        self.ws.message_received.connect(self._on_chat_msg)
        self.ws.joined_server.connect(self._on_joined)
        self.ws.user_joined.connect(self._on_user_join)
        self.ws.user_left.connect(self._on_user_leave)
        self.ws.start()

        # Timers
        self._presence_timer = QTimer()
        self._presence_timer.timeout.connect(self._poll_presence)
        self._presence_timer.start(self.PRESENCE_POLL_MS)

        self._overlay_timer = QTimer()
        self._overlay_timer.timeout.connect(self._safe_overlay_update)
        self._overlay_timer.start(self.OVERLAY_TICK_MS)

        rc = self.app.exec_()
        if self.ws:
            self.ws.stop()
        return rc

    def _safe_overlay_update(self):
        try:
            if self.overlay_mgr:
                self.overlay_mgr.update()
        except Exception:
            pass

    def _on_logout(self):
        """Handle logout: clear saved config and restart login."""
        config_manager.clear_config()
        QMessageBox.information(
            self.overlay, "Выход",
            "Вы вышли из аккаунта. Перезапустите программу для входа в новый аккаунт.",
        )
        if self.overlay:
            self.overlay.close()

    # ── WS callbacks ─────────────────────────────────────────────

    def _on_ws_connected(self):
        logger.info("WS connected to relay")
        if self.overlay:
            self.overlay.set_connecting()
        if self.ws and self.roblox:
            self.ws.authenticate(str(self.roblox.user_id), self._username)

    def _on_ws_disconnected(self):
        logger.info("WS disconnected from relay")
        if self.overlay:
            self.overlay.set_disconnected()

    def _on_auth_ok(self, _data: dict):
        logger.info("Relay server auth OK")
        if self.overlay:
            self.overlay.set_connected()
        self._poll_presence()

    def _on_auth_fail(self, reason: str):
        logger.error("Relay auth failed: %s", reason)
        if self.overlay:
            self.overlay.set_disconnected()

    def _on_chat_msg(self, data: dict):
        if self.overlay:
            self.overlay.add_message(
                data.get("channel", "server"),
                data.get("username", "???"),
                data.get("text", ""),
                data.get("timestamp", ""),
            )

    def _on_joined(self, data: dict):
        n = len(data.get("users", []))
        if self.overlay:
            self.overlay.add_message(
                "server", "Система",
                f"Подключено к серверу игры. Пользователей чата здесь: {n}",
                _now(), is_system=True,
            )

    def _on_user_join(self, data: dict):
        if self.overlay:
            self.overlay.add_message(
                "server", "Система",
                f"{data.get('username', '???')} подключился к серверному чату",
                data.get("timestamp", ""), is_system=True,
            )

    def _on_user_leave(self, data: dict):
        if self.overlay:
            self.overlay.add_message(
                "server", "Система",
                f"{data.get('username', '???')} отключился",
                data.get("timestamp", ""), is_system=True,
            )

    # ── Outgoing message (NO LOCAL DUPLICATION) ───────────────────

    def _on_send(self, channel: str, text: str):
        if not self._place_id:
            if self.overlay:
                self.overlay.add_message(
                    channel, "Система",
                    "Вы сейчас не в игре. Войдите в плейс Roblox, чтобы писать сообщения.",
                    _now(), is_system=True,
                )
            return

        if self.ws:
            self.ws.send_message(channel, text)

    # ── Safe presence polling with auto-clean on game leave/enter ─

    def _poll_presence(self):
        try:
            if not self.roblox or not self.ws:
                return

            presence = self.roblox.get_presence()

            if presence:
                pid = presence["place_id"]
                jid = presence.get("job_id") or "default"
                name = presence.get("place_name", "Игра")

                if pid != self._place_id or jid != self._job_id:
                    logger.info("Entered new game/server: place=%s job=%s (%s)", pid, jid, name)
                    self._place_id = pid
                    self._job_id = jid

                    # Clear previous game messages completely
                    if self.overlay:
                        self.overlay.clear_chats()
                        self.overlay.set_server_info(name)
                        self.overlay.add_message(
                            "server", "Система",
                            f"Вы вошли в {name}. Чат очищен и готов к общению.",
                            _now(), is_system=True,
                        )
                        self.overlay.add_message(
                            "global", "Система",
                            f"Глобальный чат подключен: {name}.",
                            _now(), is_system=True,
                        )

                    self.ws.join_server(pid, jid)
            else:
                # Player left the game / is not in-game
                if self._place_id is not None:
                    logger.info("Player left the game. Clearing chats.")
                    self._place_id = None
                    self._job_id = None

                    if self.overlay:
                        self.overlay.clear_chats()
                        self.overlay.set_server_info("Не в игре")
                        self.overlay.add_message(
                            "server", "Система",
                            "Вы вышли из плейса. Чат очищен. Ожидание захода в игру...",
                            _now(), is_system=True,
                        )
                        self.overlay.add_message(
                            "global", "Система",
                            "Вы вышли из плейса. Чат очищен.",
                            _now(), is_system=True,
                        )

                    self.ws.leave_server()
        except Exception as exc:
            logger.debug("Presence poll exception: %s", exc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main():
    app = RoChat()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
