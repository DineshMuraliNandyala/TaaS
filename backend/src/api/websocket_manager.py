"""
WebSocket Connection Manager
─────────────────────────────
Module-level singleton that tracks all active WebSocket connections
and provides broadcast + targeted send capabilities.

Design:
  - Connections are stored in a set — O(1) add/remove
  - Broadcast is fire-and-forget per connection — a slow or dead
    client never blocks delivery to healthy clients
  - Dead connections are pruned automatically on send failure

Usage:
    from backend.src.api.websocket_manager import ws_manager
    await ws_manager.broadcast(payload_dict)
"""
import asyncio
import json
from typing import Any

from fastapi import WebSocket

from backend.src.logger import get_logger

log = get_logger(__name__)


class WebSocketManager:
    """
    Manages the lifecycle of all active WebSocket connections.
    Thread-safe for asyncio — all operations are coroutines.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections.add(websocket)
        log.info(
            "websocket_client_connected",
            total_connections=self.connection_count,
            client=websocket.client,
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the registry."""
        self._connections.discard(websocket)
        log.info(
            "websocket_client_disconnected",
            total_connections=self.connection_count,
        )

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """
        Send a JSON payload to all connected clients.
        Dead connections are detected and pruned during broadcast.
        Each client send is independent — one failure does not affect others.
        """
        if not self._connections:
            log.debug("broadcast_skipped", reason="no_connected_clients")
            return

        message = json.dumps(payload, default=str)
        dead: set[WebSocket] = set()

        # Gather all send coroutines and run concurrently
        async def _send(ws: WebSocket) -> None:
            try:
                await ws.send_text(message)
            except Exception as exc:
                log.warning(
                    "websocket_send_failed",
                    client=ws.client,
                    error=str(exc),
                )
                dead.add(ws)

        await asyncio.gather(*[_send(ws) for ws in self._connections])

        # Prune dead connections
        for ws in dead:
            self._connections.discard(ws)

        log.debug(
            "broadcast_complete",
            recipients=self.connection_count,
            pruned=len(dead),
        )

    async def send_to(
        self,
        websocket: WebSocket,
        payload: dict[str, Any],
    ) -> None:
        """Send a JSON payload to a single specific client."""
        try:
            await websocket.send_text(json.dumps(payload, default=str))
        except Exception as exc:
            log.warning(
                "websocket_targeted_send_failed",
                client=websocket.client,
                error=str(exc),
            )
            self._connections.discard(websocket)


# Module-level singleton — import this everywhere
ws_manager = WebSocketManager()