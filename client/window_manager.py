"""
Windows-specific overlay Z-order management.

Keeps the chat window on top of Roblox but allows other applications
to cover it when they are in the foreground.
"""

import ctypes
import ctypes.wintypes
import logging

logger = logging.getLogger(__name__)

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

user32 = ctypes.windll.user32


def find_roblox_window() -> int:
    """Return HWND of the Roblox player window, or 0."""
    try:
        # Roblox uses the 'WINDOWSCLIENT' window class
        hwnd = user32.FindWindowW("WINDOWSCLIENT", None)
        if not hwnd:
            hwnd = user32.FindWindowW(None, "Roblox")
        return hwnd or 0
    except Exception:
        return 0


def _get_foreground() -> int:
    try:
        return user32.GetForegroundWindow()
    except Exception:
        return 0


def _get_class_name(hwnd: int) -> str:
    try:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    except Exception:
        return ""


def _get_window_text(hwnd: int) -> str:
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def _set_topmost(hwnd: int):
    try:
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
    except Exception:
        pass


def _remove_topmost(hwnd: int):
    try:
        user32.SetWindowPos(
            hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
    except Exception:
        pass


def _is_roblox(hwnd: int) -> bool:
    if not hwnd:
        return False
    try:
        cls = _get_class_name(hwnd)
        if cls == "WINDOWSCLIENT":
            return True
        return _get_window_text(hwnd) == "Roblox"
    except Exception:
        return False


class OverlayManager:
    """Keeps the overlay above Roblox, below everything else."""

    def __init__(self, overlay_hwnd: int):
        self.overlay_hwnd = overlay_hwnd
        self._is_topmost = False

    def update(self):
        try:
            fg = _get_foreground()

            if fg == self.overlay_hwnd:
                if not self._is_topmost:
                    _set_topmost(self.overlay_hwnd)
                    self._is_topmost = True
                return

            if _is_roblox(fg):
                if not self._is_topmost:
                    _set_topmost(self.overlay_hwnd)
                    self._is_topmost = True
            else:
                if self._is_topmost:
                    _remove_topmost(self.overlay_hwnd)
                    self._is_topmost = False
        except Exception:
            pass
