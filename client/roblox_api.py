"""
Roblox API wrapper — authentication and presence detection.

Uses the .ROBLOSECURITY cookie to:
  1. Verify the account via /v1/users/authenticated
  2. Poll game presence via /v1/presence/users (with CSRF handling)
"""

import logging
import requests

logger = logging.getLogger(__name__)


class RobloxAPI:
    """Thin wrapper around Roblox web APIs."""

    USERS_URL = "https://users.roblox.com"
    PRESENCE_URL = "https://presence.roblox.com"

    def __init__(self, cookie: str):
        self.session = requests.Session()
        self.session.cookies.set(".ROBLOSECURITY", cookie, domain=".roblox.com")
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        self.user_id: int | None = None
        self.username: str | None = None
        self.display_name: str | None = None

    def authenticate(self) -> bool:
        """Verify cookie and retrieve account info."""
        try:
            resp = self.session.get(
                f"{self.USERS_URL}/v1/users/authenticated",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.user_id = data.get("id")
                self.username = data.get("name")
                self.display_name = data.get("displayName")
                logger.info(
                    "Authenticated as %s (display: %s, id: %s)",
                    self.username,
                    self.display_name,
                    self.user_id,
                )
                return True
            logger.warning("Auth failed: HTTP %s", resp.status_code)
            return False
        except Exception as exc:
            logger.warning("Auth request error: %s", exc)
            return False

    def get_presence(self) -> dict | None:
        """Return current game presence or None if not in-game or on error."""
        if not self.user_id:
            return None
        try:
            payload = {"userIds": [self.user_id]}
            resp = self.session.post(
                f"{self.PRESENCE_URL}/v1/presence/users",
                json=payload,
                timeout=5,
            )

            # Handle Roblox CSRF token challenge
            if resp.status_code == 403 and "x-csrf-token" in resp.headers:
                self.session.headers["X-CSRF-TOKEN"] = resp.headers["x-csrf-token"]
                resp = self.session.post(
                    f"{self.PRESENCE_URL}/v1/presence/users",
                    json=payload,
                    timeout=5,
                )

            if resp.status_code != 200:
                return None

            data = resp.json()
            if not isinstance(data, dict):
                return None

            presences = data.get("userPresences", [])
            if not presences or not isinstance(presences, list):
                return None

            p = presences[0]
            if not isinstance(p, dict):
                return None

            # userPresenceType: 0=Offline, 1=Online, 2=InGame, 3=InStudio
            presence_type = p.get("userPresenceType", 0)
            place_id = p.get("placeId")

            # Must be actively InGame (2) and have a valid placeId
            if presence_type != 2 or not place_id:
                return None

            return {
                "place_id": str(place_id),
                "job_id": str(p.get("gameId", "") or "default"),
                "place_name": str(p.get("lastLocation", "Игра") or "Игра"),
                "presence_type": presence_type,
            }
        except Exception as exc:
            logger.debug("Presence error: %s", exc)
            return None
