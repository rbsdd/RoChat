"""
Login dialog — collects .ROBLOSECURITY cookie and relay server URL.
Supports remembering user credentials for auto-login.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox,
)
from PyQt5.QtCore import Qt


class LoginDialog(QDialog):
    """Modal dialog shown when credentials are needed."""

    def __init__(self, initial_cookie: str = "", initial_server: str = "ws://localhost:8765", parent=None):
        super().__init__(parent)
        self.setWindowTitle("RoChat — Вход")
        self.setFixedSize(450, 340)
        self._initial_cookie = initial_cookie
        self._initial_server = initial_server
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1e2024;
                color: #e5e7eb;
            }
            QLabel {
                color: #d1d5db;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #16181b;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 8px 10px;
                color: #f3f4f6;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #6b7280;
            }
            QCheckBox {
                color: #d1d5db;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #4b5563;
                background: #16181b;
            }
            QCheckBox::indicator:checked {
                background: #3b82f6;
                border-color: #3b82f6;
            }
            QPushButton {
                background-color: #374151;
                color: #f9fafb;
                border: 1px solid #4b5563;
                border-radius: 6px;
                padding: 9px 18px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #4b5563;
                border-color: #6b7280;
            }
            QPushButton:pressed {
                background-color: #1f2937;
            }
        """)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(28, 20, 28, 20)

        # Title
        title = QLabel("🎮 RoChat")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #ffffff;")
        root.addWidget(title)

        sub = QLabel("Внешний чат для Roblox")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("font-size: 12px; color: #9ca3af;")
        root.addWidget(sub)

        root.addSpacing(4)

        # Cookie input
        root.addWidget(QLabel("🔑 .ROBLOSECURITY Cookie:"))
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText("Вставьте cookie сюда…")
        self.cookie_input.setEchoMode(QLineEdit.Password)
        if self._initial_cookie:
            self.cookie_input.setText(self._initial_cookie)
        root.addWidget(self.cookie_input)

        # Server input
        root.addWidget(QLabel("🌐 Сервер чата:"))
        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("ws://localhost:8765")
        self.server_input.setText(self._initial_server or "ws://localhost:8765")
        root.addWidget(self.server_input)

        # Remember me checkbox
        self.remember_cb = QCheckBox("Запомнить меня и входить автоматически")
        self.remember_cb.setChecked(True)
        root.addWidget(self.remember_cb)

        root.addSpacing(4)

        # Login button
        self.login_btn = QPushButton("Войти в чат")
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self.accept)
        root.addWidget(self.login_btn)

        # Note
        warn = QLabel("💡 Ключ сохраняется локально на вашем ПК для авто-входа.")
        warn.setWordWrap(True)
        warn.setStyleSheet("font-size: 10px; color: #6b7280;")
        root.addWidget(warn)

    def get_cookie(self) -> str:
        return self.cookie_input.text().strip()

    def get_server_url(self) -> str:
        return self.server_input.text().strip() or "ws://localhost:8765"

    def is_remember_checked(self) -> bool:
        return self.remember_cb.isChecked()
