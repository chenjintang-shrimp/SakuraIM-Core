from __future__ import annotations

import asyncio
from dataclasses import Field, dataclass, field
from uuid import UUID

from fastapi import WebSocket
from loguru import logger

from app.models.messages.base import MessageBase


@dataclass
class AdapterSession:
    aid: UUID
    websocket: WebSocket
    outbox: asyncio.Queue[MessageBase | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=1000)
    )


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[
            UUID, AdapterSession
        ] = {}  # UUID(aid) -> AdapterSession(cid)
        self.lock = asyncio.Lock()

    async def register_connection(
        self, websocket: WebSocket, aid: UUID
    ) -> AdapterSession:
        session = AdapterSession(aid, websocket)
        async with self.lock:
            old = self.active_connections.get(aid)
            if old is not None:
                # oops. smth bad happened
                logger.warning(f"adapter {aid} already registered")
                await old.outbox.put(None)
            self.active_connections[aid] = session
            logger.info(f"registered adapter{aid}")
        return session
