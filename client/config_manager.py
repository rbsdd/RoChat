"""
Configuration manager for RoChat.
Saves and loads user session and server settings in %APPDATA%/RoChat/config.json.
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "RoChat")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config() -> dict:
    """Load settings from config.json. Returns empty dict on failure."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load config: %s", exc)
        return {}


def save_config(cookie: str, server_url: str = "ws://localhost:8765", auto_login: bool = True) -> bool:
    """Save user session for automatic authentication on next startup."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {
            "cookie": cookie.strip(),
            "server_url": server_url.strip() or "ws://localhost:8765",
            "auto_login": bool(auto_login),
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:
        logger.warning("Failed to save config: %s", exc)
        return False


def clear_config() -> bool:
    """Clear saved credentials on logout."""
    try:
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        return True
    except Exception as exc:
        logger.warning("Failed to delete config: %s", exc)
        return False
