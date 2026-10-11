#!/usr/bin/env python3
"""
RoChat — WebSocket Relay Server
Routes chat messages between clients based on Roblox Place ID and Server Job ID.

Channels:
  - 'server': messages go only to clients on the same (place_id, job_id)
  - 'global': messages go to all clients in the same place_id
"""

import asyncio
import json
import logging
import argparse
from collections import defaultdict
from datetime import datetime, timezone

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package is required. Install with: pip install websockets")
    raise SystemExit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rochat-server")


class ChatServer:
    """WebSocket relay server for Roblox external chat."""

    MAX_MESSAGE_LENGTH = 500

    def __init__(self):
        # ws -> client info dict
        self.clients: dict = {}
        # place_id -> set[ws]  (global chat rooms)
        self.place_rooms: dict[str, set] = defaultdict(set)
        # (place_id, job_id) -> set[ws]  (server chat rooms)
        self.server_rooms: dict[tuple, set] = defaultdict(set)

    # ── connection lifecycle ─────────────────────────────────────────

    async def register(self, ws):
        self.clients[ws] = {
            "user_id": None,
            "username": None,
            "place_id": None,
            "job_id": None,
            "authenticated": False,
        }
        logger.info("Client connected: %s", ws.remote_address)

    async def unregister(self, ws):
        if ws not in self.clients:
            return
        client = self.clients[ws]
        await self._leave_rooms(ws)
        name = client.get("username") or str(ws.remote_address)
        logger.info("Client disconnected: %s", name)
        del self.clients[ws]

    # ── room helpers ─────────────────────────────────────────────────

    async def _leave_rooms(self, ws):
        client = self.clients.get(ws)
        if not client:
            return

        place_id = client.get("place_id")
        job_id = client.get("job_id")

        if place_id:
            self.place_rooms[place_id].discard(ws)
            if not self.place_rooms[place_id]:
                del self.place_rooms[place_id]

        if place_id and job_id:
            key = (place_id, job_id)
            self.server_rooms[key].discard(ws)
            await self._broadcast_to_server(key, {
                "type": "user_left",
                "username": client["username"],
                "user_id": client["user_id"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, exclude=ws)
            if not self.server_rooms[key]:
                del self.server_rooms[key]

        client["place_id"] = None
        client["job_id"] = None

    async def _broadcast_to_place(self, place_id, message, exclude=None):
        targets = self.place_rooms.get(place_id, set())
        payload = json.dumps(message, ensure_ascii=False)
        coros = [ws.send(payload) for ws in targets if ws != exclude]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def _broadcast_to_server(self, key, message, exclude=None):
        targets = self.server_rooms.get(key, set())
        payload = json.dumps(message, ensure_ascii=False)
        coros = [ws.send(payload) for ws in targets if ws != exclude]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    # ── message handlers ─────────────────────────────────────────────

    async def handle_auth(self, ws, data):
        client = self.clients[ws]
        user_id = data.get("user_id")
        username = data.get("username")

        if not user_id or not username:
            await ws.send(json.dumps({
                "type": "auth_fail",
                "reason": "Missing user_id or username",
            }))
            return

        client["user_id"] = str(user_id)
        client["username"] = str(username)
        client["authenticated"] = True

        await ws.send(json.dumps({
            "type": "auth_ok",
            "user_id": client["user_id"],
            "username": client["username"],
        }))
        logger.info("Authenticated: %s (ID %s)", username, user_id)

    async def handle_join(self, ws, data):
        client = self.clients[ws]
        if not client["authenticated"]:
            return

        await self._leave_rooms(ws)

        place_id = str(data.get("place_id", "")).strip()
        job_id = str(data.get("job_id", "")).strip() or "default"
        if not place_id:
            return

        client["place_id"] = place_id
        client["job_id"] = job_id

        self.place_rooms[place_id].add(ws)
        key = (place_id, job_id)
        self.server_rooms[key].add(ws)

        # Build user list for this server
        users = []
        for other_ws in self.server_rooms[key]:
            other = self.clients.get(other_ws)
            if other:
                users.append({
                    "user_id": other["user_id"],
                    "username": other["username"],
                })

        await ws.send(json.dumps({
            "type": "joined",
            "place_id": place_id,
            "job_id": job_id,
            "users": users,
        }))

        await self._broadcast_to_server(key, {
            "type": "user_joined",
            "username": client["username"],
            "user_id": client["user_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, exclude=ws)

        logger.info("%s joined place=%s server=%s", client["username"], place_id, job_id)

    async def handle_message(self, ws, data):
        client = self.clients[ws]
        if not client["authenticated"] or not client["place_id"]:
            return

        channel = data.get("channel", "server")
        text = str(data.get("text", "")).strip()
        if not text or len(text) > self.MAX_MESSAGE_LENGTH:
            return

        message = {
            "type": "message",
            "channel": channel,
            "username": client["username"],
            "user_id": client["user_id"],
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if channel == "global":
            await self._broadcast_to_place(client["place_id"], message)
        else:  # server
            key = (client["place_id"], client["job_id"])
            await self._broadcast_to_server(key, message)

    # ── main handler ─────────────────────────────────────────────────

    async def handle_client(self, ws, path=None):
        await self.register(ws)
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from %s", ws.remote_address)
                    continue

                msg_type = data.get("type")
                if msg_type == "auth":
                    await self.handle_auth(ws, data)
                elif msg_type == "join":
                    await self.handle_join(ws, data)
                elif msg_type == "leave":
                    await self._leave_rooms(ws)
                elif msg_type == "message":
                    await self.handle_message(ws, data)
                elif msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
        except websockets.ConnectionClosed:
            pass
        finally:
            await self.unregister(ws)

    # ── entry point ──────────────────────────────────────────────────

    async def start(self, host="0.0.0.0", port=8765):
        logger.info("RoChat server starting on %s:%s", host, port)
        async with websockets.serve(self.handle_client, host, port):
            logger.info("Server is running. Press Ctrl+C to stop.")
            await asyncio.Future()  # run forever


def main():
    parser = argparse.ArgumentParser(description="RoChat Relay Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    args = parser.parse_args()

    server = ChatServer()
    try:
        asyncio.run(server.start(host=args.host, port=args.port))
    except KeyboardInterrupt:
        logger.info("Server stopped.")


if __name__ == "__main__":
    main()
