from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
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

    async def deregister_connection(self, aid: UUID) -> None:
        async with self.lock:
            current = self.active_connections.get(aid)
            if current is not None:
                self.active_connections.pop(aid)
                logger.info(f"deregistered adapter{aid}")

    async def send_to(self, aid: UUID, message: MessageBase) -> bool:
        async with self.lock:
            session = self.active_connections.get(aid)
        if session is None:
            logger.warning(f"adapter {aid} not found")
            return False
        try:
            await session.outbox.put(message)
            return True
        except asyncio.QueueFull:
            logger.warning(f"adapter {aid} outbox full")
            return False


manager = ConnectionManager()
