"""
Main chat overlay window — frameless, translucent, draggable, resizable.
Styled to match native Roblox chat UI:
  - Neutral dark semi-transparent gray background (guaranteed via custom QPainter)
  - Colored player nicknames (hashed into Roblox name color palette)
  - Dual independent QStackedWidget views (server / global)
  - Global hotkey '/' (VK_OEM_2 & VK_DIVIDE) to activate chat directly from Roblox
  - Auto-clearing and refocusing on Escape / Enter
  - Bottom input bar matching screenshot
"""

import ctypes
import ctypes.wintypes
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QStackedWidget, QFrame
)
from PyQt5.QtCore import Qt, QPoint, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont

from window_manager import find_roblox_window, user32

# Win32 Global Hotkey constants
MOD_NOREPEAT = 0x4000
VK_OEM_2 = 0xBF    # '/?' key on standard US/RU keyboards
VK_DIVIDE = 0x6F   # '/' on Numpad
HOTKEY_SLASH = 2001
HOTKEY_NUMPAD = 2002
WM_HOTKEY = 0x0312


# ═══════════════════════════════════════════════════════════════════
#  Roblox Chat Nickname Colors Palette
# ═══════════════════════════════════════════════════════════════════

ROBLOX_NAME_COLORS = [
    "#E2253B",  # Bright red
    "#1F85DE",  # Bright blue
    "#00B06F",  # Bright green
    "#F5CD2F",  # Bright yellow
    "#FF793F",  # Bright orange
    "#9B59B6",  # Purple
    "#1ABC9C",  # Teal / turquoise
    "#E67E22",  # Amber
    "#2ECC71",  # Emerald
    "#3498DB",  # Light blue
    "#E84393",  # Rose pink
    "#F39C12",  # Gold
]


def get_nickname_color(username: str) -> str:
    """Consistently hashes username to one of Roblox's signature name colors."""
    if not username:
        return "#FFFFFF"
    val = sum(ord(c) for c in username)
    return ROBLOX_NAME_COLORS[val % len(ROBLOX_NAME_COLORS)]


# ═══════════════════════════════════════════════════════════════════
#  Custom Background Panel (Guarantees translucent dark-gray)
# ═══════════════════════════════════════════════════════════════════

