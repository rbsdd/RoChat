"""
Roblox API wrapper — authentication and presence detection.

Uses:
  1. Direct local Roblox client logs (%LOCALAPPDATA%/Roblox/logs) for instant,
     100% reliable detection of Place ID and Job ID regardless of privacy settings.
  2. Web API fallback (/v1/presence/users) with CSRF challenge handling.
  3. Games API (/v1/games/multiget-place-details) to retrieve game titles.
"""

import os
import glob
import re
import ctypes
from ctypes import wintypes
import logging
import requests

logger = logging.getLogger(__name__)

# Win32 Process Snapshot
TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def is_roblox_process_running() -> bool:
    """Check if RobloxPlayerBeta.exe is currently active on Windows."""
    try:
        kernel32 = ctypes.windll.kernel32
        h_snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if h_snapshot == -1:
            return False
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        found = False
        if kernel32.Process32First(h_snapshot, ctypes.byref(pe)):
            while True:
                exe = pe.szExeFile.decode("utf-8", errors="ignore").lower()
                if "robloxplayer" in exe:
                    found = True
                    break
                if not kernel32.Process32Next(h_snapshot, ctypes.byref(pe)):
                    break
        kernel32.CloseHandle(h_snapshot)
        return found
    except Exception:
        return False


class RobloxAPI:
    """Thin wrapper around Roblox web APIs and local client monitoring."""

    USERS_URL = "https://users.roblox.com"
    PRESENCE_URL = "https://presence.roblox.com"
    GAMES_URL = "https://games.roblox.com"

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
        self._place_names: dict[str, str] = {}

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

    def get_place_name(self, place_id: str) -> str:
        """Fetch game name by Place ID with caching."""
        if not place_id:
            return "Игра"
        if place_id in self._place_names:
            return self._place_names[place_id]
        try:
            resp = self.session.get(
                f"{self.GAMES_URL}/v1/games/multiget-place-details?placeIds={place_id}",
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    name = data[0].get("sourceName") or data[0].get("name") or "Игра"
                    self._place_names[place_id] = name
                    return name
        except Exception:
            pass
        return "Игра"

    def get_local_presence(self) -> dict | None:
        """Parse local Roblox client log for real-time in-game detection."""
        if not is_roblox_process_running():
            return None

        log_dir = os.path.expandvars(r"%LOCALAPPDATA%\Roblox\logs")
        if not os.path.isdir(log_dir):
            return None

        logs = glob.glob(os.path.join(log_dir, "*_Player_*_last.log"))
        if not logs:
            return None

        logs.sort(key=os.path.getmtime, reverse=True)
        latest_log = logs[0]

        last_join = None
        last_join_idx = -1
        last_leave_idx = -1

        try:
            with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                for idx, line in enumerate(f):
                    m = re.search(r"! Joining game '([^']+)' place (\d+)", line)
                    if m:
                        last_join = (m.group(2), m.group(1))  # (place_id, job_id)
                        last_join_idx = idx
                    elif any(k in line for k in ("returnToLuaApp: (stage:UGCGame)", "Client:Disconnect", "Destroying MegaReplicator")):
                        last_leave_idx = idx
        except Exception as exc:
            logger.debug("Failed to read Roblox log: %s", exc)
            return None

        if last_join and last_join_idx > last_leave_idx:
            place_id, job_id = last_join
            place_name = self.get_place_name(place_id)
            return {
                "place_id": place_id,
                "job_id": job_id,
                "place_name": place_name,
                "presence_type": 2,
            }

        return None

    def get_presence(self) -> dict | None:
        """Return current game presence via local log (primary) or web API (fallback)."""
        # 1. Try local log detection (fastest, 100% reliable, immune to privacy settings)
        local_pres = self.get_local_presence()
        if local_pres:
            return local_pres

        # If Roblox process is running on this PC but local log says in-menu / not in game
        if is_roblox_process_running():
            return None

        # 2. Fallback to web API (e.g. if logs unavailable or playing on another device)
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

            pid_str = str(place_id)
            name = str(p.get("lastLocation", "") or "")
            if not name or name == "Игра" or name == "Website":
                name = self.get_place_name(pid_str)

            return {
                "place_id": pid_str,
                "job_id": str(p.get("gameId", "") or "default"),
                "place_name": name,
                "presence_type": presence_type,
            }
        except Exception as exc:
            logger.debug("Presence error: %s", exc)
            return None