class MainBackgroundPanel(QWidget):
    """
    Renders a dark-gray semi-transparent background with rounded corners.
    Eliminates any default white window background from Qt.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor(25, 27, 31, 200)       # 78% opacity dark gray
        border_color = QColor(80, 85, 95, 90)    # subtle border

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)


# ═══════════════════════════════════════════════════════════════════
#  Title bar & Controls
# ═══════════════════════════════════════════════════════════════════

class TitleBar(QWidget):
    """Minimalistic draggable title bar with channel switchers, pin, logout and close."""

    channel_changed = pyqtSignal(str)
    logout_clicked = pyqtSignal()

    def __init__(self, parent: "ChatOverlay"):
        super().__init__(parent)
        self._parent = parent
        self._dragging = False
        self._drag_origin = QPoint()
        self.setFixedHeight(32)
        self._current_channel = "server"
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(6)

        # Tab buttons
        self.btn_server = QPushButton("Сервер")
        self.btn_server.setCheckable(True)
        self.btn_server.setChecked(True)
        self.btn_server.setCursor(Qt.PointingHandCursor)
        self.btn_server.clicked.connect(lambda: self._select_channel("server"))

        self.btn_global = QPushButton("Глобальный")
        self.btn_global.setCheckable(True)
        self.btn_global.setChecked(False)
        self.btn_global.setCursor(Qt.PointingHandCursor)
        self.btn_global.clicked.connect(lambda: self._select_channel("global"))

        tab_style = """
            QPushButton {
                background: rgba(45, 48, 54, 0.7);
                border: 1px solid rgba(85, 90, 100, 0.5);
                border-radius: 4px;
                color: #b0b5bc;
                font-size: 11px;
                font-weight: 600;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background: rgba(65, 70, 80, 0.85);
                color: #ffffff;
            }
            QPushButton:checked {
                background: rgba(75, 80, 92, 0.9);
                border: 1px solid rgba(140, 145, 160, 0.8);
                color: #ffffff;
            }
        """
        self.btn_server.setStyleSheet(tab_style)
        self.btn_global.setStyleSheet(tab_style)

        lay.addWidget(self.btn_server)
        lay.addWidget(self.btn_global)

        # Status badge
        self.status = QLabel("●")
        self.status.setToolTip("Статус подключения")
        self.status.setStyleSheet("color: #ef4444; font-size: 11px; background: transparent; margin-left: 2px;")
        lay.addWidget(self.status)

        lay.addStretch()

        btn_ctrl_css = """
            QPushButton {
                background: transparent;
                border: none;
                color: #9da3aa;
                font-size: 13px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
                color: #ffffff;
            }
        """

        # Pin button
        self.pin_btn = QPushButton("📌")
        self.pin_btn.setFixedSize(24, 24)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setToolTip("Закрепить положение на экране")
        self.pin_btn.setStyleSheet(btn_ctrl_css + """
            QPushButton:checked {
                background: rgba(255, 255, 255, 0.25);
                color: #ffffff;
            }
        """)
        lay.addWidget(self.pin_btn)

        # Opacity button
        self.opacity_btn = QPushButton("🌙")
        self.opacity_btn.setFixedSize(24, 24)
        self.opacity_btn.setCheckable(True)
        self.opacity_btn.setToolTip("Переключить прозрачность")
        self.opacity_btn.setStyleSheet(btn_ctrl_css + """
            QPushButton:checked {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        self.opacity_btn.toggled.connect(self._toggle_opacity)
        lay.addWidget(self.opacity_btn)

        # Logout button
        self.logout_btn = QPushButton("🚪")
        self.logout_btn.setFixedSize(24, 24)
        self.logout_btn.setToolTip("Выйти из аккаунта")
        self.logout_btn.setStyleSheet(btn_ctrl_css)
        self.logout_btn.clicked.connect(self.logout_clicked.emit)
        lay.addWidget(self.logout_btn)

        # Minimize button
        btn_min = QPushButton("─")
        btn_min.setFixedSize(22, 22)
        btn_min.setStyleSheet(btn_ctrl_css)
        btn_min.clicked.connect(self._parent.showMinimized)
        lay.addWidget(btn_min)

        # Close button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(22, 22)
        btn_close.setStyleSheet(btn_ctrl_css + """
            QPushButton:hover {
                background: #e11d48;
                color: #ffffff;
            }
        """)
        btn_close.clicked.connect(self._parent.close)
        lay.addWidget(btn_close)

    def _select_channel(self, channel: str):
        self._current_channel = channel
        self.btn_server.setChecked(channel == "server")
        self.btn_global.setChecked(channel == "global")
        self.channel_changed.emit(channel)

    def set_status(self, text: str, color: str):
        self.status.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent; margin-left: 2px;")
        self.status.setToolTip(text)

    def _toggle_opacity(self, on: bool):
        self._parent.setWindowOpacity(0.55 if on else 0.88)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and not self.pin_btn.isChecked():
            self._dragging = True
            self._drag_origin = ev.globalPos() - self._parent.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._dragging and not self.pin_btn.isChecked():
            self._parent.move(ev.globalPos() - self._drag_origin)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._dragging = False


# ═══════════════════════════════════════════════════════════════════
#  Roblox-styled Single Message with Player Color
# ═══════════════════════════════════════════════════════════════════

class ChatMessage(QWidget):
    """
    Renders message in classic Roblox format:
    e.g. [Server] Username: Hello world!
    Player nickname is uniquely colored based on username hash.
    """

    def __init__(self, channel_tag: str, username: str, text: str,
                 timestamp: str = "", is_system: bool = False, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 1, 4, 1)
        lay.setSpacing(4)

        lbl = QLabel(self)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setStyleSheet("background: transparent;")

        font = QFont("Segoe UI", 10)
        font.setStyleHint(QFont.SansSerif)
        lbl.setFont(font)

        if is_system:
            lbl.setText(
                f"<span style='color: #9ca3af;'>[{channel_tag}]</span> "
                f"<span style='color: #e5e7eb; font-style: italic;'>{text}</span>"
            )
        else:
            time_part = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    time_part = f"<span style='color: #6b7280; font-size: 10px;'> {dt.strftime('%H:%M')}</span>"
                except Exception:
                    pass

            tag_color = "#38bdf8" if channel_tag.lower() in ("global", "глобал") else "#4ade80"
            name_color = get_nickname_color(username)

            lbl.setText(
                f"<span style='color: {tag_color}; font-weight: 600;'>[{channel_tag}]</span> "
                f"<span style='color: {name_color}; font-weight: 600;'>{username}:</span> "
                f"<span style='color: #ffffff;'>{text}</span>"
                f"{time_part}"
            )

        lay.addWidget(lbl)


# ═══════════════════════════════════════════════════════════════════
#  Scrollable Message View (100% Transparent, No White Background)
# ═══════════════════════════════════════════════════════════════════

class ChatMessageView(QScrollArea):
    MAX_MESSAGES = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.viewport().setAutoFillBackground(False)
        self.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        self.viewport().setStyleSheet("background: transparent;")

        self.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(120, 125, 135, 0.4);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(160, 165, 175, 0.65);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self._container = QWidget()
        self._container.setAttribute(Qt.WA_TranslucentBackground, True)
        self._container.setStyleSheet("background: transparent;")

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._layout.addStretch()

        self.setWidget(self._container)

    def add_message(self, tag: str, username: str, text: str, timestamp: str, is_system: bool):
        try:
            if self._layout.count() > self.MAX_MESSAGES:
                item = self._layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

            msg = ChatMessage(tag, username, text, timestamp, is_system, self._container)
            self._layout.insertWidget(self._layout.count() - 1, msg)
            QTimer.singleShot(40, self.scroll_to_bottom)
        except Exception:
            pass

    def clear(self):
        try:
            while self._layout.count() > 1:
                item = self._layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
        except Exception:
            pass

    def scroll_to_bottom(self):
        try:
            sb = self.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
#  Resize Grip for bottom-right corner
# ═══════════════════════════════════════════════════════════════════

class _ResizeGrip(QWidget):
    def __init__(self, parent: "ChatOverlay"):
        super().__init__(parent)
        self._parent = parent
        self.setFixedSize(14, 14)
        self.setCursor(Qt.SizeFDiagCursor)
        self._active = False
        self._origin = QPoint()
        self._orig_size = QSize()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setPen(QPen(QColor(140, 145, 155, 140), 1))
        w, h = self.width(), self.height()
        for i in range(3):
            p.drawLine(w - 3 - i * 3, h - 3, w - 3, h - 3 - (2 - i) * 3)

    def mousePressEvent(ev_self, ev):
        if ev.button() == Qt.LeftButton:
            ev_self._active = True
            ev_self._origin = ev.globalPos()
            ev_self._orig_size = ev_self._parent.size()

    def mouseMoveEvent(ev_self, ev):
        if ev_self._active:
            d = ev.globalPos() - ev_self._origin
            ev_self._parent.resize(
                max(320, ev_self._orig_size.width() + d.x()),
                max(200, ev_self._orig_size.height() + d.y()),
            )

    def mouseReleaseEvent(ev_self, _ev):
        ev_self._active = False


# ═══════════════════════════════════════════════════════════════════
#  Main Chat Overlay Window
# ═══════════════════════════════════════════════════════════════════

class ChatOverlay(QWidget):
    """
    Overlay window styled exactly like native Roblox chat:
    - Neutral dark-gray semi-transparent background (no white, no blue)
    - Two separate independent views (Server / Global) via QStackedWidget
    - Global '/' key capture to open chat seamlessly while in Roblox
    """

    send_message = pyqtSignal(str, str)  # channel, text
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(320, 200)
        self.resize(460, 260)
        self.setWindowOpacity(0.88)

        self._current_channel = "server"
        self._build()

        # Register global hotkey for '/' so pressing '/' anywhere in Roblox focuses the chat
        self._register_slash_hotkeys()

    def _register_slash_hotkeys(self):
        try:
            hwnd = int(self.winId())
            user32.RegisterHotKey(hwnd, HOTKEY_SLASH, MOD_NOREPEAT, VK_OEM_2)
            user32.RegisterHotKey(hwnd, HOTKEY_NUMPAD, MOD_NOREPEAT, VK_DIVIDE)
        except Exception:
            pass

    def _unregister_slash_hotkeys(self):
        try:
            hwnd = int(self.winId())
            user32.UnregisterHotKey(hwnd, HOTKEY_SLASH)
            user32.UnregisterHotKey(hwnd, HOTKEY_NUMPAD)
        except Exception:
            pass

    def closeEvent(self, ev):
        self._unregister_slash_hotkeys()
        super().closeEvent(ev)

    def nativeEvent(self, eventType, message):
        try:
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == WM_HOTKEY:
                # The user pressed '/' in Roblox or anywhere in Windows!
                self.focus_chat_input()
                return True, 0
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._container = MainBackgroundPanel(self)
        outer.addWidget(self._container)

        inner = QVBoxLayout(self._container)
        inner.setContentsMargins(8, 6, 8, 8)
        inner.setSpacing(4)

        # Title bar (Server / Global buttons + Controls)
        self.title_bar = TitleBar(self)
        self.title_bar.channel_changed.connect(self._on_channel_switch)
        self.title_bar.logout_clicked.connect(self.logout_requested.emit)
        inner.addWidget(self.title_bar)

        # Independent message views in a QStackedWidget
        self.stack = QStackedWidget(self._container)
        self.stack.setStyleSheet("background: transparent;")

        self.server_view = ChatMessageView(self.stack)
        self.global_view = ChatMessageView(self.stack)

        self.stack.addWidget(self.server_view)  # index 0: server
        self.stack.addWidget(self.global_view)  # index 1: global
        self.stack.setCurrentIndex(0)

        inner.addWidget(self.stack, 1)

        # Bottom Input Bar (Dark bar with border & placeholder matching image)
        self.input_frame = QFrame()
        self.input_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 20, 23, 0.90);
                border: 1px solid rgba(85, 90, 100, 0.55);
                border-radius: 6px;
            }
        """)
        input_lay = QHBoxLayout(self.input_frame)
        input_lay.setContentsMargins(10, 3, 8, 3)
        input_lay.setSpacing(6)

        self.input = QLineEdit()
        self.input.setPlaceholderText("To chat click here or press / key")
        self.input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #ffffff;
                font-size: 13px;
                padding: 4px 0px;
            }
            QLineEdit::placeholder {
                color: #7d838b;
            }
        """)
        self.input.returnPressed.connect(self._send)
        input_lay.addWidget(self.input, 1)

        # Send arrow icon
        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(26, 26)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setToolTip("Отправить")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #8b929b;
                font-size: 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: rgba(255, 255, 255, 0.12);
            }
        """)
        self.send_btn.clicked.connect(self._send)
        input_lay.addWidget(self.send_btn)

        inner.addWidget(self.input_frame)

        # Corner resize grip
        self._grip = _ResizeGrip(self)

    # ── Channel Switching ─────────────────────────────────────────

    def _on_channel_switch(self, channel: str):
        self._current_channel = channel
        self.stack.setCurrentIndex(0 if channel == "server" else 1)

    # ── Focus & Hotkey Support ────────────────────────────────────

    def focus_chat_input(self):
        """Brings overlay to foreground and focuses the input field."""
        try:
            self.show()
            self.raise_()
            self.activateWindow()
            hwnd = int(self.winId())
            user32.SetForegroundWindow(hwnd)
            self.input.setFocus()
            self.input.selectAll()
        except Exception:
            pass

    def _return_focus_to_roblox(self):
        """Returns focus back to Roblox client so player can move right away."""
        try:
            roblox_hwnd = find_roblox_window()
            if roblox_hwnd:
                user32.SetForegroundWindow(roblox_hwnd)
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────

    def add_message(self, channel: str, username: str, text: str,
                    timestamp: str, is_system: bool = False):
        try:
            tag = "Сервер" if channel == "server" else "Глобал"
            if channel == "server":
                self.server_view.add_message(tag, username, text, timestamp, is_system)
            elif channel == "global":
                self.global_view.add_message(tag, username, text, timestamp, is_system)
            else:
                self.server_view.add_message(tag, username, text, timestamp, is_system)
                self.global_view.add_message(tag, username, text, timestamp, is_system)
        except Exception:
            pass

    def set_server_info(self, text: str):
        self.title_bar.set_status(f"{text}", "#22c55e" if text != "Не в игре" else "#ef4444")

    def set_connected(self):
        self.title_bar.set_status("Подключен к RoChat", "#22c55e")

    def set_disconnected(self):
        self.title_bar.set_status("Отключен", "#ef4444")

    def set_connecting(self):
        self.title_bar.set_status("Подключение…", "#f59e0b")

    def clear_chats(self):
        try:
            self.server_view.clear()
            self.global_view.clear()
        except Exception:
            pass

    # ── Input & Key events ────────────────────────────────────────

    def _send(self):
        text = self.input.text().strip()
        if text:
            self.send_message.emit(self._current_channel, text)
            self.input.clear()
            # In Roblox, pressing Enter returns keyboard control to player
            self.input.clearFocus()
            self._return_focus_to_roblox()

    def keyPressEvent(self, ev):
        # When pressing '/' anywhere while overlay is focused, activate input
        if not self.input.hasFocus():
            if (
                ev.key() in (Qt.Key_Slash, Qt.Key_Backslash)
                or ev.text() in ("/", ".", ",")
            ):
                self.focus_chat_input()
                ev.accept()
                return
        elif ev.key() == Qt.Key_Escape:
            # Escape cancels typing and returns control to Roblox
            self.input.clearFocus()
            self._return_focus_to_roblox()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._grip.move(
            self.width() - self._grip.width(),
            self.height() - self._grip.height(),
        )
